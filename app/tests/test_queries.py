"""The SQL a Mapnik datasource runs.

Two things here are easy to get subtly wrong and impossible to notice from
a rendered tile: the scale-denominator arithmetic, which decides *which*
data a tile draws, and the bbox clause, which decides whether the query
touches an index or the whole table. Both are checked against the real
database rather than against a string.
"""

from __future__ import annotations

import math

import pytest

from renderer import queries
from renderer.queries import Source

#: cos(54 N): one ground metre is 1/cos(lat) 3857 units there, so a
#: true-metre CRS needs this to land on the same zoom.
SH_FACTOR = math.cos(math.radians(54.0))


def present_fixture():
    """Classes per table, the shape lib.db.table_classes returns."""
    return {
        'osm_point': {'cls_poi_cafe': 5, 'cls_place_city': 2},
        'osm_line': {'cls_road_primary': 9, 'cls_waterway_river': 3},
        'osm_polygon': {'cls_landcover_wood': 7},
        'osm_building': {'cls_building': 11},
        'osm_label': {'cls_poi_cafe': 4, 'cls_landcover_wood': 2},
    }


# --- the zoom expression -------------------------------------------------

def test_scale_denominator_matches_the_known_web_mercator_values():
    # The values every WMTS GoogleMapsCompatible table lists.
    assert queries.scale_denominator(0) == pytest.approx(559_082_264.0287178)
    assert queries.scale_denominator(1) == pytest.approx(279_541_132.0143589)
    assert queries.scale_denominator(18) == pytest.approx(2132.7295, rel=1e-6)


@pytest.mark.parametrize('zoom', range(0, 19))
def test_zoom_expression_inverts_scale_denominator(db, zoom):
    """Round-trip through Postgres, because the expression runs there.

    An off-by-one here does not fail: it draws the next zoom's data.
    """
    expression = queries.zoom_expression().replace(
        '!scale_denominator!', repr(queries.scale_denominator(zoom)))
    assert db.execute(f'select {expression}').fetchone()[0] == zoom


@pytest.mark.parametrize('zoom', range(0, 19))
def test_a_true_metre_crs_lands_on_the_same_zoom(db, zoom):
    # A UTM32 level with the same *ground* metres per pixel as 3857 zoom z
    # at 54 N must map back to z.
    denominator = queries.scale_denominator(zoom, SH_FACTOR)
    expression = queries.zoom_expression(SH_FACTOR).replace(
        '!scale_denominator!', repr(denominator))
    assert db.execute(f'select {expression}').fetchone()[0] == zoom


def test_a_utm_level_is_coarser_than_the_same_numbered_3857_zoom():
    # 0.59 ground metres per 3857 unit at 54 N, so the same pixel size is a
    # different denominator. This is why the factor exists at all.
    assert queries.scale_denominator(8, SH_FACTOR) < queries.scale_denominator(8)


# --- bands ---------------------------------------------------------------

def test_band_ranges_tile_the_whole_pyramid(params):
    ranges = queries.band_ranges(params.bands, 18)
    assert [(s, lo, hi) for s, lo, hi in ranges] == [
        ('_z6', 0, 6), ('_z9', 7, 9), ('_z12', 10, 12), ('', 13, 18)]
    # No gap and no overlap: every zoom is served by exactly one table.
    covered = [z for _, lo, hi in ranges for z in range(lo, hi + 1)]
    assert covered == list(range(0, 19))


# --- sources -------------------------------------------------------------

def test_a_layer_spanning_tables_becomes_several_sources(params):
    # A fill layer may read the polygon, building and line tables: in
    # Mapnik terms "fill" is the inner stroke of a road as much as it is a
    # polygon fill.
    sources = queries.sources(['cls_poi_cafe', 'cls_landcover_wood', 'cls_road_primary'],
                              present_fixture(), params.bands, 18, mode='fill')
    tables = {s.table for s in sources}
    assert 'osm_line' in tables
    assert {'osm_polygon', 'osm_polygon_z12', 'osm_polygon_z9', 'osm_polygon_z6'} <= tables


