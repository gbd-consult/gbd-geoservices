"""Classification: OSM tags -> render class, search categories.

This is the one place tags are read. It runs once per object at import time
and everything downstream reads columns, not tags (DESIGN.md
"Classifier rules", "The compiled classifier").

Evaluating 1 760 rules per object in Python would be far too slow for 5 M
objects, so the rules are compiled to bitmasks:

1. every `key=value` and `key=*` any rule mentions gets a bit number (1 554
   of them today, over 173 relevant keys);
2. each `+`-conjunction becomes one mask, and a rule is one mask per `|`
   alternative;
3. every mask is indexed by its rarest bit, so an object tests only the
   handful of rules that mention one of its own tags;
4. the finished Result is memoised on the tag bits, which collapses 5 M
   objects to a few thousand distinct classifications.

Step 4 memoises the *Result*, not just the matching rules: the ancestor
expansion and the importance lookup are the expensive part and depend on
nothing else, so they are paid once per distinct tag set too.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

#: The three geometry terms a rule's match can carry, and the vocabulary
#: the rest of the importer uses for an object's own geometry.
KINDS = ('point', 'line', 'polygon')

#: `class: none` on a rule: the class is decided, and there is none. The
#: first matching rule with a class sets it, so a rule without one cannot
#: stop a later one -- a municipality relation tagged `place=city` would be
#: drawn as a second city label by the `place=city` rule. Not a class:
#: nothing styles it, nothing checks it against the style.
NO_CLASS = 'none'


@dataclass(frozen=True, slots=True)
class Rule:
    masks: tuple[int, ...]          # one per `|` alternative; a rule matches if any matches
    category: str
    cls: str | None                 # absent on a search-only rule
    geometry: str | None            # None means any
    min_px: float | None
    fallback: bool = False          # a bare `key=*`: counts only where no rule on its key matched
    keys: frozenset[str] = frozenset()   # every key the rule's match names


@dataclass(frozen=True, slots=True)
class Result:
    cls: str | None
    min_px: float | None
    categories: tuple[str, ...]     # every matched category plus all their ancestors
    category: str | None            # the first rule that matched
    importance: int | None          # the category's, 0-100; None without a category


EMPTY = Result(None, None, (), None, None)


def split_geometry(expr: str) -> tuple[str, str | None]:
    """`a=b + c=* + line` -> ('a=b + c=*', 'line').

    A term without `=` restricts the rule to one geometry. It is part of the
    match rather than a key of its own so a rule reads as one condition;
    every `|` alternative has to name the same one, because the restriction
    belongs to the rule, not to an alternative.
    """
    geometries, alternatives = set(), []
    for alternative in expr.split('|'):
        terms = []
        found = None
        for term in alternative.split('+'):
            word = term.strip()
            if word in KINDS:
                if found is not None:
                    raise ValueError(f'two geometries in {expr!r}')
                found = word
            else:
                terms.append(word)
        geometries.add(found)
        alternatives.append(' + '.join(terms))
    if len(geometries) > 1:
        raise ValueError(f'alternatives name different geometries: {expr!r}')
    return ' | '.join(alternatives), geometries.pop()


def parse_match(expr: str) -> list[list[tuple[str, str]]]:
    """`a=b + c=* | d=e` -> [[('a','b'), ('c','*')], [('d','e')]].

    Parentheses are used by none of the rules, so they are rejected rather
    than implemented: precedence rules nobody exercises are precedence
    rules nobody has tested. Two rules say the same thing.
    """
    if '(' in expr or ')' in expr:
        raise ValueError(f'parentheses are not supported, write two rules: {expr!r}')
    out = []
    for alternative in expr.split('|'):
        terms = []
        for term in alternative.split('+'):
            key, sep, value = term.strip().partition('=')
            if not sep:
                raise ValueError(f'term without a value: {term!r} in {expr!r}')
            terms.append((key.strip(), value.strip()))
        out.append(terms)
    return out


class Categories:
    """The category tree, flattened to what classification needs.

    `importance` comes from model/importance.yaml and is inherited down the
    tree from the nearest listed node, and `ancestors` is precomputed
    because every search row stores a category together with all of its
    ancestors -- that is what makes a parent query
    (`categories @> ARRAY['cat_geography_water']`) the same indexed containment test as a
    leaf one, with no recursion in the database.
    """

    def __init__(self, tree: list[dict], importance: dict[str, int]):
        self.ancestors: dict[str, tuple[str, ...]] = {}
        self.importance: dict[str, int] = {}
        #: The node as written, for the names and search synonyms the query
        #: parser's term dictionary is generated from.
        self.nodes: dict[str, dict] = {}
        self._walk(tree, (), None, importance)
        unknown = sorted(set(importance) - set(self.ancestors))
        if unknown:
            raise ValueError(f'importance.yaml names unknown categories: {", ".join(unknown)}')

    def _walk(self, nodes: list[dict], parents: tuple[str, ...], inherited: int | None,
              importance: dict[str, int]) -> None:
        for node in nodes:
            node_id = node['id']
            if node_id in self.ancestors:
                raise ValueError(f'duplicate category id {node_id!r}')
            value = importance.get(node_id, inherited)
            if value is None:
                raise ValueError(f'importance.yaml: {node_id!r} has no value and no listed ancestor')
            if not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError(f'importance.yaml: {node_id!r} is {value!r}, not an integer 0-100')
            self.ancestors[node_id] = parents
            self.importance[node_id] = value
            self.nodes[node_id] = node
            self._walk(node.get('subs') or [], parents + (node_id,), value, importance)

    def expand(self, categories: list[str]) -> tuple[str, ...]:
        out: list[str] = []
        for category in categories:
            for value in (*self.ancestors[category], category):
                if value not in out:
                    out.append(value)
        return tuple(out)


class Classifier:
    def __init__(self, rules: list[Rule], bits: dict[tuple[str, str], int],
                 values: dict[str, set[str]], categories: Categories):
        self.rules = rules
        self._bit = bits
        self._values = values                     # key -> the values any rule mentions ('*' included)
        self.relevant_keys = frozenset(values)
        self.categories = categories
        self._by_trigger = self._index(rules)
        self._memo: dict[tuple[int, str], Result] = {}
        #: Every class a rule produces.
        self.classes = frozenset(rule.cls for rule in rules if rule.cls and rule.cls != NO_CLASS)

    @staticmethod
    def _index(rules: list[Rule]) -> dict[int, tuple[tuple[int, int], ...]]:
        """Index every mask by its rarest bit.

        Rarity is measured over the rule corpus rather than over real
        objects: it is available without a .pbf, and with 872 masks landing
        on 785 distinct triggers the lists are ~1 long either way.
        """
        frequency: Counter[int] = Counter()
        for rule in rules:
            for mask in rule.masks:
                frequency.update(_set_bits(mask))

        buckets: dict[int, list[tuple[int, int]]] = {}
        for index, rule in enumerate(rules):
            for mask in rule.masks:
                trigger = min(_set_bits(mask), key=lambda bit: (frequency[bit], bit))
                buckets.setdefault(trigger, []).append((mask, index))
        return {trigger: tuple(sorted(entries, key=lambda e: e[1]))
                for trigger, entries in buckets.items()}

    def tag_bits(self, tags: Mapping[str, str]) -> int:
        """The object's relevant tags as one integer. The hot path."""
        bits = 0
        bit, values = self._bit, self._values
        for key, value in tags.items():
            known = values.get(key)
            if known is None:
                continue
            index = bit.get((key, value))
            if index is not None:
                bits |= 1 << index
            if '*' in known:
                bits |= 1 << bit[(key, '*')]
        return bits

    def classify(self, bits: int, kind: str) -> Result:
        """Memoised on `(bits, kind)`.

        The geometry restriction is part of the key, not applied after:
        `amenity=hospital` is `landuse_hospital` as a polygon and
        `poi_hospital` as a point from one and the same tag set.
        """
        key = (bits, kind)
        cached = self._memo.get(key)
        if cached is None:
            cached = self._memo[key] = self._classify(bits, kind)
        return cached

    def _classify(self, bits: int, kind: str) -> Result:
        if not bits:
            return EMPTY

        matched: set[int] = set()
        remaining = bits
        while remaining:
            low = remaining & -remaining
            for mask, index in self._by_trigger.get(low.bit_length() - 1, ()):
                if bits & mask == mask:
                    matched.add(index)
            remaining ^= low

        cls = min_px = category = None
        categories: list[str] = []
        fallbacks: list[Rule] = []
        keys: set[str] = set()
        for index in sorted(matched):
            rule = self.rules[index]
            if rule.geometry is not None and rule.geometry != kind:
                continue
            if rule.fallback:
                fallbacks.append(rule)
                continue
            keys |= rule.keys
            if cls is None and rule.cls is not None:
                cls, min_px = rule.cls, rule.min_px
            if category is None:
                category = rule.category
            if rule.category not in categories:
                categories.append(rule.category)
        # `amenity=*` matches every amenity. It is the rule for the values no
        # other rule names, so it counts only where no rule on its key matched:
        # counted everywhere, it would put every restaurant into "Sonstiges"
        # too, and -- since it carries a POI class -- draw every bench
        # (`amenity=bench`, search-only) as a generic POI.
        for rule in fallbacks:
            if rule.keys & keys:
                continue
            if cls is None and rule.cls is not None:
                cls, min_px = rule.cls, rule.min_px
            if rule.category not in categories:
                categories.append(rule.category)
                category = category or rule.category

        if cls == NO_CLASS:
            cls = min_px = None
        if cls is None and not categories:
            return EMPTY
        return Result(cls, min_px, self.categories.expand(categories), category,
                      self.categories.importance[category] if category else None)


