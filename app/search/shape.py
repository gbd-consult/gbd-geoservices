"""Rows to GeoJSON, and model ids to what a client actually sees.

Every result is a Feature with the same flat properties (`PROPERTIES`),
whether an object or an address found it: a client for a map or a list
reads one shape and never asks which table a row came from.

Two jobs that are the same job. A result row carries `categories` as the
internal id list the importer stored -- `['cat_poi', 'cat_poi_food',
'cat_poi_food_restaurant']` -- and a client needs those *and* their names in the
requested language. `/metadata` serves the same tree for the same reason.
Both translations read `model/generated/categories.yaml`, so they live
together and cannot drift apart.

The geometry is serialized by PostGIS (`ST_AsGeoJSON`) rather than parsed
into shapely and re-serialized here, and rounded to 6 decimals -- about
10 cm, far beyond what any map client renders, and a materially smaller
body on a polygon-heavy page. It arrives as a string and is parsed back
because the caller serializes the whole payload in one `json.dumps`;
splicing pre-rendered JSON in would mean escaping it as a string or
hand-assembling the response body.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

#: Decimal places in the emitted GeoJSON. ~10 cm at this latitude.
GEOJSON_DECIMALS = 6

#: Geometry as GeoJSON: the highlight, which is whichever of the three
#: typed columns the row actually has. Exactly one is ever set, so the
#: COALESCE picks rather than merges.
GEOJSON_EXPR = ('ST_AsGeoJSON(COALESCE(o.geom_polygon, o.geom_line, o.geom_point), '
                f'{GEOJSON_DECIMALS})')

#: The centre, always present, so a client can fly to a result without
#: reading its geometry -- which for a merged street or a boundary is
#: large enough that a list view would rather not.
CENTER_EXPR = f'ST_AsGeoJSON(o.geom_center, {GEOJSON_DECIMALS})'

#: Columns every result row needs, whichever mode produced it.
RESULT_COLUMNS = (
    'o.id', 'o.osm_ids', 'o.name', 'o.class', 'o.categories', 'o.category',
    'o.addr_street', 'o.addr_housenumber', 'o.addr_postcode', 'o.addr_city',
    'o.tags', 'o.id_places',
)

#: The places of a result page, looked up once for the whole page: a row
#: carries only their ids (`id_places`, see importer/places.py). A path
#: entry is named by its admin level, not by its own category: a city's
#: area row is "Stadt" as a result (importer/places.py `merge_nodes`) and
#: "Gemeinde" or "Kreis" on a path.
PLACES_SQL = ("SELECT id, name, coalesce((SELECT c FROM unnest(categories) c"
              " WHERE c ~ '^cat_geography_admin_[0-9]+$' LIMIT 1), category) AS category"
              " FROM {objects} WHERE id = ANY(%(ids)s)")

_names: dict[str, dict[str, str]] = {}
_tree: list | None = None


def _load(model_dir: Path | None = None) -> list:
    global _tree
    if _tree is None or model_dir is not None:
        directory = model_dir or _default_model_dir()
        loaded = yaml.safe_load((directory / 'generated' / 'categories.yaml').read_text())
        if model_dir is None:
            _tree = loaded
        return loaded
    return _tree


def _default_model_dir() -> Path:
    from importer.run import MODEL
    return MODEL


def names(lang: str = 'de', model_dir: Path | None = None) -> dict[str, str]:
    """{category id: display name} for one language, flattened from the tree.

    Built once per language: the tree is ~2 000 nodes and a result page
    asks for a handful of names per row, so walking it per request would
    be the most expensive thing in the response.
    """
    if lang not in _names or model_dir is not None:
        table: dict[str, str] = {}
        _flatten(_load(model_dir), lang, table)
        if model_dir is None:
            _names[lang] = table
        return table
    return _names[lang]


def _flatten(nodes, lang: str, out: dict[str, str]) -> None:
    for node in nodes or ():
        # Falling back to the id rather than to another language: a missing
        # translation shows as `amenity_restaurant`, which is at least
        # true, where a German name under `lang=en` looks like a bug in
        # the data.
        out[node['id']] = node.get(f'name_{lang}') or node['id']
        _flatten(node.get('subs'), lang, out)


def tree(languages, icon=None, model_dir: Path | None = None) -> list:
    """The category tree for `/metadata`: id, names, icon, subcategories.

    `names` holds every language in `languages`, so a client switches
    language without asking again. `icon` maps a category id to its icon
    URL; without one there is no `icon` key. `terms_*` are stripped: they
    are query-parser input, not for display, and they are the bulk of the
    file -- serving them would make the tree two orders of magnitude
    larger than what it is for. `subcategories` is absent on a leaf.
    """
    return _strip(_load(model_dir), tuple(languages), icon)


def _strip(nodes, languages: tuple[str, ...], icon) -> list:
    out = []
    for node in nodes or ():
        entry = {'id': node['id'],
                 'names': {lang: node.get(f'name_{lang}') or node['id'] for lang in languages}}
        if icon is not None:
            entry['icon'] = icon(node['id'])
        subs = _strip(node.get('subs'), languages, icon)
        if subs:
            entry['subcategories'] = subs
        out.append(entry)
    return out


def ids(model_dir: Path | None = None) -> set[str]:
    """Every category id in the tree."""
    out: set[str] = set()
    stack = list(_load(model_dir))
    while stack:
        node = stack.pop()
        out.add(node['id'])
        stack.extend(node.get('subs') or ())
    return out


# --- rows ----------------------------------------------------------------

def place_ids(rows) -> list[int]:
    """Every place id the rows' paths name, for one PLACES_SQL lookup."""
    return sorted({place for row in rows for place in (row.get('id_places') or ())})


