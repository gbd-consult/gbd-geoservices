"""The address path: which places a search row lies in (importer/places.py).

Every one of these fails silently in the product: a path that is missing a
level, names the wrong municipality, or attaches the neighbouring one
still renders as a plausible list of place names.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

import shapely  # noqa: E402

from importer import places  # noqa: E402
from importer import tables as t  # noqa: E402
from importer.writer import TableWriter  # noqa: E402

#: A state split into two municipalities at lon 10.2; municipality A has a
#: town part in its north-west corner, municipality B has none.
STATE = (10.0, 54.0, 10.4, 54.6)
MUNICIPALITY_A = (10.0, 54.0, 10.2, 54.6)
MUNICIPALITY_B = (10.2, 54.0, 10.4, 54.6)
TOWN_PART = (10.0, 54.3, 10.1, 54.4)


@pytest.fixture
def schema(db, temp_schema):
    for table in (t.OSM_SEARCH_OBJECT, t.OSM_SEARCH_ADDRESS):
        db.execute(t.ddl(temp_schema, table))
    return temp_schema


def add_object(db, schema, name, category, *, cls=None, point=None, line=None, polygon=None,
               search_name=None, importance=20, osm_id=1, tags=None):
    geometry = point or line or polygon
    parts = category.split('_')
    # Stored with every ancestor, as the importer stores them.
    ancestors = ['_'.join(parts[:n]) for n in range(2, len(parts) + 1)]
    writer = TableWriter(db, schema, t.OSM_SEARCH_OBJECT)
    writer.add(([osm_id], name, search_name or name, name, 'X', None,
                ancestors, category, importance, cls,
                None, None, None, None,
                point, line, polygon, geometry.representative_point(),
                json.dumps(tags) if tags else None, None))
    writer.close()
    return db.execute(f'select max(id) from {schema}.osm_search_object').fetchone()[0]


def add_village(db, schema, name, point, **kw):
    return add_object(db, schema, name, 'cat_geography_places_village', cls='cls_place_village',
                      point=point, **kw)


def add_area(db, schema, name, level, box, **kw):
    return add_object(db, schema, name, places.ADMIN_CATEGORY.format(level=level),
                      polygon=shapely.MultiPolygon([shapely.box(*box)]), **kw)


def add_address(db, schema, lon, lat):
    writer = TableWriter(db, schema, t.OSM_SEARCH_ADDRESS)
    writer.add((1, 'strasse_1', 'strasse_1', 'X', None, None, '1', 1, None,
                shapely.Point(lon, lat), None, None, None))
    writer.close()
    return db.execute(f'select max(id) from {schema}.osm_search_address').fetchone()[0]


def line(*coords):
    return shapely.MultiLineString([coords])


@pytest.fixture
def areas(db, schema):
    return {
        'state': add_area(db, schema, 'state_1', 4, STATE),
        'a': add_area(db, schema, 'municipality_1', 8, MUNICIPALITY_A),
        'b': add_area(db, schema, 'municipality_2', 8, MUNICIPALITY_B),
        'part': add_area(db, schema, 'town_part_1', 10, TOWN_PART),
    }


def path(db, schema, table, row_id):
    return db.execute(f'select id_places from {schema}.{table} where id = %s',
                      (row_id,)).fetchone()[0]


def test_an_address_gets_every_area_from_the_state_down(db, schema, areas, params):
    address = add_address(db, schema, 10.05, 54.35)
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_address', address) == [
        areas['state'], areas['a'], areas['part']]


def test_a_street_across_a_border_lies_in_both_municipalities(db, schema, areas, params):
    street = add_object(db, schema, 'street_1', 'cat_built_roads_minor_residential',
                        line=line((10.19, 54.2), (10.21, 54.2)))
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', street) == [
        areas['state'], areas['a'], areas['b']]


def test_a_category_not_configured_gets_no_path(db, schema, areas, params):
    """A river would otherwise collect every municipality it passes."""
    assert not {'cat_geography', 'cat_geography_water'} & set(params.place_categories)
    river = add_object(db, schema, 'river_1', 'cat_geography_water_river',
                       line=line((10.05, 54.2), (10.35, 54.2)))
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', river) is None


def test_an_area_touching_a_border_is_not_across_it(db, schema, areas, params):
    park = add_object(db, schema, 'park_1', 'cat_geography_landcover_park',
                      polygon=shapely.MultiPolygon([shapely.box(10.15, 54.1, 10.2, 54.15)]))
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', park) == [areas['state'], areas['a']]


def test_an_area_split_by_a_border_lies_in_both_municipalities(db, schema, areas, params):
    """So the park is found under either municipality's name."""
    park = add_object(db, schema, 'park_1', 'cat_geography_landcover_park',
                      polygon=shapely.MultiPolygon([shapely.box(10.18, 54.1, 10.22, 54.15)]))
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', park) == [areas['state'], areas['a'], areas['b']]


