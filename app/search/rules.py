"""The phrase search's rules: quasi-SQL from model/search_rules.yaml,
compiled per reading of the query.

A rule reads like the condition it is -- `category = query.category AND
location IN query.place` -- and names the parts of the query it needs. The
parser (search/phrase.py) splits a query into readings, each a set of parts;
a rule runs once for every reading that has exactly its parts, and each run
is one statement built by `rank.build_sql`, the name mode's builder.

GRAMMAR

    rule   := clause ('AND' clause)* ['ORDER BY' 'distance' '(' 'location' ',' 'query.place' ')']
    clause := atom | '(' atom ('OR' atom)* ')'
    atom   := prop op 'query.'part

The atoms are a closed set (`ATOMS`), each with its SQL below; a rule that
uses anything else is refused when the file is loaded, not when a query
first reaches it.

HOW A RULE BECOMES A STATEMENT

Every atom is a list of alternatives, each a condition on `o`. `name
LIKE` contributes the fuzzy name search's own probes (`name.fuzzy_plan`),
each on its own index, and the rule's candidate probes are those, one per
LIKE alternative, each ANDed with the rule's other clauses; an OR among
the other atoms stays an OR inside the probe. Not a probe per combination:
each LIKE probe is a trigram index scan, "restaurant wilstedt" 160 ms of
one on de, and repeating it for every alternative of the place
beside it cost 1.8 s. The LIKE rule scores by the fuzzy name search's
score; every other rule like the name mode, importance and view.

A LIKE rule with anything else in it runs strict, at
`ranking.phrase_strict_min_score` and `phrase_strict_best_share` of its best
row (`phrase._run`): relaxed, "hauptstrasse" in Bargteheide
matched every other "...strasse" there. A LIKE rule on its own (`name LIKE
query.text`) runs the relaxation cascade.

Rules whose atoms are all `address.*` run on the address table, through the
address mode's matcher (`address.build_sql`).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from lib import text
from search import name as name_mode
from search import point as point_mode
from search import rank

#: (property, operator, query part).
ATOMS = frozenset({
    ('name', '=', 'text'),
    ('name', '=', 'name'),
    ('name', 'LIKE', 'text'),
    ('name', 'LIKE', 'name'),
    ('category', '=', 'text'),
    ('category', '=', 'category'),
    ('location', 'IN', 'place'),
    ('location', 'NEAR', 'place'),
    ('location', 'NEAR', 'street'),
    ('location', 'NEAR', 'location'),
    ('address.street', '=', 'street'),
    ('address.street', 'LIKE', 'street'),
    ('address.housenumber', '=', 'housenumber'),
    ('address.city', '=', 'place'),
    ('address.postcode', '=', 'postcode'),
})

#: The parts a reading can have. `text` and `location` are the request's
#: own and always there; the address parts belong to the address readings.
READING_PARTS = frozenset({'name', 'category', 'place', 'street'})

ORDER_DISTANCE_PLACE = 'distance(location, query.place)'

#: A reading's place as a condition on `o`. The path holds the places with
#: a border (importer/places.py); a border that is no administrative area
#: -- a region -- is on no path, and is tested by containment instead.
IN_PATH = 'o.id_places && %(r_place_ids)s::int[]'

#: No `&&` box in front: a region's box is most of a Land, and with it the
#: planner scans the geometry index for everything in the box before the
#: rule's other part narrows anything. Without it the other part drives,
#: and the polygon is tested on what it found.
IN_AREA = 'ST_Contains((SELECT p.geom_polygon FROM {{objects}} p WHERE p.id = %(r_area_{i})s), o.geom_center)'

#: The objects within the radius of a place mapped as a node only,
#: collected first. As a condition beside `name LIKE`, a plain `ST_DWithin`
#: lost to the trigram index: "restaurant" was looked up all over Germany
#: and then tested for the hamlet, 5.5 s on de. As an id array the
#: few objects around the hamlet are fetched by key and then tested.
NEAR_PLACE_CTE = 'near_place AS MATERIALIZED ({union})'
NEAR_POINT = ('SELECT n.id FROM {{objects}} n WHERE ST_DWithin(n.geom_center::geography,'
              ' ST_SetSRID(ST_MakePoint(%(r_lon_{i})s, %(r_lat_{i})s), 4326)::geography, %(r_radius_{i})s)')
NEAR_PLACE = 'o.id = ANY(ARRAY(SELECT id FROM near_place))'

#: The streets of that name nearest the request's location: the nearest
#: row, and every row of the name within `near_street_group_m` of it, since
#: a merged street is one row per connected piece. Not every street of the
#: name: on de that was everything along every Hauptstraße, 6 to
#: 16 s.
NEAR_STREET_CTE = """near_street AS MATERIALIZED (
        SELECT s.geom_line FROM {objects} s, (
            SELECT t.geom_line AS g FROM {objects} t
            WHERE t.search_name = %(r_street)s AND t.geom_line IS NOT NULL
            ORDER BY t.geom_line <-> ST_SetSRID(ST_MakePoint(%(r_loc_lon)s, %(r_loc_lat)s), 4326)
            LIMIT 1) nearest
        WHERE s.search_name = %(r_street)s AND s.geom_line IS NOT NULL
          AND s.geom_line && ST_Expand(nearest.g, %(r_group_dlon)s, %(r_group_dlat)s)
          AND ST_DWithin(s.geom_line::geography, nearest.g::geography, %(near_street_group_m)s)
    )"""
NEAR_STREET = ('o.id = ANY(ARRAY(SELECT n.id FROM near_street s JOIN {objects} n'
               ' ON ST_DWithin(n.geom_center::geography, s.geom_line::geography,'
               ' %(near_street_distance_m)s)))')

#: An object is on the street when an address on it is: the address rows
#: of its own OSM ids, by the btree on `osm_id`. Driven from the object, so
#: a name narrows it to a handful of probes; collecting the street's
#: addresses first read every Hauptstraße address in Germany, 131 s cold.
ON_STREET = ('EXISTS (SELECT 1 FROM {addresses} a'
             ' WHERE a.osm_id = ANY(o.osm_ids) AND a.search_street = %(r_street)s)')

NAME_EQUALS = 'o.search_name = ANY(%(r_names)s)'
CATEGORY_EQUALS = 'o.categories @> %(r_category)s'


class RuleError(ValueError):
    """A rule the grammar or the atom set does not allow."""


@dataclass(frozen=True, slots=True)
class Atom:
    prop: str
    op: str
    part: str


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    source: str
    clauses: tuple[tuple[Atom, ...], ...]
    order: str | None = None

    @property
    def atoms(self) -> tuple[Atom, ...]:
        return tuple(atom for clause in self.clauses for atom in clause)

    @property
    def on_addresses(self) -> bool:
        return all(atom.prop.startswith('address.') for atom in self.atoms)

    @property
    def on_text(self) -> bool:
        return any(atom.part == 'text' for atom in self.atoms)

    @property
    def parts(self) -> frozenset[str]:
        """The reading parts the rule needs, exactly; the place of an ORDER
        BY is one of them."""
        parts = {atom.part for atom in self.atoms}
        if self.order == ORDER_DISTANCE_PLACE:
            parts.add('place')
        return frozenset(parts) & READING_PARTS

    @property
    def like(self) -> Atom | None:
        return next((atom for atom in self.atoms if atom.op == 'LIKE'), None)

    @property
    def street_like(self) -> bool:
        return any(atom.prop == 'address.street' and atom.op == 'LIKE' for atom in self.atoms)


@dataclass(frozen=True, slots=True)
class Step:
    relevance: int
    rules: tuple[Rule, ...]
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class Place:
    """A place name in the query: every place called that."""

    name: str
    #: The ones with a border, for the path test.
    ids: tuple[int, ...]
    #: The ones with a border that is no administrative area, which no path
    #: holds, for a containment test.
    area_ids: tuple[int, ...]
    #: The ones mapped as a node only, as (lon, lat, radius in metres). A node
    #: inside a border of its own name is not one: Kiel's node would add
    #: everything within 10 km of it.
    points: tuple[tuple[float, float, float], ...]
    #: Where distance from the place is measured: the first with a border.
    centre: tuple[float, float]


@dataclass(frozen=True, slots=True)
class Reading:
    """One way of splitting the query into parts. A part is None when
    this reading does not have it."""

    text: str
    name: str | None = None
    category: str | None = None
    #: The query words the category was read from.
    term: str | None = None
    place: Place | None = None
    street: str | None = None
    addresses: tuple = ()

    @property
    def parts(self) -> frozenset[str]:
        return frozenset(part for part in READING_PARTS if getattr(self, part) is not None)

    def bindings(self) -> dict:
        """The parts as the response's `interpretation` shows them."""
        out = {}
        if self.name is not None:
            out['name'] = self.name
        if self.category is not None:
            out['category'] = self.category
            out['term'] = self.term
        if self.place is not None:
            out['place'] = self.place.name
        if self.street is not None:
            out['street'] = self.street
        return out