def place_table(rows, lang: str = 'de') -> dict[int, dict]:
    """{id: path entry} from PLACES_SQL rows."""
    table = names(lang)
    return {row['id']: {'id': row['id'], 'name': row['name'], 'category': row['category'],
                        'category_name': table.get(row['category'], row['category'])}
            for row in rows}


def _path(row, places: dict[int, dict] | None) -> list[dict]:
    return [places[i] for i in (row.get('id_places') or ()) if places and i in places]


#: The category a result without an object carries when its carrier has
#: none either: an address node. It is in the tree like every other, so it
#: has a name in every language and an icon (styles/icons.yaml), and a
#: client needs no special case for it.
ADDRESS_CATEGORY = 'cat_geography_places_address'

#: The objects behind a page's address hits, looked up once for the page:
#: an address row carries only `id_object`.
OBJECTS_SQL = ('SELECT ' + ', '.join(RESULT_COLUMNS) + f', {GEOJSON_EXPR} AS geojson '
               'FROM {objects} o WHERE o.id = ANY(%(ids)s)')

#: Every feature's properties, in this order, whatever produced it. A key
#: with nothing to say is null, never missing: a client written against one
#: result reads every other one the same way.
PROPERTIES = (
    'name', 'category', 'category_name', 'categories', 'icon',
    'center', 'places',
    'match_relevance', 'match_score', 'match_rule', 'match_distance',
    'address_street', 'address_housenumber', 'address_postcode', 'address_city',
    'osm_ids', 'osm_tags',
)

_category_paths: dict[str, list[str]] = {}


def category_path(category: str) -> list[str]:
    """The ids from the root down to `category`, as a row's `categories` has them."""
    if category not in _category_paths:
        _category_paths[category] = _path_to(_load(), category, []) or []
    return _category_paths[category]


def _path_to(nodes, category: str, above: list[str]) -> list[str] | None:
    for node in nodes or ():
        here = [*above, node['id']]
        if node['id'] == category:
            return here
        found = _path_to(node.get('subs'), category, here)
        if found is not None:
            return found
    return None


def object_ids(rows) -> list[int]:
    """Every object an address row points at, for one OBJECTS_SQL lookup."""
    return sorted({row['id_object'] for row in rows if row.get('id_object')})


def _point(geojson: str | None) -> list | None:
    return json.loads(geojson)['coordinates'] if geojson else None


