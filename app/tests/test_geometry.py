"""Projection, anchors and serialisation.

The projection is hand-written rather than delegated to pyproj, so it is
pinned against two independent references: the closed-form values at the
corners of the Web Mercator square, and pyosmium's own C++
lonlat_to_mercator, which the importer does not use but which computes the
same thing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import shapely

from importer import geometry as g

#: Half the side of the Web Mercator square: the x of 180 E, and the y of
#: the cut-off latitude.
EDGE = 20037508.342789244


def test_origin():
    # Not bit-exact: log(tan(pi/4)) is 1.7e-16 rather than 0, which the
    # earth radius scales to about a tenth of a nanometre.
    assert g.mercator(np.array([[0.0, 0.0]]))[0] == pytest.approx([0.0, 0.0], abs=1e-6)


def test_corners():
    out = g.mercator(np.array([[180.0, g.LAT_MAX], [-180.0, -g.LAT_MAX]]))
    assert out[0] == pytest.approx([EDGE, EDGE], abs=1e-3)
    assert out[1] == pytest.approx([-EDGE, -EDGE], abs=1e-3)


def test_square():
    # The projection is only useful because the square is square.
    x = g.mercator(np.array([[180.0, 0.0]]))[0][0]
    y = g.mercator(np.array([[0.0, g.LAT_MAX]]))[0][1]
    assert x == pytest.approx(y, abs=1e-3)


def test_poles_clamp_instead_of_running_away():
    # A node exactly at the pole is real in OSM data; without the clamp
    # log(tan(pi/2)) is inf and the row becomes an invalid geometry.
    out = g.mercator(np.array([[0.0, 90.0], [0.0, -90.0], [0.0, 89.999]]))
    assert np.isfinite(out).all()
    assert out[0][1] == pytest.approx(EDGE, abs=1e-3)
    assert out[1][1] == pytest.approx(-EDGE, abs=1e-3)


def test_agrees_with_pyosmium():
    """libosmium computes the same projection a slightly different way.

    Agreement is to about 0.1 mm, not to the last bit -- which is four
    orders of magnitude below the ~0.6 m that one pixel covers at z18, so
    it can never move a vertex into a different pixel.
    """
    osmium_geom = pytest.importorskip('osmium.geom')
    points = [(9.5, 54.5), (10.0, 54.0), (8.3, 53.4), (11.3, 55.0), (0.0, 0.0), (13.4, 52.5)]
    ours = g.mercator(np.array(points, dtype=float))
    for (lon, lat), (x, y) in zip(points, ours, strict=False):
        theirs = osmium_geom.lonlat_to_mercator(osmium_geom.Coordinates(lon, lat))
        assert x == pytest.approx(theirs.x, abs=1e-3)
        assert y == pytest.approx(theirs.y, abs=1e-3)


def test_x_is_linear_in_longitude():
    # Which is why a degree cell converts to 3857 metres exactly, and the
    # band builds can express their grid that way.
    a = g.mercator(np.array([[1.0, 0.0]]))[0][0]
    b = g.mercator(np.array([[2.0, 0.0]]))[0][0]
    assert b == pytest.approx(2 * a)


def test_latitude_inflation_at_54n():
    # The factor that makes 3857 area larger than ground area in the test
    # area, and the reason sizes are measured after projection.
    y1 = g.mercator(np.array([[0.0, 54.0]]))[0][1]
    y2 = g.mercator(np.array([[0.0, 54.001]]))[0][1]
    metres_per_degree = (y2 - y1) / 0.001
    expected = math.radians(1.0) * g.EARTH_RADIUS / math.cos(math.radians(54.0))
    assert metres_per_degree == pytest.approx(expected, rel=1e-4)


def test_batch_projection_matches_per_geometry():
    lines = [shapely.LineString([(9.0 + i, 54.0), (9.5 + i, 54.5)]) for i in range(5)]
    batched = g.to_3857(lines)
    for line, projected in zip(lines, batched, strict=False):
        one = g.to_3857([line])[0]
        assert shapely.equals_exact(projected, one, tolerance=1e-9)


def test_batch_handles_mixed_types():
    mixed = [shapely.Point(9.0, 54.0),
             shapely.LineString([(9.0, 54.0), (9.1, 54.1)]),
             shapely.Polygon([(9.0, 54.0), (9.1, 54.0), (9.1, 54.1), (9.0, 54.0)])]
    out = g.to_3857(mixed)
    assert [shapely.get_type_id(x) for x in out] == [shapely.get_type_id(x) for x in mixed]
    assert all(shapely.is_valid(x) for x in out)


def test_round_trip_through_wkb():
    point = shapely.Point(9.5, 54.5)
    assert shapely.equals(g.from_wkb([shapely.to_wkb(point, hex=True)])[0], point)


def test_hex_ewkb_carries_the_srid():
    encoded = g.hex_ewkb([shapely.Point(1.0, 2.0)], 3857)[0]
    # 0020 in the type word is the SRID flag; 110F is 3857 little-endian.
    assert encoded.startswith('0101000020110F0000')
    decoded = shapely.from_wkb(encoded)
    assert (decoded.x, decoded.y) == (1.0, 2.0)


@pytest.mark.parametrize('geometry,expected', [
    (shapely.Point(3, 4), (3, 4)),
    (shapely.LineString([(0, 0), (10, 0)]), (5, 0)),
    (shapely.LineString([(0, 0), (0, 10), (10, 10)]), (0, 10)),   # along the line, not the bbox
    (shapely.Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]), (2, 2)),
])
def test_label_anchor(geometry, expected):
    anchor = g.label_anchor(geometry)
    assert (anchor.x, anchor.y) == pytest.approx(expected)


def test_label_anchor_of_a_horseshoe_is_inside_it():
    # The reason it is point-on-surface and not the centroid.
    horseshoe = shapely.Polygon([(0, 0), (10, 0), (10, 10), (7, 10), (7, 3),
                                 (3, 3), (3, 10), (0, 10)])
    assert shapely.contains(horseshoe, g.label_anchor(horseshoe))
    assert not shapely.contains(horseshoe, shapely.centroid(horseshoe))


def test_polygon_parts():
    single = shapely.Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    assert g.polygon_parts(single) == [single]

    multi = shapely.MultiPolygon([
        [[(0, 0), (1, 0), (1, 1), (0, 0)], []],
        [[(5, 5), (6, 5), (6, 6), (5, 5)], []],
    ])
    parts = g.polygon_parts(multi)
    assert len(parts) == 2
    assert all(shapely.get_type_id(p) == 3 for p in parts)


def test_polygon_parts_keep_their_holes():
    ring = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(2, 2), (4, 2), (4, 4), (2, 4)]
    donut = shapely.Polygon(ring, [hole])
    part = g.polygon_parts(donut)[0]
    assert shapely.get_num_interior_rings(part) == 1
    assert part.area == pytest.approx(100 - 4)