def test_an_area_is_not_in_a_place_holding_a_small_share_of_it(db, schema, areas, params):
    """A district's boundary is off its neighbour's by slivers; without the
    share, Kiel was in Kreis Plön and a dozen other neighbours."""
    share = params.place_area_share / 2
    park = add_object(db, schema, 'park_1', 'cat_geography_landcover_park',
                      polygon=shapely.MultiPolygon([shapely.box(10.2 - 0.04 * (1 - share), 54.1,
                                                                10.2 + 0.04 * share, 54.15)]))
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', park) == [areas['state'], areas['a']]


def test_an_area_is_not_in_the_places_it_contains(db, schema, areas, params):
    """Kiel's path listed its thirty Ortsteile: their interiors overlap it."""
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', areas['a']) == [areas['state']]


def test_an_area_is_not_its_own_place(db, schema, areas, params):
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', areas['part']) == [areas['state'], areas['a']]


def test_administrative_areas_get_a_path(params):
    """Alt-Hohenschönhausen (Ortsteil) came back with no places: the areas
    themselves were not configured, only what lies in them."""
    assert 'cat_geography_admin' in params.place_categories


def test_an_area_lies_only_in_areas_of_a_lower_level(db, schema, areas, params):
    """Kiel is a district (6) and a municipality (8) with one outline. The
    share test holds both ways, so without the level rule the district lay
    in the municipality."""
    district = add_area(db, schema, 'district_1', 6, MUNICIPALITY_A)
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', district) == [areas['state']]
    assert path(db, schema, 'osm_search_object', areas['a']) == [areas['state'], district]


def test_a_level_outside_the_levels_still_limits_the_path(db, schema, areas, params):
    """An Amt (7) is no place on any path, but it is an area, and lies
    only in the coarser ones."""
    assert 7 not in params.place_levels
    district = add_area(db, schema, 'district_1', 6, STATE)
    amt = add_area(db, schema, 'amt_1', 7, MUNICIPALITY_A)
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_object', amt) == [areas['state'], district]


def test_a_place_without_a_border_is_not_on_the_path(db, schema, areas, params):
    """Nothing can be said to lie in a node: the nearest village was a guess,
    and put a region spanning several municipalities in a hamlet near its
    centre."""
    add_village(db, schema, 'village_1', shapely.Point(10.3, 54.2))
    address = add_address(db, schema, 10.301, 54.2)
    places.resolve(db, schema, params)
    assert path(db, schema, 'osm_search_address', address) == [areas['state'], areas['b']]


def test_the_working_tables_are_dropped(db, schema, areas, params):
    places.resolve(db, schema, params)
    left = db.execute(
        "select count(*) from pg_tables where schemaname = %s and tablename like '\\_place%%'",
        (schema,)).fetchone()[0]
    assert left == 0


# --- place nodes merged into their areas ---------------------------------