@dataclass(frozen=True, slots=True)
class Compiled:
    """A rule run on a reading: the plan, the request to build it with, and
    how to run it."""

    plan: rank.Plan
    req: object
    min_score: float
    relax: bool = False


# --- the grammar ---------------------------------------------------------

_TOKEN = r"\(|\)|,|=|[\w.]+"


def parse_rule(rule_id: str, source: str) -> Rule:
    """One rule's quasi-SQL, or RuleError."""
    tokens = re.findall(_TOKEN, source)
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def take(expected: str | None = None) -> str:
        nonlocal pos
        token = peek()
        if token is None or (expected is not None and token.upper() != expected):
            raise RuleError(f'{rule_id}: expected {expected or "a token"} at {token!r} in {source!r}')
        pos += 1
        return token

    def atom() -> Atom:
        prop = take()
        op = take().upper()
        operand = take()
        if not operand.startswith('query.'):
            raise RuleError(f'{rule_id}: {operand!r} is not a query part')
        found = Atom(prop, op, operand.removeprefix('query.'))
        if (found.prop, found.op, found.part) not in ATOMS:
            raise RuleError(f'{rule_id}: unknown atom {prop} {op} {operand}')
        return found

    def clause() -> tuple[Atom, ...]:
        if peek() != '(':
            return (atom(),)
        take('(')
        atoms = [atom()]
        while peek() and peek().upper() == 'OR':
            take('OR')
            atoms.append(atom())
        take(')')
        return tuple(atoms)

    clauses = [clause()]
    while peek() and peek().upper() == 'AND':
        take('AND')
        clauses.append(clause())

    order = None
    if peek() and peek().upper() == 'ORDER':
        take('ORDER')
        take('BY')
        order = ''.join(tokens[pos:]).replace(',', ', ')
        if order != ORDER_DISTANCE_PLACE:
            raise RuleError(f'{rule_id}: unknown order {order!r}')
        pos = len(tokens)
    if peek() is not None:
        raise RuleError(f'{rule_id}: unexpected {peek()!r} in {source!r}')

    rule = Rule(id=rule_id, source=' '.join(source.split()), clauses=tuple(clauses), order=order)
    _check(rule)
    return rule