def _properties(obj, lang: str, *, address, match, center, places, osm_ids, osm_tags,
                carrier: str | None = None) -> dict:
    table = names(lang)
    category = obj['category'] if obj else (carrier or ADDRESS_CATEGORY)
    category_ids = list(obj['categories'] or ()) if obj else category_path(category)
    category_name = table.get(category, category) if category else None
    name = (obj['name'] if obj else None) or ''
    street, housenumber, postcode, city = address
    relevance, score, rule, distance = match
    return {
        'name': name,
        'category': category,
        'category_name': category_name,
        'categories': [{'id': c, 'name': table.get(c, c)} for c in category_ids],
        'icon': None,
        'center': center,
        'places': places,
        'match_relevance': int(relevance) if relevance is not None else None,
        'match_score': round(float(score), 4) if score is not None else None,
        'match_rule': rule,
        'match_distance': round(float(distance), 1) if distance is not None else None,
        'address_street': street,
        'address_housenumber': housenumber,
        'address_postcode': postcode,
        'address_city': city,
        'osm_ids': osm_ids,
        'osm_tags': osm_tags,
    }


def _match(row) -> tuple:
    return row.get('relevance'), row.get('score'), row.get('rule'), row.get('distance')


def feature(row, lang: str = 'de', places: dict[int, dict] | None = None) -> dict:
    """One `osm_search_object` row as a GeoJSON Feature.

    `id` is `o` and the search row's serial, not an OSM id: a merged street
    is one result built from many ways, so `osm_ids` is a list and no single
    OSM id identifies the row. The prefix keeps it apart from an address
    hit's `a` id -- the two tables' serials overlap.
    """
    properties = _properties(
        row, lang,
        address=(row['addr_street'], row['addr_housenumber'],
                 row['addr_postcode'], row['addr_city']),
        match=_match(row),
        center=_point(row.get('center')),
        places=_path(row, places),
        osm_ids=list(row['osm_ids'] or ()),
        osm_tags=row['tags'])
    return {
        'type': 'Feature',
        'id': f'o{row["id"]}',
        'properties': properties,
        'geometry': json.loads(row['geojson']) if row.get('geojson') else None,
    }


def address_feature(row, lang: str = 'de', places: dict[int, dict] | None = None,
                    objects: dict[int, dict] | None = None) -> dict:
    """One `osm_search_address` row as a Feature of the same shape.

    With an object behind it (`id_object`) the feature is that object --
    its name, category, OSM ids and tags, and its geometry as the highlight
    -- with the address that matched, not the object's own `addr:*`: a
    building with numbers 1 and 3 found as "Hauptstraße 3" says 3. Without
    one it is a pure address: no name, the carrier's own category
    ("Wohnhaus", "Garage"; `ADDRESS_CATEGORY` for an address node), and the
    carrier as its OSM id, which is what lets a client fetch the building
    outline from `osm_building` -- most addresses sit on an unnamed building. Either
    way `center` is the address point, which is where the address is; a
    campus's centre is not.

    `id` is `a` and the address row's serial, even with an object: two
    addresses of one building are two results, and would share an object id.
    """
    obj = (objects or {}).get(row.get('id_object'))
    properties = _properties(
        obj, lang,
        address=(row['street'], row['housenumber'], row['postcode'], row['city']),
        match=_match(row),
        center=_point(row.get('geojson')),
        places=_path(row, places),
        osm_ids=list(obj['osm_ids'] or ()) if obj else [row['osm_id']],
        osm_tags=obj['tags'] if obj else None,
        carrier=row.get('category'))
    geometry = (obj or {}).get('geojson') or row.get('geojson')
    return {
        'type': 'Feature',
        'id': f'a{row["id"]}',
        'properties': properties,
        'geometry': json.loads(geometry) if geometry else None,
    }


def collection(features: list[dict]) -> dict:
    return {'type': 'FeatureCollection', 'features': features}


def page(features: list[dict], *, req, total: int,
         interpretation: list | None = None) -> dict:
    """A page of results, the response body DESIGN.md "Shape" describes.

    The metadata beside `results`, and `results` a plain FeatureCollection a
    map client can take as it is -- no foreign members in the GeoJSON.

    `total` is the true count of matching rows, not the page's length --
    it comes from `count(*) OVER ()` in the same pass as the page, so it
    costs nothing extra and `has_more` can be right. In the phrase mode it is
    the size of the merged list of capped rules.
    """
    body = {
        'page': req.page,
        'limit': req.limit,
        'count': len(features),
        'total': total,
        'has_more': (req.offset + len(features)) < total,
    }
    if interpretation is not None:
        body['interpretation'] = interpretation
    body['results'] = collection(features)
    return body


def empty(req, interpretation: list | None = None) -> dict:
    return page([], req=req, total=0, interpretation=interpretation)