def test_the_mode_restricts_which_tables_are_candidates(params):
    """A fill layer must never read osm_label, which has no `minzoom`.

    Only found by loading the generated XML in Mapnik: cls_landcover_wood is in
    osm_polygon *and* osm_label, and intersecting with every table picked
    up both.
    """
    sources = queries.sources(['cls_landcover_wood'], present_fixture(), params.bands,
                              18, mode='fill')
    assert 'osm_label' not in {s.table for s in sources}

    labels = queries.sources(['cls_landcover_wood'], present_fixture(), params.bands,
                             18, mode='label')
    assert 'osm_label' in {s.table for s in labels}
    assert 'osm_polygon' not in {s.table for s in labels}


def test_marker_mode_reads_only_the_point_table(params):
    sources = queries.sources(['cls_poi_cafe'], present_fixture(), params.bands,
                              18, mode='marker')
    assert {s.table for s in sources} == {'osm_point'}


def test_a_class_not_in_a_table_produces_no_source(params):
    sources = queries.sources(['cls_poi_cafe'], present_fixture(), params.bands,
                              18, mode='marker')
    assert 'osm_building' not in {s.table for s in sources}


def test_only_banded_tables_get_bands(params):
    sources = queries.sources(['cls_poi_cafe'], present_fixture(), params.bands,
                              18, mode='marker')
    assert len(sources) == 1
    assert (sources[0].min_zoom, sources[0].max_zoom) == (0, 18)


def test_a_source_carries_only_the_classes_that_table_holds(params):
    sources = queries.sources(['cls_poi_cafe', 'cls_road_primary'], present_fixture(),
                              params.bands, 18, mode='fill')
    by_table = {s.table: s.classes for s in sources}
    assert by_table['osm_line'] == ('cls_road_primary',)
    assert 'osm_point' not in by_table      # fill does not read points


def test_text_modes_are_the_ones_that_read_labels(params):
    for mode in ('label', 'shield'):
        sources = queries.sources(['cls_landcover_wood'], present_fixture(),
                                  params.bands, 18, mode=mode)
        assert all(s.text and s.descending for s in sources)
    for mode in ('fill', 'line', 'casing', 'marker'):
        sources = queries.sources(['cls_landcover_wood', 'cls_poi_cafe', 'cls_road_primary'],
                                  present_fixture(), params.bands, 18, mode=mode)
        assert all(not s.text and not s.descending for s in sources)


# --- the SQL -------------------------------------------------------------

def source(**kw) -> Source:
    base = dict(table='osm_line', classes=('cls_road_primary',), text=False,
                descending=False, min_zoom=13, max_zoom=18)
    return Source(**{**base, **kw})


def test_the_bbox_is_inside_the_subquery():
    # Outside it, Mapnik's own clause filters only after the subquery has
    # produced every row of the class at that zoom -- a table scan a tile.
    statement = queries.sql('sh', source())
    assert '!bbox!' in statement
    assert statement.index('!bbox!') < statement.index('order by')


def test_drawn_layers_filter_on_minzoom():
    statement = queries.sql('sh', source())
    assert 'minzoom <=' in statement and 'minzoom_label' not in statement
    assert 'order by z_order asc' in statement


def test_text_layers_filter_on_minzoom_label_and_sort_descending():
    # Descending so the larger place wins the collision test.
    statement = queries.sql('sh', source(table='osm_label', text=True, descending=True))
    assert 'minzoom_label is not null and minzoom_label <=' in statement
    assert 'order by z_order desc' in statement
    assert 'name, label' in statement


def test_a_label_yields_to_its_icon_from_where_the_icon_starts():
    statement = queries.sql('sh', source(table='osm_label', text=True, icon_zooms=((80, 14),),
                                         yields=('cls_landuse_hospital',)))
    floor = queries.importance_floor(((80, 14),))
    assert (f"and (class not in ('cls_landuse_hospital') or icon is null"
            f" or importance < {floor})") in statement


def test_a_number_layer_reads_only_rows_with_a_label():
    # A building without a house number draws no number and is not fetched.
    sources = queries.sources(('cls_building',), {'osm_label': {'cls_building': 1}}, (), 18,
                              mode='number')
    assert [s.table for s in sources] == ['osm_label']
    statement = queries.sql('sh', sources[0])
    assert 'minzoom_label <=' in statement and 'and label is not null' in statement
    assert 'and label is not null' not in queries.sql('sh', source(table='osm_label', text=True))


def test_a_label_without_an_icon_class_does_not_yield():
    statement = queries.sql('sh', source(table='osm_label', text=True, icon_zooms=((80, 14),)))
    assert 'importance' not in statement