def _check(rule: Rule) -> None:
    """What the grammar allows but no statement can run."""
    atoms = rule.atoms
    if rule.on_addresses:
        return
    if any(a.prop.startswith('address.') and (a.prop, a.op) != ('address.street', '=') for a in atoms):
        raise RuleError(f'{rule.id}: an object rule takes only address.street = query.street')
    if rule.on_text and rule.parts:
        raise RuleError(f'{rule.id}: query.text is the whole query and takes no other part')
    if sum(a.op == 'LIKE' for a in atoms) > 1:
        raise RuleError(f'{rule.id}: one LIKE per rule')


# --- loading -------------------------------------------------------------

_steps: tuple[Step, ...] | None = None


def steps(model_dir: Path | None = None) -> tuple[Step, ...]:
    """The steps of model/search_rules.yaml, read and checked once."""
    global _steps
    if _steps is None or model_dir is not None:
        directory = model_dir or _default_model_dir()
        loaded = load(yaml.safe_load((directory / 'search_rules.yaml').read_text()))
        if model_dir is None:
            _steps = loaded
        return loaded
    return _steps


def load(document: dict) -> tuple[Step, ...]:
    out = []
    seen = set()
    for step in document['steps']:
        rules = []
        for rule_id, source in step['rules'].items():
            if rule_id in seen:
                raise RuleError(f'{rule_id}: defined twice')
            seen.add(rule_id)
            rules.append(parse_rule(rule_id, source))
        out.append(Step(relevance=int(step['relevance']), rules=tuple(rules),
                        enabled=bool(step.get('enabled', True))))
    return tuple(out)


def _default_model_dir() -> Path:
    from importer.run import MODEL
    return MODEL


_parameters: dict | None = None


def parameters() -> dict:
    """`near_street_distance_m` and `near_street_group_m` from parameters.yaml."""
    global _parameters
    if _parameters is None:
        values = yaml.safe_load((_default_model_dir() / 'parameters.yaml').read_text())
        _parameters = {key: float(values[key])
                       for key in ('near_street_distance_m', 'near_street_group_m')}
    return _parameters


# --- compiling -----------------------------------------------------------

