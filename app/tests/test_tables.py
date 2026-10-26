"""The table definitions are the contract every other module reads.

The invariant worth testing is that the one column list really does drive
both the DDL and the COPY statement, and that what Postgres ends up with
matches it in the same order -- a column silently shifted by one is the
failure mode COPY has, and it produces plausible wrong data rather than an
error.
"""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

from importer import tables as t  # noqa: E402

ALL = (*t.RENDER_TABLES, *t.SEARCH_TABLES, t.STREET_ENDS, t.IMPORT_META,
       *(t.band_table(base, band) for base in t.BANDED for band in ('_z12', '_z9', '_z6')))


def test_every_table_has_unique_column_names():
    for table in ALL:
        names = t.column_names(table)
        assert len(names) == len(set(names)), table.name
        assert len(names) == len(table.columns)


def test_render_tables_share_the_common_columns():
    common = t.column_names(t.Table('x', t.RENDER_COLUMNS))
    for table in (t.OSM_POINT, t.OSM_LINE, t.OSM_POLYGON, t.OSM_BUILDING):
        assert t.column_names(table)[:len(common)] == common
        assert t.column_names(table)[-1] == 'geom'


def test_bands_match_their_parent_column_for_column():
    # A band is the same data prepared for a zoom range, so a query
    # generated for the full table has to work against it unchanged.
    for base in t.BANDED:
        parent = t.OSM_POLYGON if base == 'osm_polygon' else t.OSM_LINE
        for suffix in ('_z12', '_z9', '_z6'):
            band = t.band_table(base, suffix)
            assert t.column_names(band) == t.column_names(parent)
            assert band.name == base + suffix
            assert band.cluster_on is not None


def test_buildings_are_not_banded():
    # Class minzoom 13 is above every band, so a building can never satisfy
    # one; a band table for them would always be empty.
    assert 'osm_building' not in t.BANDED


def test_search_object_holds_one_geometry_per_row():
    columns = dict(t.OSM_SEARCH_OBJECT.columns)
    assert 'MultiLineString' in columns['geom_line']
    assert 'MultiPolygon' in columns['geom_polygon']
    assert columns['geom_center'].endswith('not null')
    assert '4326' in columns['geom_point']


def test_the_address_table_has_a_key_of_its_own():
    """osm_id is why the table has a key.

    No table references an address row -- id_object and id_places both
    point the other way -- but the client does: a result has to be pageable, and `ORDER BY` needs a unique
    tie-break or two equal rows can swap between pages, showing one twice
    and another never. osm_id cannot be that key, because OSM ids are
    unique per *type* and a node and a way can share one -- 63 of
    Liechtenstein's 12 629 addresses do.
    """
    assert 'id' in t.column_names(t.OSM_SEARCH_ADDRESS)
    assert dict(t.OSM_SEARCH_ADDRESS.columns)['id'] == 'serial primary key'
    # And it is not in the COPY stream: the sequence fills it.
    assert 'id' not in t.copy_names(t.OSM_SEARCH_ADDRESS)


@pytest.mark.parametrize('table', ALL, ids=lambda x: x.name)
def test_ddl_creates_what_the_column_list_says(db, temp_schema, table):
    db.execute(t.ddl(temp_schema, table))
    rows = db.execute(
        'select column_name from information_schema.columns'
        ' where table_schema = %s and table_name = %s order by ordinal_position',
        (temp_schema, table.name),
    ).fetchall()
    assert tuple(r[0] for r in rows) == t.column_names(table)


@pytest.mark.parametrize('table', ALL, ids=lambda x: x.name)
def test_indexes_are_valid(db, temp_schema, table):
    db.execute(t.ddl(temp_schema, table))
    for statement in t.index_statements(temp_schema, table):
        db.execute(statement)


def test_copy_statement_names_every_column_in_order(db, temp_schema):
    table = t.OSM_POINT
    db.execute(t.ddl(temp_schema, table))
    statement = t.copy_sql(temp_schema, table).as_string(db)
    for name in t.column_names(table):
        assert f'"{name}"' in statement
    assert statement.index('"osm_id"') < statement.index('"class"') < statement.index('"geom"')


