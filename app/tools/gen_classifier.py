"""Generate model/generated/categories.yaml and model/generated/classifier.yaml.

Sources:

- model/categories.yaml, hand-written: the category tree, and which iD
  presets map into which of its nodes (DESIGN.md "The category tree").
- iD tagging schema (openstreetmap/id-tagging-schema, npm dist): the presets
  are the de-facto definition of "what kind of thing is this" -- one entry per
  feature type with its tags, allowed geometry, a folder-like hierarchy
  (`amenity/cafe/bubble_tea`) and translated names and search terms.
- OpenMapTiles layer definitions: the `class` value mappings of the poi,
  landcover, landuse, transportation, water, waterway, place and aeroway
  layers, a proven grouping of tag values into render classes.

The generated tree is the hand-written one made deep: every preset a node
claims becomes a child of that node, nested the way iD nests them, with its
names and search terms from iD -- except the node's `main` preset, or its
only one, which is the node itself. The deep tree keeps search precise -- a search for "Metzger"
finds butchers, not the whole grocery group they are filed under -- while
the tree anyone edits stays short.

The classifier rules are one per preset, most specific first, with the
preset's node as the category. The render class comes from OpenMapTiles
where the preset's tags fall into one of its classes, otherwise the rule is
search-only. A POI class is one per second-level category
(`cls_poi_food`), and only below a node marked `marker: true`; POI kinds
that need their own class get it from a hand-written rule in
model/classifier.yaml, which the importer reads before these.

    python tools/gen_classifier.py            # from /app; writes model/generated/

Downloads are cached in tools/.cache. Both outputs are generated and never
edited by hand.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

ID_VERSION = '7.2.0'
ID_BASE = f'https://unpkg.com/@openstreetmap/id-tagging-schema@{ID_VERSION}/dist/'
OMT_VERSION = 'v3.15'
OMT_BASE = f'https://raw.githubusercontent.com/openmaptiles/openmaptiles/{OMT_VERSION}/layers/'
OMT_LAYERS = ['poi', 'landcover', 'landuse', 'transportation', 'water', 'waterway', 'place', 'aeroway']

LANGUAGES = ['de', 'en']

# Preset ids that are not kinds of object: geometry types, relation types,
# templates, address and lifecycle prefixes. Everything else iD marks
# searchable is a candidate, and the tree decides where it goes.
NON_OBJECT = ('@templates', 'type', 'area', 'line', 'point', 'vertex', 'relation', 'addr', 'address',
              'disused', 'demolished', 'building_point', 'ford_line')

# Presets iD marks unsearchable (legacy tagging it only adds alongside the
# public_transport form) that still occur on their own in the data. The tree
# lists them explicitly.
FORCE_KEEP = ('highway/bus_stop', 'railway/tram_stop')

# Only to choose the primary tag of a multi-tag preset for its bare-tag rule
# (add_base_rules); which presets count is decided by the tree.
PRIMARY_KEYS = (
    'amenity', 'shop', 'tourism', 'leisure', 'natural', 'landuse', 'highway', 'railway',
    'waterway', 'place', 'building', 'man_made', 'historic', 'office', 'craft', 'healthcare',
    'public_transport', 'aeroway', 'aerialway', 'education', 'power', 'boundary', 'military',
    'barrier', 'emergency',
)

REGIONS = {'Planet', '001', 'Q46', 'eu', 'de'}

GEOMETRY = {'point': 'point', 'vertex': 'point', 'line': 'line', 'area': 'polygon'}
KINDS = ('point', 'line', 'polygon')

APP = Path(__file__).resolve().parent.parent
MODEL = APP / 'model'
STYLES = APP / 'styles'

RAIL_CLASSES = {
    'rail': ['rail', 'narrow_gauge', 'preserved', 'funicular'],
    'transit': ['subway', 'light_rail', 'tram', 'monorail'],
}


#: Assigned by the water import; no rule produces it.
WATER_CLASS = 'cls_ocean'


def fetch(url: str, cache: Path) -> Path:
    target = cache / re.sub(r'[^\w.-]+', '_', url.split('//', 1)[1])
    if not target.exists():
        print(f'fetching {url}', file=sys.stderr)
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:
            target.write_bytes(r.read())
    return target


def load_sources(cache: Path) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    presets = json.loads(fetch(ID_BASE + 'presets.json', cache).read_text())
    names = {}
    for lang in LANGUAGES:
        data = json.loads(fetch(ID_BASE + f'translations/{lang}.json', cache).read_text())
        names[lang] = data[lang]['presets']['presets']
    omt = {}
    for layer in OMT_LAYERS:
        omt[layer] = yaml.safe_load(fetch(OMT_BASE + f'{layer}/{layer}.yaml', cache).read_text())
    return presets, names, omt


def wanted(preset_id: str, preset: dict) -> bool:
    if preset.get('searchable') is False and preset_id not in FORCE_KEEP:
        return False
    if preset_id.split('/')[0] in NON_OBJECT:
        return False
    include = (preset.get('locationSet') or {}).get('include')
    if include and not set(include) & REGIONS:
        return False
    tags = preset.get('tags', {})
    return bool(tags) and not any(k.startswith('@') for k in tags)


def clean_name(name: str) -> str:
    return name.rstrip('. …').strip()


def segment(text: str) -> str:
    """A preset path part as an id segment: `multi-storey` -> `multistorey`."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def value_list(spec) -> list[str]:
    if spec is None:
        return []
    if isinstance(spec, str):
        return [spec]
    return list(spec)


