"""COPY encoding.

The failure mode this guards is not an exception -- it is a tab or a
backslash inside an OSM name shifting every following column by one and
producing rows that look plausible. So the escaping is checked by writing
through a real COPY and reading the values back.
"""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

import shapely  # noqa: E402

from importer import tables as t  # noqa: E402
from importer.writer import NULL, TableWriter, array_literal, field  # noqa: E402

#: Strings that break a naive text COPY, all of them real in OSM data.
NASTY = [
    'plain',
    'tab\there',
    'newline\nhere',
    'carriage\rreturn',
    'back\\slash',
    r'literal \N',
    'quote"and\'apostrophe',
    'brace{}and,comma',
    'Café Müller & Söhne',
    '',
]


def test_field_encodes_the_four_special_characters():
    assert field(None) == NULL
    assert field('plain') == 'plain'
    assert field('a\tb') == 'a\\tb'
    assert field('a\nb') == 'a\\nb'
    assert field('a\rb') == 'a\\rb'
    assert field('a\\b') == 'a\\\\b'
    assert field(42) == '42'
    assert field(True) == 't'


def test_backslash_is_doubled_before_anything_else():
    # Otherwise the escape for a tab would itself be re-escaped, or a
    # literal \N in a name would arrive as a NULL.
    assert field('\\t') == '\\\\t'
    assert field(r'\N') == r'\\N'


def test_array_literal():
    assert array_literal([]) == '{}'
    assert array_literal(None) == NULL
    assert array_literal([1, 2, 3]) == '{1,2,3}'
    assert array_literal(['a', 'b']) == '{"a","b"}'
    assert array_literal(['a,b']) == '{"a,b"}'
    assert array_literal(['a"b']) == '{"a\\"b"}'
    assert array_literal([None, 'a']) == '{NULL,"a"}'


@pytest.mark.parametrize('value', NASTY)
def test_text_round_trips(db, temp_schema, value):
    db.execute(t.ddl(temp_schema, t.OSM_POINT))
    writer = TableWriter(db, temp_schema, t.OSM_POINT)
    writer.add((1, 'cls_poi_food', value, None, 0, 14, 14, 'cat_poi_food_cafe', None, 60,
                shapely.Point(1.0, 2.0)))
    writer.close()
    stored = db.execute(f'select name from {temp_schema}.osm_point').fetchone()[0]
    assert stored == value


def test_every_column_lands_where_it_belongs(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.OSM_BUILDING))
    writer = TableWriter(db, temp_schema, t.OSM_BUILDING)
    square = shapely.Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    writer.add((-7, 'cls_building', 'Rat\thaus', '12a', 1060, 13, 15, 9.6, 'levels', square))
    assert writer.close() == 1
    row = db.execute(
        f'select osm_id, class, name, label, z_order, minzoom, minzoom_label, height,'
        f' height_src, st_area(geom), st_srid(geom) from {temp_schema}.osm_building'
    ).fetchone()
    assert row == (-7, 'cls_building', 'Rat\thaus', '12a', 1060, 13, 15,
                   pytest.approx(9.6), 'levels', pytest.approx(100.0), 3857)


def test_arrays_and_jsonb_round_trip(db, temp_schema):
    import json
    db.execute(t.ddl(temp_schema, t.OSM_SEARCH_OBJECT))
    writer = TableWriter(db, temp_schema, t.OSM_SEARCH_OBJECT)
    tags = {'name': 'Zur\tPost', 'amenity': 'pub', 'note': 'a "quoted" \\ thing'}
    writer.add(([12, -34], 'Zur\tPost', 'zur post', 'zur post', '87284', None,
                ['amenity', 'amenity_pub'], 'amenity_pub', 60, 'poi_pub',
                None, None, None, None,
                shapely.Point(9.5, 54.5), None, None, shapely.Point(9.5, 54.5),
                json.dumps(tags, ensure_ascii=False), None))
    writer.close()
    row = db.execute(
        f'select osm_ids, name, categories, tags, st_x(geom_point), st_srid(geom_center)'
        f' from {temp_schema}.osm_search_object'
    ).fetchone()
    assert row[0] == [12, -34]
    assert row[1] == 'Zur\tPost'
    assert row[2] == ['amenity', 'amenity_pub']
    assert row[3] == tags
    assert row[4] == pytest.approx(9.5)
    assert row[5] == 4326


def test_serial_id_is_filled_by_the_database(db, temp_schema):
    # The three passes write this table concurrently, so ids cannot be
    # handed out on the Python side.
    db.execute(t.ddl(temp_schema, t.OSM_SEARCH_OBJECT))
    writer = TableWriter(db, temp_schema, t.OSM_SEARCH_OBJECT)
    for i in range(3):
        writer.add(([i], f'n{i}', None, None, None, None, [], None, None, None,
                    None, None, None, None, shapely.Point(9, 54), None, None,
                    shapely.Point(9, 54), None, None))
    writer.close()
    ids = [r[0] for r in db.execute(f'select id from {temp_schema}.osm_search_object order by id')]
    assert ids == [1, 2, 3]


def test_null_geometry_stays_null(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.OSM_SEARCH_OBJECT))
    writer = TableWriter(db, temp_schema, t.OSM_SEARCH_OBJECT)
    line = shapely.MultiLineString([[(9, 54), (9.1, 54.1)]])
    writer.add(([1], 'Street', None, None, None, None, [], None, None, None,
                None, None, None, None, None, line, None, shapely.Point(9, 54), None, None))
    writer.close()
    row = db.execute(
        f'select geom_point is null, geom_line is null, geom_polygon is null'
        f' from {temp_schema}.osm_search_object').fetchone()
    assert row == (True, False, True)


def test_batching_writes_everything(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.OSM_POINT))
    writer = TableWriter(db, temp_schema, t.OSM_POINT, batch=7)
    for i in range(50):
        writer.add((i, 'cls_poi_food', f'n{i}', None, 0, 14, None, 'cat_poi_food_cafe', None, 60,
                    shapely.Point(i, 1.0)))
    assert writer.close() == 50
    assert db.execute(f'select count(*) from {temp_schema}.osm_point').fetchone()[0] == 50


def test_wrong_width_is_refused(db, temp_schema):
    writer = TableWriter(db, temp_schema, t.OSM_POINT)
    with pytest.raises(ValueError, match='takes 11 columns, got 3'):
        writer.add((1, 'cls_poi_food', 'x'))


def test_flush_is_safe_when_empty(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.OSM_POINT))
    writer = TableWriter(db, temp_schema, t.OSM_POINT)
    writer.flush()
    assert writer.close() == 0