def _set_bits(mask: int) -> list[int]:
    out = []
    while mask:
        low = mask & -mask
        out.append(low.bit_length() - 1)
        mask ^= low
    return out


def compile_rules(rules: list[dict], categories: Categories) -> Classifier:
    bits: dict[tuple[str, str], int] = {}
    values: dict[str, set[str]] = {}
    compiled: list[Rule] = []

    for raw in rules:
        masks = []
        tags, geometry = split_geometry(raw['match'])
        alternatives = parse_match(tags)
        for alternative in alternatives:
            mask = 0
            for term in alternative:
                index = bits.get(term)
                if index is None:
                    index = bits[term] = len(bits)
                values.setdefault(term[0], set()).add(term[1])
                mask |= 1 << index
            masks.append(mask)

        category = raw['category']
        if category not in categories.ancestors:
            raise ValueError(f'rule names unknown category {category!r}: {raw["match"]!r}')
        fallback = len(alternatives) == 1 and len(alternatives[0]) == 1 and alternatives[0][0][1] == '*'
        compiled.append(Rule(tuple(masks), category, raw.get('class'),
                             geometry, raw.get('min_px'), fallback,
                             frozenset(key for alternative in alternatives for key, _ in alternative)))

    return Classifier(compiled, bits, values, categories)


def load_rules(model_dir: Path) -> list[dict]:
    """The hand-written rules, then the generated ones: the order they are evaluated in."""
    return (yaml.safe_load((model_dir / 'classifier.yaml').read_text()) or []) + \
        yaml.safe_load((model_dir / 'generated' / 'classifier.yaml').read_text())


def load_categories(model_dir: Path) -> list[dict]:
    """The deep category tree tools/gen_classifier.py writes."""
    return yaml.safe_load((model_dir / 'generated' / 'categories.yaml').read_text())


def load_importance(model_dir: Path) -> dict[str, int]:
    return yaml.safe_load((model_dir / 'importance.yaml').read_text()) or {}


def load(model_dir: Path) -> Classifier:
    return compile_rules(load_rules(model_dir),
                         Categories(load_categories(model_dir), load_importance(model_dir)))
