"""Band tables.

The case that matters: OSM splits a
road into a way per junction, so every individual motorway way fails the
size test at low zoom even though the motorway obviously belongs on a z6
map. Selecting lines on the row's own minzoom left 36 lines in _z6 for the
whole of Schleswig-Holstein. They are selected by the class's minzoom
instead, and the size test is applied to the merged run.
"""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

import copy  # noqa: E402

import shapely  # noqa: E402

from importer import postprocess  # noqa: E402
from importer import tables as t  # noqa: E402
from importer.writer import TableWriter  # noqa: E402


def starting(params, class_minzoom):
    """The params with only the band build's input replaced: which zoom each
    class starts at (classes.yaml, through `Params.class_minzoom`)."""
    out = copy.copy(params)
    out.class_minzoom = class_minzoom
    return out


@pytest.fixture
def banded(db, temp_schema, params):
    for table in (t.OSM_LINE, t.OSM_POLYGON):
        db.execute(t.ddl(temp_schema, table))
    for base in t.BANDED:
        for band in params.bands:
            db.execute(t.ddl(temp_schema, t.band_table(base, band.suffix)))
    return temp_schema


def band(params, suffix):
    return next(b for b in params.bands if b.suffix == suffix)


def chain(x0, length, segments):
    """A road split into `segments` touching ways, as OSM stores it."""
    step = length / segments
    return [shapely.LineString([(x0 + i * step, 0), (x0 + (i + 1) * step, 0)])
            for i in range(segments)]


def test_a_segmented_road_reaches_the_lowest_band(db, banded, params):
    # 40 km of motorway as 100 short ways. Every way's own minzoom is 14 --
    # none of them would pass a row-level filter at z6.
    writer = TableWriter(db, banded, t.OSM_LINE)
    for i, segment in enumerate(chain(0.0, 40_000.0, 100)):
        writer.add((i, 'cls_road_motorway', None, None, 90, 14, None, segment))
    writer.close()

    starts = starting(params, {'cls_road_motorway': 5})
    rows = postprocess.band_lines(db, banded, starts, band(params, '_z6'))

    assert rows >= 1
    total = db.execute(f'select sum(st_length(geom)) from {banded}.osm_line_z6').fetchone()[0]
    assert total == pytest.approx(40_000.0, rel=0.01)
    # The 100 fragments came back as one run.
    assert db.execute(f'select count(*) from {banded}.osm_line_z6').fetchone()[0] == 1


def test_a_merged_run_is_drawable_at_its_class_zoom(db, banded, params):
    """Being *in* the band is not being on the map.

    The render query filters `minzoom <= z`. A merged run that keeps
    min() of its ways' minzooms -- 14 here, the short ways the merge exists
    to rescue -- sits in _z6 and is drawn at no zoom _z6 serves. On
    `de_sh` that was every motorway and trunk run and the national border,
    at z5 and z6. The test above checks the table and passes either way.
    """
    writer = TableWriter(db, banded, t.OSM_LINE)
    for i, segment in enumerate(chain(0.0, 40_000.0, 100)):
        writer.add((i, 'cls_road_motorway', None, None, 90, 14, None, segment))
    writer.close()

    starts = starting(params, {'cls_road_motorway': 5})
    postprocess.band_lines(db, banded, starts, band(params, '_z6'))
    (minzoom,) = db.execute(f'select minzoom from {banded}.osm_line_z6').fetchone()
    assert minzoom == 5


def test_a_merged_run_is_not_held_to_the_per_way_length_rule(db, banded, params):
    """Selected by class, so shown by class; the pixel filter is the size test.

    The per-way rule wanted 8 px, which at z5 is 39 km -- and once
    ST_LineMerge has broken a motorway at every ramp and the grid has cut
    it at every cell edge, almost no run is that long. Applying it to the
    merged length hid 906 of `de_sh`'s 1 157 motorway runs in _z9.
    """
    length = 10_000.0          # far under 8 px at z5, far over a pixel at z6
    assert params.size_minzoom_length(length, 8) > 6
    writer = TableWriter(db, banded, t.OSM_LINE)
    for i, segment in enumerate(chain(0.0, length, 10)):
        writer.add((i, 'cls_road_motorway', None, None, 90, 14, None, segment))
    writer.close()

    starts = starting(params, {'cls_road_motorway': 5})
    postprocess.band_lines(db, banded, starts, band(params, '_z6'))
    (minzoom,) = db.execute(f'select minzoom from {banded}.osm_line_z6').fetchone()
    assert minzoom == 5


