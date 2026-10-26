"""Seeding the pre-cache tier.

The z0-12 pre-cache is what the band tables exist to make affordable, so
what matters here is that the run covers the right tiles, survives a bad
one, and can be interrupted and resumed without redoing work.
"""

from __future__ import annotations

import pytest

from renderer import matrix, precache
from renderer.cache import FilesystemCache, TileCacheFacade

GRIDS = {
    'GoogleMapsCompatible': {'crs': 'EPSG:3857',
                                 'origin': [-20037508.342789244, 20037508.342789244],
                                 'span': 40075016.685578488, 'levels': 19, 'centre_lat': 0},
    'DE_EPSG_25832_ADV': {'crs': 'EPSG:25832', 'origin': [-46133.17, 6301219.54],
                          'span': 1252344.2714243277, 'levels': 15, 'centre_lat': 51.0},
}

#: Liechtenstein, in 3857.
EXTENT = (1054316.0, 5949870.0, 1072699.0, 5986467.0)


class FakeRegistry:
    """Renders a deterministic byte string, or fails for chosen tiles."""

    def __init__(self, fail: set | None = None):
        self.calls: list[tuple] = []
        self.fail = fail or set()

    def render(self, theme, bbox, fmt, crs=None, matrix_set=None):
        self.calls.append((theme, bbox, fmt, crs, matrix_set))
        if len(self.calls) in self.fail:
            raise RuntimeError('render failed')
        return f'{theme}:{bbox[0]:.0f}'.encode()


@pytest.fixture
def web():
    return matrix.load(['GoogleMapsCompatible'], GRIDS)['GoogleMapsCompatible']


@pytest.fixture
def tiers(tmp_path):
    return TileCacheFacade(FilesystemCache(tmp_path / 'precache'),
                           FilesystemCache(tmp_path / 'ondemand'),
                           {'GoogleMapsCompatible': 12})


# --- CRS codes -----------------------------------------------------------

def test_srid_of():
    assert precache.srid_of('EPSG:25832') == 25832
    assert precache.srid_of('epsg:3857') == 3857


@pytest.mark.parametrize('bad', ['25832', 'ESRI:54009', '', 'EPSG:', 'EPSG:abc'])
def test_a_non_epsg_code_is_refused(bad):
    with pytest.raises(ValueError, match='not an EPSG code'):
        precache.srid_of(bad)


# --- the plan ------------------------------------------------------------

def test_the_plan_is_coarsest_first(web):
    """An interrupted run should leave a usable map.

    The low zooms are what a client reaches for first and what is most
    expensive to render on demand.
    """
    levels = [level for level, _, _ in precache.plan(web, EXTENT, 12)]
    assert levels == sorted(levels)
    assert levels[0] == 0


def test_the_plan_stops_at_the_depth(web):
    assert max(level for level, _, _ in precache.plan(web, EXTENT, 8)) == 8
    assert max(level for level, _, _ in precache.plan(web, EXTENT, 12)) == 12


def test_the_plan_never_leaves_the_grid(web):
    # A depth beyond the declared levels must clamp, not address tiles
    # that do not exist.
    tiles = list(precache.plan(web, EXTENT, 99))
    assert max(level for level, _, _ in tiles) == web.levels - 1


def test_the_plan_covers_the_extent_and_no_more(web):
    tiles = [(c, r) for level, c, r in precache.plan(web, EXTENT, 10) if level == 10]
    assert tiles
    for col, row in tiles:
        left, bottom, right, top = web.bbox(10, col, row)
        assert left < EXTENT[2] and right > EXTENT[0]
        assert bottom < EXTENT[3] and top > EXTENT[1]


def test_a_small_area_is_a_small_plan(web):
    # Liechtenstein to z12 is tens of tiles, not thousands: the check that
    # the extent is actually being used.
    assert len(list(precache.plan(web, EXTENT, 12))) < 100


# --- seeding -------------------------------------------------------------

def test_every_planned_tile_is_rendered_and_stored(web, tiers):
    registry = FakeRegistry()
    result = precache.seed(registry, tiers, web, 'default', EXTENT, 8, workers=2)

    assert result.rendered == result.tiles > 0
    assert result.failed == 0
    level, col, row = next(iter(precache.plan(web, EXTENT, 8)))
    assert tiers.get('default', web.identifier, 'png', level, col, row) is not None