def test_markers_come_most_important_first():
    """Markers do not overlap: the first one placed keeps its spot, so the
    order of the rows decides which of two neighbouring POIs is drawn."""
    statement = queries.sql('sh', source(table='osm_point', classes=('cls_poi_food',), icon=True,
                                         icon_zooms=((100, 12), (60, 15))))
    # `name` for the shield: the icon's label is drawn with it -- none
    # without `label_zooms`, so every icon is bare.
    assert 'class, icon, case when importance >= 101 then name end as name, geom' in statement
    # An undrawn category has no icon and is not fetched at all.
    assert 'icon is not null and importance >= (case ' in statement
    # Of two equally important, the named one: an unnamed icon never gets a label.
    assert 'order by importance desc, name is null, z_order asc' in statement


def test_an_icon_marker_is_drawn_by_importance_not_by_the_class_minzoom():
    # The class minzoom would hide every POI below z14 whatever the detail says.
    statement = queries.sql('sh', source(table='osm_point', classes=('cls_poi_food',), icon=True,
                                         icon_zooms=((100, 12),)))
    assert 'minzoom' not in statement


def test_no_icon_zooms_means_no_icon():
    assert queries.importance_floor(()) == '101'


@pytest.mark.parametrize('zoom,floor', [(11, 101), (12, 100), (13, 100), (14, 80), (15, 60),
                                        (16, 60), (17, 20), (18, 20)])
def test_the_importance_floor_steps_down_with_the_zoom(db, zoom, floor):
    """Round-trip through Postgres, like the zoom expression it is built on.

    An icon starts at the zoom of the highest entry its importance reaches:
    80 at z14, and a 90 too, because it reaches 80 and not 100.
    """
    expression = queries.importance_floor(((100, 12), (80, 14), (60, 15), (20, 17))).replace(
        '!scale_denominator!', repr(queries.scale_denominator(zoom)))
    assert db.execute(f'select {expression}').fetchone()[0] == floor


def test_none_of_the_expressions_the_importer_removed_come_back():
    for statement in (queries.sql('sh', source()),
                      queries.sql('sh', source(table='osm_label', text=True))):
        for banned in ('!pixel_width!', 'way_area', 'case ', 'coalesce', 'st_simplify'):
            assert banned not in statement.lower(), banned


@pytest.mark.parametrize('bad', ['sh; drop table x', "a' or '1'='1", 'Sh', '1abc', '', 'a-b'])
def test_names_that_are_not_identifiers_are_refused(bad):
    with pytest.raises(ValueError, match='not a plain identifier'):
        queries.check_name(bad)


def test_a_bad_class_name_is_refused_before_it_reaches_sql():
    with pytest.raises(ValueError, match='not a plain identifier'):
        queries.sql('sh', source(classes=("road'; drop table sh.osm_line; --",)))


# --- against the real schema ---------------------------------------------

def explain(db, statement: str, bbox: str, zoom: int) -> str:
    """Run the datasource query the way Mapnik would.

    Mapnik substitutes both tokens before the query ever reaches Postgres;
    a test that substitutes only one is testing a query that never runs.
    """
    inner = (statement
             .replace('!bbox!', bbox)
             .replace('!scale_denominator!', repr(queries.scale_denominator(zoom)))
             .removeprefix('(').removesuffix(') as t'))
    rows = db.execute(f'explain (analyze, buffers) {inner}').fetchall()
    return '\n'.join(r[0] for r in rows)


@pytest.fixture
def imported(db, small):
    return small


def test_the_generated_sql_uses_the_geometry_index(db, imported):
    # A tile-sized box at z14 must not read the table sequentially.
    box = "st_makeenvelope(1060000, 5930000, 1065000, 5935000, 3857)"
    statement = queries.sql(imported, source(classes=('cls_road_primary', 'cls_road_secondary')))
    plan = explain(db, statement, box, 14)
    assert 'Index' in plan or 'Bitmap' in plan, plan


def test_a_low_zoom_tile_reads_the_band_not_the_full_table(db, imported, params):
    # The whole point of the bands: a z6 tile must not touch osm_line.
    statement = queries.sql(imported, source(
        table='osm_line_z6', classes=('cls_road_motorway',), min_zoom=0, max_zoom=6))
    box = "st_makeenvelope(-2000000, 4000000, 4000000, 9000000, 3857)"
    plan = explain(db, statement, box, 6)
    assert 'osm_line_z6' in plan
    assert 'osm_line ' not in plan


