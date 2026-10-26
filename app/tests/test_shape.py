"""Result shaping: rows to GeoJSON, model ids to what a client sees.

The category translation is the half worth testing hard. A result carries
internal ids (`cat_poi_food_restaurant`), the client needs names in its own
language, and a missing translation has to look like a missing translation
rather than like data from the wrong language.
"""

from __future__ import annotations

import json

import pytest

from search import shape

ROW = {
    'id': 42,
    'osm_ids': [123, 456],
    'name': 'Kieler Hof',
    'class': 'cls_poi_food',
    'categories': ['cat_poi', 'cat_poi_food', 'cat_poi_food_restaurant'],
    'category': 'cat_poi_food_restaurant',
    'addr_street': 'Holtenauer Straße',
    'addr_housenumber': '12a',
    'addr_postcode': '24105',
    'addr_city': 'Kiel',
    'tags': {'amenity': 'restaurant'},
    'geojson': '{"type":"Point","coordinates":[10.13,54.33]}',
    'center': '{"type":"Point","coordinates":[10.13,54.33]}',
    'score': 0.87654321,
    'distance': 1234.5678,
    'rule': 'name_in_place',
}


class Req:
    mode, page, limit, offset = 'name', 0, 50, 0


# --- the category tree ---------------------------------------------------

def test_names_are_flattened_from_the_whole_tree():
    table = shape.names('de')
    assert table['cat_poi_food'] == 'Gastronomie'
    assert table['cat_poi_food_restaurant']
    assert len(table) > 500


def test_both_configured_languages_resolve():
    de, en = shape.names('de'), shape.names('en')
    assert de['cat_poi_food'] != en['cat_poi_food']
    assert set(de) == set(en)


def test_a_missing_translation_falls_back_to_the_id():
    """Not to another language.

    A German name served under lang=en looks like a bug in the data; the
    id at least is true.
    """
    table = shape.names('xx')
    assert table['cat_poi_food'] == 'cat_poi_food'


def test_the_tree_carries_no_terms():
    """`terms_*` are query-parser input and the bulk of the file.

    Serving them makes this response two orders of magnitude larger than
    what it is for.
    """
    serialized = json.dumps(shape.tree(['de', 'en']))
    assert 'terms_de' not in serialized and 'terms_en' not in serialized
    assert '"id": "cat_poi"' in serialized.replace('"id":"cat_poi"', '"id": "cat_poi"')


def test_the_tree_keeps_its_shape():
    tree = shape.tree(['de', 'en'], icon=lambda category: f'/icons/{category}.svg')
    top = next(n for n in tree if n['id'] == 'cat_poi')
    assert set(top) == {'id', 'names', 'icon', 'subcategories'}
    assert set(top['names']) == {'de', 'en'}
    assert top['icon'] == '/icons/cat_poi.svg'
    assert any(sub['id'] == 'cat_poi_food' for sub in top['subcategories'])


def test_the_tree_has_no_icon_key_without_an_icon_url():
    assert 'icon' not in shape.tree(['de'])[0]


def test_each_preset_of_a_group_is_a_category_of_its_own():
    """The deep tree: a search for "Metzger" finds butchers, not the whole
    grocery group they are filed under in model/categories.yaml."""
    assert shape.category_path('cat_poi_shopping_groceries_butcher')[-2:] == [
        'cat_poi_shopping_groceries', 'cat_poi_shopping_groceries_butcher']


def test_a_leaf_has_no_subcategories_key():
    def leaves(nodes):
        for node in nodes:
            if 'subcategories' in node:
                yield from leaves(node['subcategories'])
            else:
                yield node
    assert any(leaves(shape.tree(['de'])))


def test_a_category_path_runs_from_the_root():
    assert shape.category_path('cat_poi_food_restaurant') == [
        'cat_poi', 'cat_poi_food', 'cat_poi_food_restaurant']


def test_an_unknown_category_has_an_empty_path():
    assert shape.category_path('no_such_category') == []


# --- features ------------------------------------------------------------

def test_a_row_becomes_a_feature():
    feature = shape.feature(ROW, 'de')
    assert feature['type'] == 'Feature'
    assert feature['id'] == 'o42'
    assert feature['geometry'] == {'type': 'Point', 'coordinates': [10.13, 54.33]}


def test_the_feature_id_is_the_search_row_not_an_osm_id():
    """A merged street is one result built from many ways.

    osm_id cannot be its identity, so the result carries the list and is
    identified by the row's own serial.
    """
    feature = shape.feature(ROW, 'de')
    assert feature['id'] == f"o{ROW['id']}"
    assert feature['properties']['osm_ids'] == [123, 456]