def build_class_lookup(omt: dict) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """(key, value) -> render class, from the OpenMapTiles class mappings.

    Two tables: `area` for polygon classes (landcover, landuse, water) and
    `lookup` for everything else. A tag that is in both (`amenity=school`:
    a school ground as an area, a school as a POI) yields two rules,
    restricted by geometry. Classes here are unprefixed; `cls_` is added
    when a rule is written."""
    lookup: dict[tuple[str, str], str] = {}
    area: dict[tuple[str, str], str] = {}

    poi_keys = ['amenity', 'shop', 'tourism', 'leisure', 'historic', 'office', 'railway',
                'aerialway', 'sport', 'landuse', 'barrier', 'waterway', 'building', 'highway']
    for cls, spec in omt['poi']['layer']['fields']['class']['values'].items():
        entries = spec if isinstance(spec, list) else [spec]
        for entry in entries:
            if '__AND__' in entry:
                sub = entry['__AND__']
                keys = value_list(sub.get('mapping_key')) or poi_keys
                values = value_list(sub.get('subclass'))
            else:
                keys, values = poi_keys, value_list(entry.get('subclass'))
            for key in keys:
                for value in values:
                    lookup.setdefault((key, value), f'poi_{cls}')

    for cls, spec in omt['landcover']['layer']['fields']['class']['values'].items():
        for value in value_list(spec.get('subclass')):
            for key in ('natural', 'landuse', 'leisure', 'wetland'):
                area[(key, value)] = f'landcover_{cls}'

    for value in omt['landuse']['layer']['fields']['class']['values']:
        for key in ('landuse', 'amenity', 'leisure', 'tourism'):
            area.setdefault((key, value), f'landuse_{value}')
    for key, value in list(lookup):
        if lookup[(key, value)] == 'poi_cemetery':
            area.setdefault((key, value), 'landuse_cemetery')

    for cls, spec in omt['transportation']['layer']['fields']['class']['values'].items():
        if 'construction' in cls:
            continue
        for key, values in spec.items():
            for value in value_list(values):
                lookup[(key, value)] = f'road_{cls}' if key == 'highway' else f'{key}_{cls}'
    for cls, values in RAIL_CLASSES.items():
        for value in values:
            lookup[('railway', value)] = f'{cls}_{value}'
    lookup[('route', 'ferry')] = 'ferry'

    for cls, spec in omt['water']['layer']['fields']['class']['values'].items():
        for key, values in (spec or {}).items():
            for value in value_list(values):
                area[(key, value)] = f'water_{cls}'
    area[('natural', 'water')] = 'water_lake'
    for value in omt['waterway']['layer']['fields']['class']['values']:
        lookup[('waterway', value)] = f'waterway_{value}'
    for value in omt['place']['layer']['fields']['class']['values']:
        lookup[('place', value)] = f'place_{value}'
    for value in omt['aeroway']['layer']['fields']['class']['values']:
        lookup[('aeroway', value)] = f'aeroway_{value}'
    area[('building', '*')] = 'building'
    return lookup, area