def test_the_text_query_runs_against_osm_label(db, imported):
    box = "st_makeenvelope(1000000, 5900000, 1100000, 6000000, 3857)"
    statement = queries.sql(imported, source(
        table='osm_label', classes=('cls_poi_restaurant',), text=True, descending=True))
    explain(db, statement, box, 17)


def test_the_zoom_filter_actually_filters(db, imported):
    """The tile at z10 must not draw what only belongs at z14.

    This is the whole contract between the importer's minzoom column and
    the renderer, and it is invisible on a tile unless you know what should
    not be there. A wood starts at z5 by class and later by size, so its
    rows spread over the zooms.
    """
    box = "st_makeenvelope(1000000, 5900000, 1100000, 6000000, 3857)"
    statement = queries.sql(imported, source(table='osm_polygon', classes=('cls_landcover_wood',),
                                             min_zoom=0, max_zoom=18))
    counts = {}
    for zoom in (10, 14, 18):
        inner = (statement.replace('!bbox!', box)
                 .replace('!scale_denominator!', repr(queries.scale_denominator(zoom)))
                 .removeprefix('(').removesuffix(') as t'))
        counts[zoom] = db.execute(f'select count(*) from ({inner}) x').fetchone()[0]
    assert counts[10] < counts[14] <= counts[18]


def test_the_importance_floor_actually_filters(db, imported):
    """An icon query returns only rows at or above the zoom's floor, and
    more of them as the zoom rises -- the contract between importance.yaml,
    details.yaml `symbols.icons` and the tile."""
    box = "st_makeenvelope(1000000, 5900000, 1100000, 6000000, 3857)"
    icon_zooms = ((100, 12), (80, 14), (60, 15), (40, 16), (20, 17))
    classes = tuple(c for (c,) in db.execute(
        f"select distinct class from {imported}.osm_point where class like 'cls_poi_%'"))
    statement = queries.sql(imported, source(table='osm_point', classes=classes, icon=True,
                                             icon_zooms=icon_zooms, min_zoom=0, max_zoom=18))
    counts = {}
    for zoom, floor in ((11, 101), (14, 80), (16, 40), (18, 20)):
        inner = (statement.replace('!bbox!', box)
                 .replace('!scale_denominator!', repr(queries.scale_denominator(zoom)))
                 .replace('select class, icon, case when importance >= 101 then name end as name, geom',
                          'select importance')
                 .removeprefix('(').removesuffix(') as t'))
        rows = db.execute(f'select count(*), min(importance) from ({inner}) x').fetchone()
        counts[zoom] = rows[0]
        assert rows[1] is None or rows[1] >= floor, (zoom, rows)
    assert counts[11] == 0
    assert counts[14] <= counts[16] <= counts[18]
    assert counts[18] > counts[14]


def test_the_label_floor_actually_filters(db, imported):
    """An icon's label comes with the row only at or above the label floor
    of the tile's zoom (details.yaml `symbols.labels`); below it the name is
    NULL and the rule draws the bare icon."""
    box = "st_makeenvelope(1000000, 5900000, 1100000, 6000000, 3857)"
    classes = tuple(c for (c,) in db.execute(
        f"select distinct class from {imported}.osm_point where class like 'cls_poi_%'"))
    statement = queries.sql(imported, source(table='osm_point', classes=classes, icon=True,
                                             icon_zooms=((1, 12),), label_zooms=((80, 14), (20, 17)),
                                             min_zoom=0, max_zoom=18))
    labelled = {}
    for zoom, floor in ((13, 101), (14, 80), (18, 20)):
        inner = (statement.replace('!bbox!', box)
                 .replace('!scale_denominator!', repr(queries.scale_denominator(zoom)))
                 .removeprefix('(').removesuffix(') as t'))
        rows = db.execute(f'select count(*), min(importance) from ({inner}) x'
                          f' join {imported}.osm_point p using (geom)'
                          f' where x.name is not null').fetchone()
        labelled[zoom] = rows[0]
        assert rows[1] is None or rows[1] >= floor, (zoom, rows)
    assert labelled[13] == 0
    assert 0 < labelled[14] < labelled[18]