def compile_rule(rule: Rule, reading: Reading, req, limit: int,
                 w: rank.Weights) -> Compiled | None:
    """The statement for an object rule on a reading, or None when a part
    cannot match anything (a place with no border for `IN`, say)."""
    plan_req = req.for_rule(text='', categories=(), page=0, limit=limit)
    params: dict = dict(parameters())
    ctes: list[str] = []
    clauses: list[list[str]] = []
    like_plan = None

    for clause in rule.clauses:
        alternatives: list[str] = []
        for atom in clause:
            if atom.op == 'LIKE':
                value = reading.text if atom.part == 'text' else reading.name
                like_plan = name_mode.fuzzy_plan(plan_req.for_rule(text=value),
                                                 narrowed=len(rule.clauses) > 1)
                alternatives += like_plan.probes
                params.update(like_plan.params)
            elif atom == Atom('location', 'NEAR', 'location'):
                # An order, not a condition: the nearest first, inside
                # whatever view the request itself carries.
                if req.sort == 'score' and req.point is not None:
                    plan_req = plan_req.for_rule(sort='distance')
                alternatives.append('TRUE')
            else:
                alternatives += _conditions(atom, reading, req, params, ctes)
        if not alternatives:
            return None
        if len(alternatives) > 1 and not any(a.op == 'LIKE' for a in clause):
            alternatives = ['(' + ' OR '.join(alternatives) + ')']
        clauses.append(alternatives)

    probes = tuple(' AND '.join(c for c in combination if c != 'TRUE') or 'TRUE'
                   for combination in itertools.product(*clauses))
    if rule.order == ORDER_DISTANCE_PLACE or (reading.place and req.point is None):
        # Equals nearest the place first -- the restaurants of Kiel from its
        # centre out -- unless the request has a point of its own.
        plan_req = plan_req.for_rule(near=reading.place.centre)

    if like_plan is not None:
        score = like_plan.score
        strict = len(rule.clauses) > 1
        min_score = w.phrase_strict_min_score if strict else w.min_score
        return Compiled(rank.Plan(probes=probes, score=score, params=params, ctes=tuple(ctes)),
                        plan_req, min_score, relax=not strict)
    score = f'1.0 + {rank.inside_view_term(req.spatial)}'
    return Compiled(rank.Plan(probes=probes, score=score, params=params, ctes=tuple(ctes)),
                    plan_req, w.min_score)


def _conditions(atom: Atom, reading: Reading, req, params: dict, ctes: list[str]) -> list[str]:
    """One atom's alternatives, its parameters added to `params` and the
    CTEs it reads to `ctes`."""
    if atom.prop == 'name':
        value = reading.text if atom.part == 'text' else reading.name
        name = text.expand_street(value)
        if not name:
            return []
        params['r_names'] = [name]
        if atom.part == 'name' and reading.place is not None:
            # "Hauptbahnhof Kiel" is the station mapped as "Kiel Hauptbahnhof":
            # a name in a place is also the name with the place on either side.
            # No bonus for it: bus stops are named so too ("Balzers
            # Rheinstrasse"), and would outrank the street.
            place = text.expand_street(reading.place.name)
            params['r_names'] += [f'{place} {name}', f'{name} {place}']
        return [NAME_EQUALS]

    if atom.prop == 'category':
        params['r_category'] = [reading.category]
        return [CATEGORY_EQUALS]

    if atom == Atom('location', 'IN', 'place'):
        place = reading.place
        out = []
        if place.ids:
            params['r_place_ids'] = list(place.ids)
            out.append(IN_PATH)
        for i, area_id in enumerate(place.area_ids):
            params[f'r_area_{i}'] = area_id
            out.append(IN_AREA.format(i=i))
        return out

    if atom == Atom('location', 'NEAR', 'place'):
        points = reading.place.points
        if not points:
            return []
        for i, (lon, lat, radius) in enumerate(points):
            params.update({f'r_lon_{i}': lon, f'r_lat_{i}': lat, f'r_radius_{i}': radius})
        ctes.append(NEAR_PLACE_CTE.format(
            union=' UNION '.join(NEAR_POINT.format(i=i) for i in range(len(points)))))
        return [NEAR_PLACE]

    if atom == Atom('location', 'NEAR', 'street'):
        # Nearest to the request's location; without one there is no
        # telling which Hauptstraße is meant.
        if req.point is None:
            return []
        params['r_street'] = reading.street
        params['r_loc_lon'], params['r_loc_lat'] = req.point
        # The box in front of the metric test, so that the geography
        # distance is computed for the few rows around the nearest street,
        # not for all 10 000 Hauptstraßen: 830 ms on de.
        params['r_group_dlon'], params['r_group_dlat'] = point_mode.degrees_for(
            params['near_street_group_m'], req.point[1])
        ctes.append(NEAR_STREET_CTE)
        return [NEAR_STREET]

    if atom == Atom('address.street', '=', 'street'):
        params['r_street'] = reading.street
        return [ON_STREET]

    raise RuleError(f'no SQL for {atom}')