def test_an_object_and_an_address_never_share_an_id():
    """The two tables' serials overlap: object 7 and address 7 both exist."""
    assert (shape.feature({**ROW, 'id': 7})['id']
            != shape.address_feature(ADDRESS_ROW)['id'])


def test_categories_are_id_and_name_root_first():
    categories = shape.feature(ROW, 'de')['properties']['categories']
    assert [c['id'] for c in categories] == ROW['categories']
    assert categories[1] == {'id': 'cat_poi_food', 'name': 'Gastronomie'}


def test_category_names_follow_the_language():
    de = shape.feature(ROW, 'de')['properties']
    en = shape.feature(ROW, 'en')['properties']
    assert [c['name'] for c in de['categories']] != [c['name'] for c in en['categories']]
    assert de['category_name'] == de['categories'][-1]['name']
    assert en['category_name'] == en['categories'][-1]['name']


def test_an_unknown_category_id_shows_as_itself():
    row = {**ROW, 'categories': ['invented_thing'], 'category': 'invented_thing'}
    properties = shape.feature(row)['properties']
    assert properties['categories'] == [{'id': 'invented_thing', 'name': 'invented_thing'}]


def test_the_score_is_rounded_but_present():
    """A score computed and never returned is no use to the client.

    Without it a client cannot tell a confident hit from a desperate one,
    and neither can anyone debugging the ranking.
    """
    assert shape.feature(ROW)['properties']['match_score'] == 0.8765


def test_distance_is_metres_to_a_decimetre():
    assert shape.feature(ROW)['properties']['match_distance'] == 1234.6


def test_the_centre_is_a_bare_coordinate_pair():
    # So a list view can fly to a result without parsing a boundary
    # polygon it is not going to draw.
    assert shape.feature(ROW)['properties']['center'] == [10.13, 54.33]


@pytest.mark.parametrize('field,key', [('score', 'match_score'), ('rule', 'match_rule'),
                                       ('distance', 'match_distance'), ('center', 'center')])
def test_an_absent_optional_field_is_nulled_not_left_out(field, key):
    """A client reads every result the same way, so a key is never missing."""
    row = {k: v for k, v in ROW.items() if k != field}
    assert shape.feature(row)['properties'][key] is None


def test_the_objects_address_is_its_own_addr_tags():
    properties = shape.feature(ROW)['properties']
    assert (properties['address_street'], properties['address_housenumber'],
            properties['address_postcode'], properties['address_city']) == \
        ('Holtenauer Straße', '12a', '24105', 'Kiel')


def test_an_unnamed_object_has_an_empty_name():
    assert shape.feature({**ROW, 'name': None})['properties']['name'] == ''


def test_a_row_without_geometry_is_a_feature_with_null_geometry():
    # GeoJSON allows it, and a caller that asked for no geometry should
    # still get a well-formed FeatureCollection.
    row = {k: v for k, v in ROW.items() if k != 'geojson'}
    assert shape.feature(row)['geometry'] is None


def test_the_highlight_is_the_typed_column_not_the_centre():
    assert 'geom_polygon, o.geom_line, o.geom_point' in shape.GEOJSON_EXPR
    assert 'geom_center' in shape.CENTER_EXPR


# --- addresses -----------------------------------------------------------

ADDRESS_ROW = {
    'id': 7, 'street': 'Holtenauer Straße', 'housenumber': '12a',
    'postcode': '24105', 'city': 'Kiel', 'osm_id': 99, 'id_object': None,
    'id_places': [2, 1], 'geojson': '{"type":"Point","coordinates":[10.1,54.3]}',
    'score': 0.5,
}

OBJECT_ROW = {**ROW, 'id': 42, 'name': 'Kieler Hof',
              'addr_housenumber': '14',
              'geojson': '{"type":"Polygon","coordinates":[[[10,54],[11,54],[11,55],[10,54]]]}'}


def test_every_feature_has_the_same_properties_in_the_same_order():
    """Object, address with an object, pure address: one shape."""
    shapes = [
        shape.feature(ROW),
        shape.address_feature({**ADDRESS_ROW, 'id_object': 42}, objects={42: OBJECT_ROW}),
        shape.address_feature(ADDRESS_ROW),
    ]
    for feature in shapes:
        assert tuple(feature['properties']) == shape.PROPERTIES


def test_a_pure_address_is_the_address_category():
    properties = shape.address_feature(ADDRESS_ROW, 'de')['properties']
    assert properties['name'] == ''
    assert properties['category'] == shape.ADDRESS_CATEGORY
    assert properties['category_name'] == 'Adresse'
    assert [c['id'] for c in properties['categories']] == [
        'cat_geography', 'cat_geography_places', 'cat_geography_places_address']