# OpenMapTiles' rule for a POI value that no grouped class lists: the class is the
# value itself. Applied per key so a key that OMT does not treat as POI at all
# (craft, healthcare, office) is still a POI. Which POI class it gets is decided
# by the category (poi_class), so only "is it a POI" matters here.
POI_VALUE_KEYS = ('amenity', 'shop', 'tourism', 'leisure', 'historic')
POI_KEYS = ('craft', 'healthcare', 'office')


def render_class_area(tags: dict, area: dict) -> str | None:
    for key, value in tags.items():
        if (key, value) in area:
            return area[(key, value)]
    for key, value in tags.items():
        if (key, '*') in area:
            return area[(key, '*')]
    return None


def render_class(tags: dict, lookup: dict) -> str | None:
    for key, value in tags.items():
        if (key, value) in lookup:
            return lookup[(key, value)]
    for key, value in tags.items():
        if (key, '*') in lookup:
            return lookup[(key, '*')]
    for key, value in tags.items():
        if key in POI_VALUE_KEYS and value != '*':
            return f'poi_{value}'
        if key in POI_KEYS:
            return f'poi_{key}'
    return None


def legacy_tags(preset: dict) -> dict:
    """The POI tag iD adds with a preset but does not match on.

    iD 7 moved the education presets to `education=*` and the bus and ferry
    stations to `public_transport=station`, and keeps the tag everyone maps
    -- `amenity=kindergarten`, `amenity=bus_station` -- only in `addTags`.
    Matched on `tags` alone, 1 022 kindergartens and 869 schools on de_sh
    reached no rule but `amenity=*` and were drawn as "other". Only where
    `tags` carry no POI key of their own: a clinic's added `healthcare=clinic`
    is a second tag for something `amenity=clinic` already matches.
    """
    tags, added = preset['tags'], preset.get('addTags') or {}
    if any(key in POI_VALUE_KEYS + POI_KEYS for key in tags):
        return {}
    return {key: value for key, value in added.items()
            if key in POI_VALUE_KEYS + POI_KEYS and key not in tags and value != '*'}


def poi_class(category: str) -> str:
    """One POI class per second-level category: `cat_poi_food_cafe` -> `poi_food`.

    Segments never contain `_`, so the second level is the third part."""
    return 'poi_' + category.split('_')[2]


def match_expression(tags: dict) -> str:
    return ' + '.join(f'{k}={v}' for k, v in tags.items())


# --- the tree --------------------------------------------------------------

class Tree:
    """The hand-written tree, flattened: nodes, parents, claimed presets."""

    def __init__(self, roots: list[dict]):
        self.roots = roots
        self.nodes: dict[str, dict] = {}
        self.parent: dict[str, str | None] = {}
        self.owner: dict[str, str] = {}          # preset pattern -> node id
        self.marker: dict[str, bool] = {}
        self._walk(roots, None, False)

    def _walk(self, nodes: list[dict], parent: str | None, marker: bool) -> None:
        for node in nodes:
            node_id = node['id']
            if not re.fullmatch(r'cat(_[a-z0-9]+)+', node_id):
                raise SystemExit(f'categories.yaml: {node_id!r} is not cat_<segment>_...')
            if parent is not None and node_id.rsplit('_', 1)[0] != parent:
                raise SystemExit(f'categories.yaml: {node_id!r} is not {parent!r} plus one segment')
            if node_id in self.nodes:
                raise SystemExit(f'categories.yaml: duplicate id {node_id!r}')
            for field in ('name_en', 'name_de'):
                if not node.get(field):
                    raise SystemExit(f'categories.yaml: {node_id!r} has no {field}')
            self.nodes[node_id] = node
            self.parent[node_id] = parent
            self.marker[node_id] = bool(node.get('marker', marker))
            main = node.get('main')
            if main is not None and main not in (node.get('presets') or []):
                raise SystemExit(f'categories.yaml: {node_id!r} main {main!r} is not one of its presets')
            for pattern in node.get('presets') or []:
                if pattern in self.owner:
                    raise SystemExit(f'categories.yaml: preset {pattern!r} is listed at '
                                     f'{self.owner[pattern]!r} and {node_id!r}')
                self.owner[pattern] = node_id
            self._walk(node.get('subs') or [], node_id, self.marker[node_id])

    def node_for(self, preset_id: str) -> str | None:
        """The node whose longest listed pattern covers this preset."""
        best = None
        for pattern in self.owner:
            if (preset_id == pattern or preset_id.startswith(pattern + '/')) and (
                    best is None or len(pattern) > len(best)):
                best = pattern
        return self.owner[best] if best else None


