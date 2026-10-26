"""Tile grids.

A grid is a public addressing scheme: once a client has stored a URL or a
tile is in the cache, moving the grid breaks both silently. So the numbers
are declared, and these tests pin them -- including that EPSG:3857 comes
out of the generic builder identical to the OGC well-known set rather than
being special-cased into it.
"""

from __future__ import annotations

import math

import pytest

from renderer import matrix, queries

WEB_MERCATOR_EDGE = 20037508.342789244

GRIDS = {
    'GoogleMapsCompatible': {'crs': 'EPSG:3857',
                                 'origin': [-WEB_MERCATOR_EDGE, WEB_MERCATOR_EDGE],
                                 'span': 2 * WEB_MERCATOR_EDGE, 'levels': 19, 'centre_lat': 0},
    'DE_EPSG_25832_ADV': {'crs': 'EPSG:25832', 'origin': [-46133.17, 6301219.54],
                          'span': 1252344.2714243277, 'levels': 15, 'centre_lat': 51.0},
}


@pytest.fixture
def sets():
    return matrix.load(list(GRIDS), GRIDS)


@pytest.fixture
def web(sets):
    return sets['GoogleMapsCompatible']


@pytest.fixture
def utm(sets):
    return sets['DE_EPSG_25832_ADV']


# --- the well-known set --------------------------------------------------

def test_web_mercator_reproduces_googlemapscompatible(web):
    """The generic builder must produce the standard set exactly.

    Every WMTS client has these numbers; being close is not enough.
    """
    assert web.identifier == 'GoogleMapsCompatible'
    assert web.matrix(0).scale_denominator == pytest.approx(559_082_264.0287178)
    assert web.matrix(1).scale_denominator == pytest.approx(279_541_132.0143589)
    assert web.matrix(18).scale_denominator == pytest.approx(2132.7295, rel=1e-6)


def test_level_n_is_xyz_zoom_n(web):
    # What makes /xyz/ the EPSG:3857 case of /wmts/ rather than a second
    # grid that happens to look similar.
    for zoom in range(19):
        assert web.matrix(zoom).scale_denominator == pytest.approx(
            queries.scale_denominator(zoom))


def test_the_whole_world_is_one_tile_at_level_zero(web):
    assert web.matrix(0).matrix_width == web.matrix(0).matrix_height == 1
    assert web.bbox(0, 0, 0) == pytest.approx(
        (-WEB_MERCATOR_EDGE, -WEB_MERCATOR_EDGE, WEB_MERCATOR_EDGE, WEB_MERCATOR_EDGE))


def test_rows_count_down_from_the_top(web):
    # Row 0 is the north half, which is what both WMTS and XYZ mean.
    _, _, _, top = web.bbox(1, 0, 0)
    _, bottom, _, _ = web.bbox(1, 0, 1)
    assert top == pytest.approx(WEB_MERCATOR_EDGE)
    assert bottom == pytest.approx(-WEB_MERCATOR_EDGE)


def test_a_point_round_trips_through_its_tile(web):
    # Triesen, the area test_core renders. Computed, not asserted from
    # memory: the tile a point is in and the bbox of that tile have to be
    # inverses or a click lands on the wrong tile.
    point = (1_062_500.0, 5_957_500.0)
    for level in range(19):
        col, row = web.tile_for(level, *point)
        left, bottom, right, top = web.bbox(level, col, row)
        assert left <= point[0] <= right
        assert bottom <= point[1] <= top
        assert right - left == pytest.approx(top - bottom)


def test_tiles_in_covers_a_bbox(web):
    box = (1_060_000.0, 5_955_000.0, 1_065_000.0, 5_960_000.0)
    tiles = list(web.tiles_in(13, box))
    assert tiles
    # Every returned tile touches the box, and the corners are included.
    for col, row in tiles:
        left, bottom, right, top = web.bbox(13, col, row)
        assert left < box[2] and right > box[0]
        assert bottom < box[3] and top > box[1]
    assert web.tile_for(13, box[0], box[3]) in tiles
    assert web.tile_for(13, box[2], box[1]) in tiles


def test_tiles_in_is_clipped_to_the_grid(web):
    # A bbox larger than the world must not produce negative indices.
    huge = (-9e7, -9e7, 9e7, 9e7)
    tiles = list(web.tiles_in(2, huge))
    assert len(tiles) == 16
    assert all(0 <= c < 4 and 0 <= r < 4 for c, r in tiles)


def test_the_far_edge_belongs_to_the_last_tile(web):
    # Otherwise a point exactly on the boundary addresses a tile that does
    # not exist.
    assert web.tile_for(1, WEB_MERCATOR_EDGE, -WEB_MERCATOR_EDGE) == (1, 1)


def test_the_quadtree_doubles(web):
    for level in range(1, 19):
        assert web.matrix(level).matrix_width == 2 ** level
        assert web.tile_span(level) == pytest.approx(web.tile_span(level - 1) / 2)


def test_four_children_tile_their_parent(web):
    parent = web.bbox(5, 10, 12)
    children = [web.bbox(6, 20 + dx, 24 + dy) for dx in (0, 1) for dy in (0, 1)]
    assert min(c[0] for c in children) == pytest.approx(parent[0])
    assert max(c[2] for c in children) == pytest.approx(parent[2])
    assert min(c[1] for c in children) == pytest.approx(parent[1])
    assert max(c[3] for c in children) == pytest.approx(parent[3])


# --- the UTM set ---------------------------------------------------------