def test_a_class_above_the_band_is_not_selected(db, banded, params):
    writer = TableWriter(db, banded, t.OSM_LINE)
    for i, segment in enumerate(chain(0.0, 40_000.0, 10)):
        writer.add((i, 'cls_road_service', None, None, 50, 14, None, segment))
    writer.close()

    starts = starting(params, {'cls_road_service': 14})
    assert postprocess.band_lines(db, banded, starts, band(params, '_z6')) == 0


def test_a_short_merged_run_is_dropped(db, banded, params):
    # Below one pixel at the band's finest zoom, even after merging.
    pixel = 2 * band(params, '_z6').tolerance_m
    writer = TableWriter(db, banded, t.OSM_LINE)
    writer.add((1, 'cls_road_motorway', None, None, 90, 5, None,
                shapely.LineString([(0, 0), (pixel * 0.4, 0)])))
    writer.close()

    starts = starting(params, {'cls_road_motorway': 5})
    assert postprocess.band_lines(db, banded, starts, band(params, '_z6')) == 0


def test_z12_keeps_one_row_per_way(db, banded, params):
    # No union at z12, so the osm_id link to the search tables survives.
    writer = TableWriter(db, banded, t.OSM_LINE)
    for i, segment in enumerate(chain(0.0, 40_000.0, 5)):
        writer.add((100 + i, 'cls_road_motorway', 'A7', 'A7', 90, 8, 10, segment))
    writer.close()

    starts = starting(params, {'cls_road_motorway': 5})
    postprocess.band_lines(db, banded, starts, band(params, '_z12'))
    rows = db.execute(
        f'select osm_id, name from {banded}.osm_line_z12 order by osm_id').fetchall()
    assert [r[0] for r in rows] == [100, 101, 102, 103, 104]
    assert all(r[1] == 'A7' for r in rows)


def test_unioned_rows_lose_their_identity(db, banded, params):
    # A union of many objects has no single id or name, so those columns are
    # empty in _z9 and _z6 -- true of the bands that union, not of _z12.
    writer = TableWriter(db, banded, t.OSM_POLYGON)
    side = 4000.0
    for i in range(4):
        x = i * side
        writer.add((i, 'cls_landcover_wood', f'Forst {i}', None, 0, 5, None,
                    shapely.Polygon([(x, 0), (x + side, 0), (x + side, side), (x, side)])))
    writer.close()

    postprocess.band_polygons(db, banded, params, band(params, '_z9'))
    rows = db.execute(
        f'select osm_id, name, class from {banded}.osm_polygon_z9').fetchall()
    assert rows and all(r[0] == 0 and r[1] is None and r[2] == 'cls_landcover_wood' for r in rows)
    # Four touching squares of one class become one shape.
    assert len(rows) == 1


def test_polygons_are_selected_on_their_own_minzoom(db, banded, params):
    # Unlike a road, a small lake really is small: the row's minzoom is the
    # property the threshold is about.
    writer = TableWriter(db, banded, t.OSM_POLYGON)
    writer.add((1, 'cls_water_lake', None, None, 0, 14, None,
                shapely.Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])))
    writer.close()
    assert postprocess.band_polygons(db, banded, params, band(params, '_z6')) == 0


def test_band_output_is_valid_and_typed(db, banded, params):
    writer = TableWriter(db, banded, t.OSM_POLYGON)
    side = 8000.0
    writer.add((1, 'cls_landcover_wood', None, None, 0, 5, None,
                shapely.Polygon([(0, 0), (side, 0), (side, side), (0, side)])))
    writer.close()
    postprocess.band_polygons(db, banded, params, band(params, '_z6'))
    bad = db.execute(
        f'select count(*) from {banded}.osm_polygon_z6'
        f" where not st_isvalid(geom) or st_geometrytype(geom) <> 'ST_Polygon'").fetchone()[0]
    assert bad == 0