def assign(tree: Tree, presets: dict) -> tuple[dict[str, str], list[str]]:
    """{preset id: hand-written node} for every kept preset, and the unclaimed ones."""
    for pattern in tree.owner:
        if not any(pid == pattern or pid.startswith(pattern + '/') for pid in presets):
            raise SystemExit(f'categories.yaml: no iD {ID_VERSION} preset {pattern!r}')
    kept = {pid for pid, preset in presets.items() if wanted(pid, preset)}
    # A preset listed by its exact id is kept even if iD would not keep it.
    kept |= {pattern for pattern in tree.owner if pattern in presets and presets[pattern].get('tags')}
    assigned, unclaimed = {}, []
    for pid in sorted(kept):
        node = tree.node_for(pid)
        if node is None:
            unclaimed.append(pid)
        else:
            assigned[pid] = node
    return assigned, unclaimed


def deepen(tree: Tree, assigned: dict[str, str], names: dict) -> tuple[list[dict], dict[str, str]]:
    """The deep tree, and {preset id: its category}."""
    by_node: dict[str, list[str]] = {}
    for pid, node in assigned.items():
        by_node.setdefault(node, []).append(pid)

    category: dict[str, str] = {}
    generated: dict[str, list[dict]] = {}        # parent id -> generated child nodes
    own_terms: dict[str, dict[str, list[str]]] = {}

    def preset_names(pid: str) -> dict[str, str]:
        return {lang: clean_name(names[lang].get(pid, {}).get('name', pid)) for lang in LANGUAGES}

    def preset_terms(pid: str) -> dict[str, list[str]]:
        return {lang: list(names[lang].get(pid, {}).get('terms') or []) for lang in LANGUAGES}

    for node_id, pids in by_node.items():
        pids.sort(key=lambda p: (p.count('/'), p))
        listed = tree.nodes[node_id].get('presets') or []
        # The preset that is the node itself: its objects are filed at the
        # node. Without it a node whose presets include the thing it is named
        # after would have a child that meant the same (`..._river_waterwayriver`).
        single = listed[0] if len(listed) == 1 else tree.nodes[node_id].get('main')

        parent_of: dict[str, str] = {}           # preset -> preset or '' (the node itself)
        for pid in pids:
            if pid == single:
                continue
            up, parent = pid, ''
            while '/' in up:
                up = up.rsplit('/', 1)[0]
                if up in pids:
                    parent = '' if up == single else up
                    break
            parent_of[pid] = parent

        if single in pids:
            category[single] = node_id
            own_terms[node_id] = {'name': preset_names(single), 'terms': preset_terms(single)}

        taken = {child['id'] for child in tree.nodes[node_id].get('subs') or []}
        pending = [''] + [pid for pid in pids if pid in parent_of]
        for current in pending:
            parent_id = node_id if current == '' else category[current]
            children = [pid for pid, parent in parent_of.items() if parent == current]
            for pid, seg in _segments(children, parent_id, taken).items():
                child_id = f'{parent_id}_{seg}'
                category[pid] = child_id
                node = {'id': child_id, **{f'name_{lang}': n for lang, n in preset_names(pid).items()}}
                for lang, terms in preset_terms(pid).items():
                    if terms:
                        node[f'terms_{lang}'] = list(dict.fromkeys(terms))
                generated.setdefault(parent_id, []).append(node)
                taken.add(child_id)

    def emit(nodes: list[dict]) -> list[dict]:
        out = []
        for node in nodes:
            entry = {'id': node['id'], 'name_de': node['name_de'], 'name_en': node['name_en']}
            extra = own_terms.get(node['id'])
            for lang in LANGUAGES:
                terms = list(node.get(f'terms_{lang}') or [])
                if extra:
                    terms += [extra['name'][lang].lower()] + extra['terms'][lang]
                terms = [t for t in dict.fromkeys(terms) if t != entry[f'name_{lang}'].lower()]
                if terms:
                    entry[f'terms_{lang}'] = terms
            subs = emit(node.get('subs') or []) + emit(generated.get(node['id'], []))
            if subs:
                entry['subs'] = subs
            out.append(entry)
        return out

    return emit(tree.roots), category


