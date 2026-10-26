"""Linking addresses to the objects they sit on, and the query dictionaries."""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

import shapely  # noqa: E402

from importer import postprocess  # noqa: E402
from importer import tables as t  # noqa: E402
from importer.writer import TableWriter  # noqa: E402

#: Two places about 3 km apart near Kiel, in 4326.
WEST = (10.10, 54.32)
EAST = (10.15, 54.32)


def street_at(lon, lat, length=0.004):
    return shapely.MultiLineString([[(lon, lat), (lon + length, lat)]])


@pytest.fixture
def search_schema(db, temp_schema):
    for table in (t.OSM_SEARCH_OBJECT, t.OSM_SEARCH_ADDRESS, t.OSM_STREET, t.OSM_CATEGORY_TERM):
        db.execute(t.ddl(temp_schema, table))
    return temp_schema


def add_street(db, schema, name, *, postcode=None, city=None, at=WEST):
    writer = TableWriter(db, schema, t.OSM_SEARCH_OBJECT)
    writer.add(([1], name, name, name, 'X', city, ['highway'], 'highway', 80,
                'cls_road_minor', None, None, postcode, city,
                None, street_at(*at), None, shapely.Point(*at), None, None))
    writer.close()
    return db.execute(
        f"select id from {schema}.osm_search_object where addr_postcode is not distinct from %s"
        f" and addr_city is not distinct from %s and name = %s",
        (postcode, city, name)).fetchone()[0]


def add_address(db, schema, street, *, postcode=None, city=None, at=WEST, osm_id=99):
    writer = TableWriter(db, schema, t.OSM_SEARCH_ADDRESS)
    writer.add((osm_id, street, street, 'X', postcode, city, '1', 1, None,
                shapely.Point(*at), None, None, None))
    writer.close()


def test_id_object_links_to_the_carrier(db, search_schema):
    # The reason osm_search_address carries osm_id at all: the search row's
    # id is a serial the database assigned, so this is the only handle.
    writer = TableWriter(db, search_schema, t.OSM_SEARCH_OBJECT)
    writer.add(([4242], 'Rathaus', 'rathaus', 'rathaus', 'X', None,
                ['cat_poi'], 'cat_poi', 80, 'cls_poi_public', None, None, None, None,
                None, None, shapely.MultiPolygon([[[(10.0, 54.0), (10.1, 54.0),
                                                    (10.1, 54.1), (10.0, 54.0)]], ]),
                shapely.Point(10.05, 54.03), None, None))
    writer.close()
    add_address(db, search_schema, 'marktplatz', osm_id=4242)

    assert postprocess.resolve_id_object(db, search_schema) == 1
    row = db.execute(
        f'select a.id_object, o.name from {search_schema}.osm_search_address a'
        f' join {search_schema}.osm_search_object o on o.id = a.id_object').fetchone()
    assert row[1] == 'Rathaus'


STREET_CLASSES = ['cls_road_minor', 'cls_road_primary', 'cls_road_secondary']


def test_street_dictionary_counts_distinct_names(db, search_schema, classifier):
    add_street(db, search_schema, 'hauptstrasse', postcode='24103', at=WEST)
    add_street(db, search_schema, 'hauptstrasse', postcode='24114', at=EAST)
    add_street(db, search_schema, 'bahnhofstrasse', at=WEST)

    counts = postprocess.build_dictionaries(db, search_schema, classifier, ['de'], STREET_CLASSES)
    assert counts['osm_street'] == 2
    rows = dict(db.execute(f'select search_street, n from {search_schema}.osm_street').fetchall())
    assert rows == {'hauptstrasse': 2, 'bahnhofstrasse': 1}


def test_only_streets_reach_the_street_dictionary(db, search_schema, classifier):
    """osm_street holds the search objects with a street class.

    Selecting on `geom_line is not null` instead picks up every named line
    that got a search row -- rivers, railways, and the named lines with no
    render class at all. The address search matches the user's street
    against this table, so a stream called Mühlbach would answer as one.
    """
    add_street(db, search_schema, 'hauptstrasse', at=WEST)
    writer = TableWriter(db, search_schema, t.OSM_SEARCH_OBJECT)
    for name, cls in [('muehlbach', 'cls_waterway_stream'), ('nordbahn', 'cls_rail_rail'),
                      ('namenlos', None)]:
        writer.add(([9], name, name, name, 'X', None, ['x'], 'x', 20, cls,
                    None, None, None, None, None, street_at(*EAST), None,
                    shapely.Point(*EAST), None, None))
    writer.close()

    postprocess.build_dictionaries(db, search_schema, classifier, ['de'], STREET_CLASSES)
    names = {r[0] for r in db.execute(f'select search_street from {search_schema}.osm_street')}
    assert names == {'hauptstrasse'}


def test_category_terms_are_normalized_and_phonetic(db, search_schema, classifier):
    postprocess.build_dictionaries(db, search_schema, classifier, ['de', 'en'], STREET_CLASSES)
    total = db.execute(f'select count(*) from {search_schema}.osm_category_term').fetchone()[0]
    assert total > 5000

    # A term the phrase parser has to resolve: "restaurant" -> the category.
    rows = db.execute(
        f"select category from {search_schema}.osm_category_term where term = 'restaurant'"
    ).fetchall()
    # One category, not the dozen cuisines that list "restaurant" among
    # their synonyms: a category's own name wins over the others' terms.
    assert set(rows) == {('cat_poi_food_restaurant',)}

    # Umlauts folded the same way the query side folds them.
    assert db.execute(
        f"select count(*) from {search_schema}.osm_category_term where term like '%ä%'"
    ).fetchone()[0] == 0
    assert db.execute(
        f"select count(*) from {search_schema}.osm_category_term where phon_term is null"
    ).fetchone()[0] == 0
