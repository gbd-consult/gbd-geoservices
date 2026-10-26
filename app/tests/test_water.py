"""Water polygons.

OSM has no ocean polygons, only `natural=coastline` ways, so without this
path the sea is not drawn at all (DESIGN.md "Principles"). The fixture is
written rather than checked in: a shapefile is four binary files, and
generating one keeps the intent readable.
"""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

import shapefile  # noqa: E402
import shapely  # noqa: E402

from importer import tables as t  # noqa: E402
from importer import water  # noqa: E402

#: Somewhere in the North Sea, in 3857 units.
WEST, SOUTH = 800_000.0, 7_000_000.0
SIZE = 100_000.0


def square(x, y, size=SIZE):
    return [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]


@pytest.fixture
def shp(tmp_path):
    """Three polygons: two inside the test bbox, one far outside."""
    path = tmp_path / 'water.shp'
    writer = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    writer.field('FID', 'N')
    for index, (x, y) in enumerate([(WEST, SOUTH),
                                    (WEST + SIZE, SOUTH),
                                    (WEST + 5_000_000.0, SOUTH)]):
        writer.poly(square(x, y))
        writer.record(index)
    writer.close()
    return path


BBOX = (WEST - 1000.0, SOUTH - 1000.0, WEST + 2 * SIZE + 1000.0, SOUTH + SIZE + 1000.0)


def test_far_polygons_are_not_read(shp):
    # The bbox filter reads each record's header box and skips the rest, so
    # the 1.27 GB full set costs a seek per tile rather than a parse.
    parts = water._clipped_parts(shp, BBOX)
    assert len(parts) == 2


def test_clipping_stays_inside_the_box(shp):
    box = shapely.box(*BBOX)
    for part in water._clipped_parts(shp, BBOX):
        assert shapely.covers(box, part)


def test_output_is_valid_polygons(shp):
    for part in water._clipped_parts(shp, BBOX):
        assert shapely.is_valid(part)
        assert shapely.get_type_id(part) == 3
        assert shapely.area(part) > 0


def test_a_polygon_crossing_the_edge_is_cut(shp):
    narrow = (WEST - 1000.0, SOUTH - 1000.0, WEST + SIZE / 2, SOUTH + SIZE + 1000.0)
    parts = water._clipped_parts(shp, narrow)
    assert parts
    assert sum(shapely.area(p) for p in parts) == pytest.approx(SIZE * SIZE / 2, rel=1e-6)


def test_load_writes_ocean_rows(db, temp_schema, shp):
    db.execute(t.ddl(temp_schema, t.OSM_POLYGON))
    rows = water.load(db, temp_schema, shp, BBOX, 1000)
    assert rows == 2
    stored = db.execute(
        f'select class, minzoom, z_order, name, st_srid(geom)'
        f' from {temp_schema}.osm_polygon').fetchall()
    assert all(r == ('cls_ocean', 0, 0, None, 3857) for r in stored)


def test_load_bands_uses_the_union_bands_only(db, temp_schema, shp, params):
    for band in params.bands:
        db.execute(t.ddl(temp_schema, t.band_table('osm_polygon', band.suffix)))
    counts = water.load_bands(db, temp_schema, shp, BBOX, params, 1000)
    # _z12 does not union, so it takes the full set from osm_polygon instead.
    assert set(counts) == {'osm_polygon_z6', 'osm_polygon_z9'}
    assert all(v > 0 for v in counts.values())


def test_ocean_class_has_no_classifier_rule(classifier):
    # Nothing in OSM carries it; the water import is what assigns it, which
    # is why classifier.yaml has no rule producing it.
    assert water.OCEAN not in {rule.cls for rule in classifier.rules if rule.cls}


def test_area_bbox_widens_the_extract_box():
    class Corner:
        def __init__(self, lon, lat):
            self.lon, self.lat = lon, lat

    class Box:
        bottom_left = Corner(8.0, 54.0)
        top_right = Corner(10.0, 55.0)

    tight = water.area_bbox(Box(), 0.0)
    wide = water.area_bbox(Box(), 0.5)
    assert wide[0] < tight[0] and wide[1] < tight[1]
    assert wide[2] > tight[2] and wide[3] > tight[3]