def _segments(children: list[str], parent_id: str, taken: set[str]) -> dict[str, str]:
    """An id segment per child preset, unique under `parent_id`.

    The last path part where that is unique; where two children share it
    (`highway/footway/crossing`, `highway/cycleway/crossing`) all of them
    take more of their path, so neither gets the short name by accident of
    order."""
    depth = {pid: 1 for pid in children}
    while True:
        seg = {pid: segment(''.join(pid.split('/')[-depth[pid]:])) for pid in children}
        counts: dict[str, int] = {}
        for value in seg.values():
            counts[value] = counts.get(value, 0) + 1
        clash = [pid for pid in children
                 if counts[seg[pid]] > 1 or f'{parent_id}_{seg[pid]}' in taken]
        if not clash:
            return seg
        grown = False
        for pid in clash:
            if depth[pid] < pid.count('/') + 1:
                depth[pid] += 1
                grown = True
        if not grown:
            raise SystemExit(f'cannot name {clash} uniquely under {parent_id!r}')


# --- the rules --------------------------------------------------------------

def build_rules(presets: dict, assigned: dict[str, str], category: dict[str, str], tree: Tree,
                lookups: tuple[dict, dict]) -> list[dict]:
    lookup, area = lookups
    rules = []
    # A legacy tag another preset matches as it is -- `leisure=marina`, which
    # the "marina without facilities" preset adds -- belongs to that preset;
    # and one two presets add (`amenity=bus_station`, bus and trolleybus
    # stations) to the first of them.
    matched_as_is = {tuple(sorted(presets[pid]['tags'].items())) for pid in assigned}
    legacy_seen: set[tuple] = set()
    for pid in sorted(assigned, key=lambda p: (p.count('/'), p)):
        preset = presets[pid]
        tags = preset['tags']
        legacy = legacy_tags(preset)
        legacy_key = tuple(sorted(legacy.items()))
        if legacy_key in matched_as_is or legacy_key in legacy_seen:
            legacy = {}
        legacy_seen.add(legacy_key)
        # The class follows from the legacy tag too: `education=school` says
        # nothing OpenMapTiles knows, `amenity=school` is a POI.
        class_tags = {**tags, **legacy}
        target = category[pid]
        root = len(tags) == 1 and next(iter(tags.values())) == '*'
        geometries = list(dict.fromkeys(GEOMETRY[g] for g in preset.get('geometry', []) if g in GEOMETRY))

        area_cls = render_class_area(class_tags, area) if 'polygon' in geometries or root else None
        other_cls = None
        if not root and ([g for g in geometries if g != 'polygon'] or not area_cls):
            other_cls = render_class(class_tags, lookup)
            if other_cls and other_cls.startswith('poi_'):
                other_cls = poi_class(target) if tree.marker[assigned[pid]] else None

        if root:
            # A bare `key=*` (`shop=*`, `building=*`) closes the list: it is the
            # rule for every value iD has no preset for, and counts only for an
            # object no other rule on its key matched (importer/rules.py). Its
            # class is an area class -- `building=yes`, 53 % of the buildings in
            # a German extract, is drawn by nothing else -- or, for a POI key
            # below a `marker` node, the POI class: an `amenity=` value iD does
            # not know is still a place someone is looking for, drawn with its
            # category's icon, the generic one.
            key = next(iter(tags))
            if not area_cls and tree.marker[assigned[pid]] and key in POI_VALUE_KEYS + POI_KEYS:
                variants = [(poi_class(target), None)]
            else:
                variants = [(area_cls, 'polygon' if area_cls else None)]
        elif area_cls and other_cls and set(geometries) > {'polygon'}:
            variants = [(area_cls, 'polygon')] + [(other_cls, g) for g in geometries if g != 'polygon']
        elif area_cls:
            variants = [(area_cls, 'polygon' if len(geometries) > 1 else None)]
        else:
            variants = [(other_cls, None)]
        for cls, geometry in variants:
            for matched in (tags, legacy) if legacy else (tags,):
                rule = {'match': match_expression(matched), 'category': target}
                if cls:
                    rule['class'] = cls
                if geometry:
                    rule['geometry'] = geometry
                elif len(geometries) == 1 and not root:
                    rule['geometry'] = geometries[0]
                rules.append((root, -len(tags), pid, rule))

    rules.sort(key=lambda r: r[:3])
    ordered = [r[3] for r in rules]
    specific = [r for r in ordered if not is_root(r)]
    roots = [r for r in ordered if is_root(r)]

    def base_category(key: str, value: str, group: list[dict]) -> str | None:
        own = category.get(f'{key}/{value}')
        if own:
            return own
        return common_ancestor([r['category'] for r in group])

    return prune_redundant(add_base_rules(specific, base_category) + roots)


