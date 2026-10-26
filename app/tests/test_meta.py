"""import_meta: what the schema was built from.

Written last and in its own transaction, so a schema without a row in it is
a partial import.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

from importer import meta  # noqa: E402
from importer import tables as t  # noqa: E402

EXTRACT = Path('/data/downloads/liechtenstein-latest.osm.pbf')


def has_extract() -> bool:
    return EXTRACT.is_file()


needs_extract = pytest.mark.skipif(not has_extract(), reason=f'{EXTRACT} not present')


@needs_extract
def test_replication_position_comes_from_the_header():
    position = meta.replication(EXTRACT)
    assert position['replication_base_url'].endswith('liechtenstein-updates')
    assert isinstance(position['replication_sequence'], int)
    assert position['extract_timestamp'].endswith('Z')


@needs_extract
def test_bbox_is_the_extract_not_the_tables():
    """`manage.py pre-cache` seeds this extent.

    Taken from the pbf header rather than ST_Extent over a table: the road
    table's extent is inflated by maritime boundaries -- for de_sh to
    7.4-12.3 E against 8.3-11.3 E of actual highways -- and pre-caching
    that would spend most of its time on open sea.
    """
    minx, miny, maxx, maxy = meta.bbox_3857(EXTRACT)
    assert minx < maxx and miny < maxy
    # Liechtenstein: about 9.5 E, 47.1 N.
    assert 1_000_000 < minx < 1_100_000
    assert 5_900_000 < miny < 6_000_000


@needs_extract
def test_write_stores_a_usable_envelope(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.IMPORT_META))
    meta.write(db, temp_schema, area='li', extract=EXTRACT,
               row_counts={'osm_point': 3}, duration_s=12.5,
               style_zooms={'cls_road_motorway': (5, 10), 'cls_poi_food': (None, None)},
               table_classes={'osm_point': {'class_1': 3}})

    row = db.execute(
        f'select area, source, duration_s, st_srid(bbox_3857),'
        f' st_area(bbox_3857) > 0, row_counts, style_zooms, table_classes'
        f' from {temp_schema}.import_meta').fetchone()
    assert row[0] == 'li'
    assert row[1] == EXTRACT.name
    assert row[2] == 12
    # The column exists for the pre-cache to read; NULL would be worse than
    # no column at all.
    assert row[3] == 3857
    assert row[4] is True
    assert row[5] == {'osm_point': 3}
    assert row[6] == {'cls_road_motorway': [5, 10], 'cls_poi_food': [None, None]}
    assert row[7] == {'osm_point': {'class_1': 3}}


@needs_extract
def test_update_sets_columns_of_the_row(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.IMPORT_META))
    meta.write(db, temp_schema, area='li', extract=EXTRACT,
               row_counts={}, duration_s=1.0, style_zooms={}, table_classes={})
    meta.update(db, temp_schema, icons_applied='key_1',
                table_classes={'osm_line': {'class_1': 2}})
    row = meta.read(db, temp_schema)
    assert row['icons_applied'] == 'key_1'
    assert row['table_classes'] == {'osm_line': {'class_1': 2}}


@needs_extract
def test_only_one_row_can_exist(db, temp_schema):
    # The check constraint on id: a second import into a live schema would
    # otherwise leave two rows and no way to tell which is current.
    db.execute(t.ddl(temp_schema, t.IMPORT_META))
    meta.write(db, temp_schema, area='li', extract=EXTRACT,
               row_counts={}, duration_s=1.0, style_zooms={}, table_classes={})
    with pytest.raises(Exception, match='duplicate key|check constraint'):
        meta.write(db, temp_schema, area='li', extract=EXTRACT,
                   row_counts={}, duration_s=1.0, style_zooms={}, table_classes={})


def test_import_meta_survives_a_crash():
    # Everything else is UNLOGGED during the import and switched at the end;
    # this table is the completion marker and is logged from the start.
    assert t.IMPORT_META.unlogged is False