def test_a_second_run_renders_nothing(web, tiers):
    """Resumable: an interrupted seed picks up where it stopped.

    A full pre-cache of a real area is minutes of work; redoing it because
    the process was restarted is the difference between usable and not.
    """
    first = precache.seed(FakeRegistry(), tiers, web, 'default', EXTENT, 8, workers=2)
    registry = FakeRegistry()
    second = precache.seed(registry, tiers, web, 'default', EXTENT, 8, workers=2)

    assert second.cached == first.rendered
    assert second.rendered == 0
    assert registry.calls == []


def test_force_re_renders_everything(web, tiers):
    precache.seed(FakeRegistry(), tiers, web, 'default', EXTENT, 8, workers=2)
    result = precache.seed(FakeRegistry(), tiers, web, 'default', EXTENT, 8,
                           workers=2, force=True)
    assert result.cached == 0 and result.rendered == result.tiles


def test_one_bad_tile_does_not_abort_the_run(web, tiers):
    # A single failing tile in a run of thousands must not lose the rest.
    registry = FakeRegistry(fail={2})
    result = precache.seed(registry, tiers, web, 'default', EXTENT, 8, workers=1)
    assert result.failed == 1
    assert result.rendered == result.tiles - 1


def test_the_render_names_the_sets_compiled_xml(web, tiers):
    """A theme is compiled once per grid, so the render has to say which
    one it wants -- the CRS alone does not pick a file."""
    registry = FakeRegistry()
    precache.seed(registry, tiers, web, 'default', EXTENT, 2, workers=1)
    assert {ms for *_, ms in registry.calls} == {web.identifier}


def test_the_tile_is_rendered_in_the_sets_own_crs(web, tiers):
    registry = FakeRegistry()
    precache.seed(registry, tiers, web, 'default', EXTENT, 2, workers=1)
    assert {crs for _, _, _, crs, _ in registry.calls} == {'epsg:3857'}


def test_the_bbox_handed_to_the_renderer_is_the_tiles_own(web, tiers):
    registry = FakeRegistry()
    precache.seed(registry, tiers, web, 'default', EXTENT, 1, workers=1)
    planned = {web.bbox(level, col, row)
               for level, col, row in precache.plan(web, EXTENT, 1)}
    assert {bbox for _, bbox, _, _, _ in registry.calls} == planned


def test_tiles_land_in_the_precache_tier_not_on_demand(web, tiers):
    precache.seed(FakeRegistry(), tiers, web, 'default', EXTENT, 8, workers=1)
    level, col, row = next(iter(precache.plan(web, EXTENT, 8)))
    key = f'default/{web.identifier}/png/{level}/{col}/{row}'
    assert tiers.precache.get(key) is not None
    assert tiers.ondemand.get(key) is None


def test_per_level_counts_are_reported(web, tiers):
    result = precache.seed(FakeRegistry(), tiers, web, 'default', EXTENT, 4, workers=1)
    assert set(result.per_level) == {0, 1, 2, 3, 4}
    assert sum(result.per_level.values()) == result.rendered


# --- the extent ----------------------------------------------------------

@pytest.fixture
def imported(db, small):
    return small


def test_the_extent_comes_from_import_meta(db, imported):
    box = precache.extent_for(db, imported, 'EPSG:3857')
    assert 1_000_000 < box[0] < box[2] < 1_200_000
    assert 5_900_000 < box[1] < box[3] < 6_100_000


def test_the_extent_is_reprojected_per_set(db, imported):
    """A UTM set needs the area in UTM, not in Web Mercator.

    Seeding a UTM grid with 3857 numbers would address tiles far outside
    the area, or none at all.
    """
    utm = precache.extent_for(db, imported, 'EPSG:25832')
    # Liechtenstein in EPSG:25832: easting ~535-548 km, northing ~5210-5236 km.
    assert 500_000 < utm[0] < utm[2] < 600_000
    assert 5_200_000 < utm[1] < utm[3] < 5_300_000


def test_an_unfinished_import_is_named(db, temp_schema):
    from importer import tables as t

    db.execute(t.ddl(temp_schema, t.IMPORT_META))
    with pytest.raises(RuntimeError, match='did not finish'):
        precache.extent_for(db, temp_schema, 'EPSG:3857')