def is_root(rule: dict) -> bool:
    conds = conditions(rule)
    return len(conds) == 1 and next(iter(conds))[1] == '*'


def common_ancestor(ids: list[str]) -> str | None:
    parts = [i.split('_') for i in ids]
    common = []
    for column in zip(*parts, strict=False):
        if len(set(column)) != 1:
            break
        common.append(column[0])
    return '_'.join(common) if len(common) >= 2 else None


def add_base_rules(rules: list[dict], base_category) -> list[dict]:
    """iD sometimes has presets only for refinements of a tag
    (`healthcare=dentist + healthcare:speciality=...`, `public_transport=platform
    + bus=yes`) and none for the bare tag. Add the bare-tag rule so an object
    carrying only the base tag still lands: its category the bare tag's own
    preset's where the tree has it, else the refinements' common ancestor;
    class and geometry only where every refinement agrees."""
    singles = {conditions(r) for r in rules if len(conditions(r)) == 1}
    derived: dict[tuple[str, str], list[dict]] = {}
    for rule in rules:
        conds = conditions(rule)
        if len(conds) < 2:
            continue
        candidates = [c for c in conds if c[0] in PRIMARY_KEYS and c[1] != '*']
        primary = min(candidates, key=lambda c: PRIMARY_KEYS.index(c[0])) if candidates else None
        if primary is None or frozenset([primary]) in singles:
            continue
        derived.setdefault(primary, []).append(rule)
    added = []
    for (key, value), group in sorted(derived.items()):
        target = base_category(key, value, group)
        if target is None:
            continue
        base = {'match': f'{key}={value}', 'category': target}
        for field in ('class', 'geometry'):
            values = {r.get(field) for r in group}
            if len(values) == 1 and values != {None}:
                base[field] = values.pop()
        added.append(base)
    return rules + added


def conditions(rule: dict) -> frozenset[tuple[str, str]]:
    return frozenset(tuple(t.strip().split('=', 1)) for t in rule['match'].split('+'))


def outputs(rule: dict) -> tuple:
    return tuple(rule.get(k) for k in ('category', 'class'))


def geometry_covers(general: dict, specific: dict) -> bool:
    return general.get('geometry') in (None, specific.get('geometry'))


def prune_redundant(rules: list[dict]) -> list[dict]:
    """Drop a rule when a more general one (a subset of its conditions, `*`
    accepted as any value, no geometry restriction or the same one) matches
    every object it matches and produces the same category and class."""
    def covers(general: frozenset, specific: frozenset) -> bool:
        specific_map = dict(specific)
        return all(k in specific_map and (v == '*' or specific_map[k] == v) for k, v in general)

    kept = []
    for rule in rules:
        conds = conditions(rule)
        redundant = any(
            other is not rule and outputs(other) == outputs(rule) and geometry_covers(other, rule)
            and conditions(other) != conds and covers(conditions(other), conds)
            for other in rules
        )
        if not redundant:
            kept.append(rule)
    return kept


def written(rule: dict) -> dict:
    """The rule as the files carry it: `cls_` on the class, the geometry as
    the last term of the match."""
    out = {'match': rule['match'] + (f' + {rule["geometry"]}' if rule.get('geometry') else ''),
           'category': rule['category']}
    if rule.get('class'):
        out['class'] = 'cls_' + rule['class']
    return out


# --- checks -----------------------------------------------------------------

def collect_ids(nodes: list[dict], out: set[str]) -> set[str]:
    for node in nodes:
        out.add(node['id'])
        collect_ids(node.get('subs') or [], out)
    return out


def contour_classes(model: Path) -> set[str]:
    """Assigned by the import's contours step, one per `contours.levels_m`
    (importer/elevation.py classes()); no rule produces them."""
    levels = yaml.safe_load((model / 'parameters.yaml').read_text())['contours']['levels_m']
    return {f'cls_contour_{int(m)}' for m in levels}