def row(db, schema, row_id):
    return db.execute(f'select category, categories, importance, st_astext(geom_center),'
                      f' geom_polygon is not null from {schema}.osm_search_object where id = %s',
                      (row_id,)).fetchone()


def add_town(db, schema, name, point):
    return add_object(db, schema, name, 'cat_geography_places_town', cls='cls_place_town',
                      point=point, importance=100)


def test_a_place_node_is_merged_into_the_area_of_its_name(db, schema, areas):
    """"Berlin" was the node first and the Land's polygon below it, and a
    client highlighted a point. One row now: the area's polygon, the node's
    category, importance and centre."""
    town = add_town(db, schema, 'municipality_1', shapely.Point(10.15, 54.2))
    assert places.merge_nodes(db, schema) == 1
    assert row(db, schema, town) is None
    category, categories, importance, center, polygon = row(db, schema, areas['a'])
    assert category == 'cat_geography_places_town'
    assert {'cat_geography_places_town', 'cat_geography_admin_8'} <= set(categories)
    assert len(categories) == len(set(categories))
    assert importance == 100
    assert center == 'POINT(10.15 54.2)'
    assert polygon


def test_a_place_node_of_another_name_stays(db, schema, areas):
    village = add_village(db, schema, 'village_1', shapely.Point(10.15, 54.2))
    assert places.merge_nodes(db, schema) == 0
    assert row(db, schema, village) is not None
    assert row(db, schema, areas['a'])[0] == 'cat_geography_admin_8'


def test_a_place_node_outside_the_area_of_its_name_stays(db, schema, areas):
    town = add_town(db, schema, 'municipality_1', shapely.Point(10.3, 54.2))
    assert places.merge_nodes(db, schema) == 0
    assert row(db, schema, town) is not None


def test_a_place_node_joins_the_smallest_area_of_its_name(db, schema, areas):
    district = add_area(db, schema, 'municipality_1', 6, STATE)
    add_town(db, schema, 'municipality_1', shapely.Point(10.15, 54.2))
    assert places.merge_nodes(db, schema) == 1
    assert row(db, schema, areas['a'])[0] == 'cat_geography_places_town'
    assert row(db, schema, district)[0] == 'cat_geography_admin_6'


def test_a_place_node_of_no_kind_keeps_the_area_category(db, schema, areas):
    """`place=country` is "Sonstiger Ort"; the area's "Staat" says more."""
    add_object(db, schema, 'municipality_1', places.PLACE_OTHER, point=shapely.Point(10.15, 54.2),
               importance=40)
    assert places.merge_nodes(db, schema) == 1
    category, categories, importance, _, _ = row(db, schema, areas['a'])
    assert category == 'cat_geography_admin_8'
    assert places.PLACE_OTHER in categories and importance == 40


def test_a_merged_place_keeps_both_osm_ids_and_both_tag_sets(db, schema):
    """The node carries what the place is -- `place`, `population`, most
    translations -- and the relation what the unit is; a client links to
    either. The relation wins a shared key: a capital's node has
    `admin_level=2`, and the area is still a municipality."""
    area = add_area(db, schema, 'municipality_1', 8, MUNICIPALITY_A, osm_id=-1,
                    tags={'boundary': 'administrative', 'name': 'name_1', 'admin_level': '8'})
    add_object(db, schema, 'municipality_1', 'cat_geography_places_town',
               point=shapely.Point(10.15, 54.2), importance=100, osm_id=1,
               tags={'place': 'town', 'name': 'name_2', 'admin_level': '2'})
    places.merge_nodes(db, schema)
    osm_ids, tags = db.execute(f'select osm_ids, tags from {schema}.osm_search_object'
                               f' where id = %s', (area,)).fetchone()
    assert osm_ids == [-1, 1]
    assert tags == {'boundary': 'administrative', 'admin_level': '8', 'place': 'town',
                    'name': 'name_1'}