def test_copy_round_trips_a_row(db, temp_schema):
    # The end-to-end shape the writer relies on: a tuple in column order,
    # geometry as hex EWKB, NULL as \\N.
    table = t.OSM_POINT
    db.execute(t.ddl(temp_schema, table))
    point = '0101000020110F000000000000008041400000000000C05A40'  # SRID 3857
    with db.cursor().copy(t.copy_sql(temp_schema, table)) as copy:
        copy.write('42\tcls_poi_food\tCafé\t\\N\t0\t14\t14\tcat_poi_food_cafe\t\\N\t60\t'
                   + point + '\n')
    row = db.execute(
        f'select osm_id, class, name, label, category, icon, importance, st_srid(geom)'
        f' from {temp_schema}.osm_point'
    ).fetchone()
    assert row == (42, 'cls_poi_food', 'Café', None, 'cat_poi_food_cafe', None,
                   60, 3857)


def test_class_is_indexed_where_it_discriminates():
    """A b-tree on class.

    Skipped on osm_building on purpose: it holds exactly one class by
    construction, so the index would be a pointer to every one of 1.35 M
    rows and would never narrow anything.
    """
    for table in (t.OSM_POINT, t.OSM_LINE, t.OSM_POLYGON, t.OSM_LABEL):
        assert 'using btree (class)' in table.indexes, table.name
    assert 'using btree (class)' not in t.OSM_BUILDING.indexes


def test_bands_are_clustered_not_class_indexed():
    # Small, clustered on geometry, and read nearly whole by a layer.
    for base in t.BANDED:
        band = t.band_table(base, '_z6')
        assert band.cluster_on is not None
        assert 'using btree (class)' not in band.indexes


def test_the_big_tables_are_written_in_spatial_order():
    """As the passes write them, a tile's rows are scattered over the table:
    on de a z13 road layer read 2 576 heap pages for 2 485 rows.
    The bands are clustered on their GiST instead."""
    for table in (*t.RENDER_TABLES, t.OSM_SEARCH_OBJECT, t.OSM_SEARCH_ADDRESS):
        assert table.order_by is not None, table.name
    for base in t.BANDED:
        assert t.band_table(base, '_z6').order_by is None


@pytest.mark.parametrize('table', [table for table in ALL if table.order_by],
                         ids=lambda x: x.name)
def test_order_tables_sorts_and_leaves_no_index(db, temp_schema, table):
    """CLUSTER needs an index; the one it sorts by is dropped again, and the
    table's own indexes are built after."""
    from importer import postprocess

    db.execute(t.ddl(temp_schema, table))
    postprocess.order_tables(db, temp_schema, [table])
    indexes = db.execute('select indexname from pg_indexes where schemaname = %s'
                         ' and tablename = %s and indexname like %s',
                         (temp_schema, table.name, '%_order_idx')).fetchall()
    assert indexes == []


def test_index_names_are_unique_within_a_table():
    """Auto-naming collides, and the build is concurrent.

    `(geom_center)` and `((geom_center::geography))` both derive
    <table>_geom_center_idx, so Postgres refuses the second -- and because
    four connections build indexes at once, even names that would have been
    distinct can be chosen twice before either is inserted.
    """
    for table in ALL:
        names = [t.index_name(table.name, body) for body in table.indexes]
        assert len(names) == len(set(names)), table.name


def test_index_names_fit_in_an_identifier():
    for table in ALL:
        for body in table.indexes:
            assert len(t.index_name(table.name, body)) <= t.NAME_MAX


def test_index_name_distinguishes_a_column_from_an_expression():
    assert (t.index_name('x', 'using gist (geom_center)')
            != t.index_name('x', 'using gist ((geom_center::geography))'))


def test_index_statements_carry_the_name(db, temp_schema):
    db.execute(t.ddl(temp_schema, t.OSM_SEARCH_OBJECT))
    for statement in t.index_statements(temp_schema, t.OSM_SEARCH_OBJECT):
        db.execute(statement)
    names = [r[0] for r in db.execute(
        'select indexname from pg_indexes where schemaname = %s and tablename = %s',
        (temp_schema, 'osm_search_object'))]
    assert 'osm_search_object_geom_center_idx' in names
    assert 'osm_search_object_geom_center_geography_idx' in names


def test_import_meta_is_logged():
    # Everything else is UNLOGGED for the import and switched at the end;
    # import_meta is the completion marker and must survive a crash.
    assert t.IMPORT_META.unlogged is False
    assert all(x.unlogged for x in t.RENDER_TABLES)