def check_classes(rules: list[dict], classes_path: Path, model: Path = MODEL) -> list[str]:
    """Warnings, both directions, between the rules and styles/classes.yaml.

    `manage.py compile-styles` refuses a style entry no rule produces; this says so
    earlier, before an import is run on a model the style cannot draw."""
    styled = {key.split()[0] for section, entries in yaml.safe_load(classes_path.read_text()).items()
              if section not in ('templates', 'defaults') for key in entries}
    # `none` says a rule decides there is no class; it is not one.
    produced = ({r['class'] for r in rules if r.get('class') not in (None, 'none')}
                | {WATER_CLASS} | contour_classes(model))
    warnings = [f'{cls!r} is classified but styles/classes.yaml does not style it'
                for cls in sorted(produced - styled)]
    warnings += [f'styles/classes.yaml styles {cls!r}, which no rule produces'
                 for cls in sorted(styled - produced)]
    return warnings


# --- output -----------------------------------------------------------------

class Dumper(yaml.SafeDumper):
    pass


def _represent_dict(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data, flow_style=False)


def _represent_list(dumper, data):
    flow = all(isinstance(v, str) for v in data)
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=flow)


Dumper.add_representer(dict, _represent_dict)
Dumper.add_representer(list, _represent_list)


RULE_KEYS = ['match', 'category', 'class']


def flow_scalar(value) -> str:
    text = str(value)
    if text == '' or any(c in text for c in ',[]{}#"\'') or ': ' in text or text[0] in '!&*?|>%@`-':
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return text


def dump_rules(rules: list[dict]) -> str:
    return ''.join('- {' + ', '.join(f'{k}: {flow_scalar(r[k])}' for k in RULE_KEYS if k in r) + '}\n' for r in rules)


def header(kind: str) -> str:
    return (f'# GENERATED by tools/gen_classifier.py -- NEVER EDIT BY HAND. The {kind} come from '
            'model/categories.yaml and the sources below; hand-written rules go into model/classifier.yaml.\n'
            f'# Sources: iD tagging schema {ID_VERSION} (presets, names, terms), OpenMapTiles {OMT_VERSION} '
            f'(class mappings). Generated {datetime.date.today()}.\n'
            f'#   {ID_BASE}presets.json, {ID_BASE}translations/<lang>.json (ISC, (c) iD contributors)\n'
            f'#   {OMT_BASE}<layer>/<layer>.yaml for {", ".join(OMT_LAYERS)} (BSD-3-Clause, (c) OpenMapTiles contributors)\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--model', type=Path, default=MODEL)
    parser.add_argument('--styles', type=Path, default=STYLES)
    parser.add_argument('--cache', type=Path, default=Path(__file__).with_name('.cache'))
    args = parser.parse_args()
    out = args.model / 'generated'

    presets, names, omt = load_sources(args.cache)
    tree = Tree(yaml.safe_load((args.model / 'categories.yaml').read_text()))
    assigned, unclaimed = assign(tree, presets)
    categories, category = deepen(tree, assigned, names)
    rules = build_rules(presets, assigned, category, tree, build_class_lookup(omt))
    rules = [written(r) for r in rules]

    known = collect_ids(categories, set())
    manual = yaml.safe_load((args.model / 'classifier.yaml').read_text()) or []
    for rule in manual:
        if rule['category'] not in known:
            raise SystemExit(f'model/classifier.yaml: unknown category {rule["category"]!r}')
    # A hand-written rule with the same match replaces the generated one.
    manual_matches = {r['match'] for r in manual}
    rules = [r for r in rules if r['match'] not in manual_matches]

    out.mkdir(parents=True, exist_ok=True)
    (out / 'categories.yaml').write_text(
        header('categories') + yaml.dump(categories, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120))
    (out / 'classifier.yaml').write_text(
        header('rules') + '# The importer reads model/classifier.yaml first, then these. A term without `=` restricts\n'
        '# the rule to one geometry: point, line or polygon.\n' + dump_rules(rules))
    if yaml.safe_load((out / 'classifier.yaml').read_text()) != rules:
        raise SystemExit('classifier.yaml does not round-trip')

    for pid in unclaimed:
        print(f'warning: no category claims iD preset {pid!r}', file=sys.stderr)
    for warning in check_classes(manual + rules, args.styles / 'classes.yaml', args.model):
        print(f'warning: {warning}', file=sys.stderr)

    with_class = [r for r in manual + rules if r.get('class') not in (None, 'none')]
    print(f'{len(known)} categories, {len(manual)} hand-written and {len(rules)} generated rules '
          f'({len(with_class)} with a render class, {len({r["class"] for r in with_class})} distinct classes)',
          file=sys.stderr)


if __name__ == '__main__':
    main()