def test_a_pure_address_is_what_it_sits_on():
    """A house with an address and no name is a house, not "Adresse"."""
    properties = shape.address_feature({**ADDRESS_ROW, 'category': 'cat_built_buildings'},
                                       'de')['properties']
    assert properties['name'] == ''
    assert properties['category'] == 'cat_built_buildings'
    assert properties['category_name'] == shape.names('de')['cat_built_buildings']
    assert [c['id'] for c in properties['categories']] == ['cat_built', 'cat_built_buildings']


def test_the_address_category_is_in_the_tree():
    """Removed from categories.yaml, every pure address would lose its name
    and its icon, and nothing else would notice."""
    assert shape.ADDRESS_CATEGORY in shape.ids()


def test_a_pure_address_carries_the_carrier_osm_id():
    """Most addresses sit on an unnamed building and so have no id_object.

    osm_id against osm_building is the only way a client gets the outline.
    """
    properties = shape.address_feature(ADDRESS_ROW)['properties']
    assert properties['osm_ids'] == [99] and properties['osm_tags'] is None


def test_a_pure_address_is_its_point():
    feature = shape.address_feature(ADDRESS_ROW)
    assert feature['id'] == 'a7'
    assert feature['geometry'] == {'type': 'Point', 'coordinates': [10.1, 54.3]}
    assert feature['properties']['center'] == [10.1, 54.3]


def test_an_address_with_an_object_is_that_object_at_that_address():
    """The matched address, not the object's own `addr:*`: a building with
    12a and 14 found as "Holtenauer Straße 12a" says 12a. The object's
    geometry is the highlight; the centre stays the address point."""
    feature = shape.address_feature({**ADDRESS_ROW, 'id_object': 42}, 'de',
                                    objects={42: OBJECT_ROW})
    properties = feature['properties']
    assert feature['id'] == 'a7'
    assert properties['name'] == 'Kieler Hof'
    assert properties['category'] == 'cat_poi_food_restaurant'
    assert properties['address_housenumber'] == '12a'
    assert properties['osm_ids'] == [123, 456]
    assert properties['osm_tags'] == {'amenity': 'restaurant'}
    assert feature['geometry']['type'] == 'Polygon'
    assert properties['center'] == [10.1, 54.3]


def test_an_address_whose_object_was_not_looked_up_is_a_pure_address():
    feature = shape.address_feature({**ADDRESS_ROW, 'id_object': 42})
    assert feature['properties']['category'] == shape.ADDRESS_CATEGORY


def test_the_object_lookup_asks_for_each_object_once():
    rows = [{'id_object': 5}, {'id_object': 5}, {'id_object': None}, {'id_object': 3}]
    assert shape.object_ids(rows) == [3, 5]


PLACES = shape.place_table([
    {'id': 1, 'name': 'Kiel', 'category': 'cat_geography_admin_6'},
    {'id': 2, 'name': 'Schleswig-Holstein', 'category': 'cat_geography_admin_4'},
])


def test_the_path_keeps_the_order_the_importer_stored():
    path = shape.address_feature(ADDRESS_ROW, places=PLACES)['properties']['places']
    assert [p['name'] for p in path] == ['Schleswig-Holstein', 'Kiel']
    assert path[1]['category_name'] == 'Kreis'


def test_a_row_without_a_path_has_an_empty_one():
    assert shape.feature(ROW, places=PLACES)['properties']['places'] == []


def test_the_page_lookup_asks_for_each_place_once():
    rows = [{'id_places': [2, 1]}, {'id_places': [1]}, {'id_places': None}]
    assert shape.place_ids(rows) == [1, 2]


# --- the page ------------------------------------------------------------

def test_a_page_reports_the_true_total_not_its_own_length():
    body = shape.page([shape.feature(ROW)], req=Req(), total=137)
    assert body['count'] == 1 and body['total'] == 137 and body['has_more'] is True


def test_has_more_is_false_on_the_last_page():
    class Last:
        mode, page, limit, offset = 'name', 2, 50, 100
    body = shape.page([shape.feature(ROW)], req=Last(), total=101)
    assert body['has_more'] is False


def test_the_interpretation_is_only_present_in_phrase_mode():
    assert 'interpretation' not in shape.page([], req=Req(), total=0)
    assert shape.page([], req=Req(), total=0, interpretation=[])['interpretation'] == []


def test_the_results_are_plain_geojson_and_the_metadata_beside_them():
    """A map client takes `results` as it is; nothing but GeoJSON is in it."""
    body = shape.page([shape.feature(ROW)], req=Req(), total=1)
    assert set(body['results']) == {'type', 'features'}
    assert body['results']['type'] == 'FeatureCollection'
    assert 'type' not in body and 'features' not in body


def test_an_empty_page_is_still_a_feature_collection():
    body = shape.empty(Req())
    assert body['results'] == {'type': 'FeatureCollection', 'features': []}