#: What basemap.de's capabilities advertise for the AdV sets: the top-left
#: corner, and the scale denominators of levels 00, 08 and 13.
ADV = {
    'DE_EPSG_25832_ADV': (-46133.17, 6301219.54),
    'DE_EPSG_25833_ADV': (-464849.38, 6310160.14),
}
ADV_SCALES = {0: 17471320.750897426, 8: 68247.3466831932, 13: 2132.729583849782}


@pytest.mark.parametrize('identifier', sorted(ADV))
def test_the_utm_grids_are_the_adv_sets(identifier):
    """Our tiles must align with the AdV services' tile for tile; a set
    that is merely close puts every tile beside theirs."""
    tms = matrix.load()[identifier]
    for level, scale in ADV_SCALES.items():
        tm = tms.matrix(level)
        assert tm.identifier == f'{level:02d}'
        assert tm.top_left == ADV[identifier]
        assert tm.scale_denominator == pytest.approx(scale, rel=1e-12)
        assert tm.matrix_width == tm.matrix_height == 2 ** level


def test_web_mercator_identifiers_are_not_padded(web):
    # The OGC well-known set numbers its levels 0, 1, ...
    assert web.matrix(8).identifier == '8'


def test_the_utm_grid_contains_germany(utm):
    # Germany in EPSG:25832: easting ~257k-962k, northing ~5232k-6123k.
    left, bottom, right, top = utm.bbox(0, 0, 0)
    assert left <= 257_000 and right >= 962_000
    assert bottom <= 5_232_000 and top >= 6_123_000


def test_utm_and_web_mercator_levels_are_not_the_same_scale(utm, web):
    # Which is the whole reason a level is not a zoom.
    assert utm.matrix(8).scale_denominator != pytest.approx(
        web.matrix(8).scale_denominator)


# --- the metres factor ---------------------------------------------------

def test_web_mercator_needs_no_correction(web):
    # Its units already are Web Mercator units, at every latitude.
    assert web.metres_factor == pytest.approx(1.0)


def test_a_true_metre_crs_is_corrected_for_its_latitude(utm):
    assert utm.metres_factor == pytest.approx(math.cos(math.radians(51.0)))


def test_the_factor_maps_a_level_onto_the_zoom_minzoom_is_written_in(db, utm):
    """The connection between a grid level and the importer's columns.

    `minzoom` is an EPSG:3857 zoom. A UTM level has to be converted, or a
    UTM tile draws the wrong detail.
    """
    expression = queries.zoom_expression(utm.metres_factor).replace(
        '!scale_denominator!', repr(utm.matrix(8).scale_denominator))
    zoom = db.execute(f'select {expression}').fetchone()[0]
    # 19 m/px of ground at 51 N is about 30 Web Mercator units per pixel, z12.3.
    assert zoom == 12


# --- errors --------------------------------------------------------------

def test_a_tile_outside_the_grid_is_refused(web):
    with pytest.raises(ValueError, match='outside'):
        web.bbox(1, 2, 0)
    with pytest.raises(ValueError, match='outside'):
        web.bbox(1, 0, -1)


def test_an_unknown_level_names_the_range(web):
    with pytest.raises(ValueError, match='levels 0-18'):
        web.matrix(19)


def test_a_served_grid_without_a_declaration_is_refused():
    """Otherwise it is advertised and then 404s on every tile.

    A client that reads GetCapabilities and gets nothing back has no way
    to tell that from an outage.
    """
    with pytest.raises(ValueError, match='no entry in grids.yaml'):
        matrix.load(['GoogleMapsCompatible', 'GK3'], GRIDS)


def test_an_incomplete_grid_names_what_is_missing():
    with pytest.raises(ValueError, match='levels'):
        matrix.from_config('grid_1', {'crs': 'EPSG:1234', 'origin': [0, 0],
                                      'span': 1.0, 'centre_lat': 0})


# --- the real configuration ----------------------------------------------

def test_the_served_grids_are_all_declared():
    sets = matrix.load()
    assert set(sets) == {'GoogleMapsCompatible', 'DE_EPSG_25832_ADV', 'DE_EPSG_25833_ADV'}


def test_by_crs_finds_the_grid_in_that_crs(sets):
    assert matrix.by_crs(sets, 'EPSG:25832').identifier == 'DE_EPSG_25832_ADV'
    assert matrix.by_crs(sets, 'EPSG:31467') is None
    assert matrix.by_crs(matrix.load(), 'EPSG:25833').identifier == 'DE_EPSG_25833_ADV'


#: Germany's corners in EPSG:25833 (gdaltransform from 5.87-15.04 E,
#: 47.27-55.06 N): its west lies far west of the zone's false origin.
GERMANY_25833 = (-190370.1, 5235169.7, 503025.7, 6139634.4)


def test_utm33n_contains_germany():
    """A grid is fixed once clients store its URLs, so its origin has to
    leave room: a tile outside the pyramid is a 404, and an origin of 0
    would cut off everything west of 15 E minus 500 km."""
    xmin, ymin, xmax, ymax = matrix.load()['DE_EPSG_25833_ADV'].bbox(0, 0, 0)
    west, south, east, north = GERMANY_25833
    assert xmin < west and ymin < south and east < xmax and north < ymax


def test_the_precache_depths_are_within_the_declared_levels():
    from lib import config

    sets = matrix.load()
    for identifier, depth in (config.opt('precache') or {}).items():
        assert depth < sets[identifier].levels, f'{identifier} pre-caches deeper than its grid goes'
