"""The tile cache.

Every component of a key becomes a path segment under the cache root, and
all of them arrive from a request -- so the key check is a path-traversal
guard, not tidiness. The tier split is the other thing worth testing: each
grid is pre-cached to its own depth, not to a fixed z12.
"""

from __future__ import annotations

import pytest

from renderer import cache
from renderer.cache import (
    FilesystemCache,
    InvalidTileKey,
    TileCacheFacade,
    TileKey,
    check_component,
)

#: Keyed the way the facade is really keyed: by the TileMatrixSet
#: identifier a request sends, not by the CRS code `precache:` is written
#: with. An earlier version of this file invented `EPSG3857`, which is
#: neither -- and so passed while the production wiring matched nothing.
DEPTHS = {'GoogleMapsCompatible': 12, 'DE_EPSG_25832_ADV': 8}


@pytest.fixture
def tiers(tmp_path):
    return TileCacheFacade(FilesystemCache(tmp_path / 'precache'),
                           FilesystemCache(tmp_path / 'ondemand'), DEPTHS)


# --- keys ----------------------------------------------------------------

def test_the_key_shape():
    assert str(TileKey('default', 'GoogleMapsCompatible', 'png', 12, 2200, 1345)) == \
        'default/GoogleMapsCompatible/png/12/2200/1345'


def test_every_set_caches_separately():
    # The reason the set is in the key at all: the same z/x/y in another
    # CRS is a different tile.
    a = cache.cache_key('default', 'GoogleMapsCompatible', 'png', 8, 1, 1)
    b = cache.cache_key('default', 'DE_EPSG_25832_ADV', 'png', 8, 1, 1)
    assert a != b


@pytest.mark.parametrize('bad', [
    '../../etc/passwd', 'a/b', '.', '..', '', 'a b', '/abs', 'thème',
])
def test_a_component_that_could_address_a_path_is_refused(bad):
    with pytest.raises(InvalidTileKey):
        cache.cache_key(bad, 'GoogleMapsCompatible', 'png', 1, 1, 1)
    with pytest.raises(InvalidTileKey):
        cache.cache_key('default', bad, 'png', 1, 1, 1)
    with pytest.raises(InvalidTileKey):
        cache.cache_key('default', 'GoogleMapsCompatible', bad, 1, 1, 1)


@pytest.mark.parametrize('bad', ['1', 1.5, None, True, False])
def test_non_integer_coordinates_are_refused(bad):
    # bool is an int subclass and would render as True/False in a path.
    with pytest.raises(InvalidTileKey):
        cache.cache_key('default', 'GoogleMapsCompatible', 'png', bad, 1, 1)


# --- the filesystem tier -------------------------------------------------

def test_round_trip(tmp_path):
    tier = FilesystemCache(tmp_path)
    tier.set('default/GoogleMapsCompatible/png/3/4/5', b'tile')
    assert tier.get('default/GoogleMapsCompatible/png/3/4/5') == b'tile'


def test_a_miss_is_none_not_an_error(tmp_path):
    assert FilesystemCache(tmp_path).get('default/GoogleMapsCompatible/png/3/4/5') is None


def test_the_key_becomes_the_path(tmp_path):
    tier = FilesystemCache(tmp_path)
    tier.set('dark_min/DE_EPSG_25832_ADV/jpg/7/8/9', b'x')
    assert (tmp_path / 'dark_min' / 'DE_EPSG_25832_ADV' / 'jpg' / '7' / '8' / '9.jpg').is_file()


def test_a_traversal_key_cannot_escape_the_root(tmp_path):
    tier = FilesystemCache(tmp_path / 'root')
    with pytest.raises(InvalidTileKey):
        tier.set('../../../etc/x/1/2/3', b'x')
    assert not (tmp_path / 'etc').exists()


def test_writes_are_atomic(tmp_path, monkeypatch):
    """A half-written tile read by a racing request stays cached.

    Two requests for the same uncached tile race by construction: a
    browser asks for a whole viewport at once.
    """
    tier = FilesystemCache(tmp_path)
    key = 'default/GoogleMapsCompatible/png/3/4/5'
    real_replace = cache.os.replace
    seen = {}

    def spy(src, dst):
        # Before the rename the destination must not exist at all.
        seen['existed'] = cache.Path(dst).exists()
        return real_replace(src, dst)

    monkeypatch.setattr(cache.os, 'replace', spy)
    tier.set(key, b'abc')
    assert seen['existed'] is False
    assert tier.get(key) == b'abc'


def test_a_failed_write_leaves_no_temporary(tmp_path, monkeypatch):
    tier = FilesystemCache(tmp_path)
    monkeypatch.setattr(cache.os, 'replace',
                        lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        tier.set('default/GoogleMapsCompatible/png/3/4/5', b'x')
    assert list(tmp_path.rglob('*.tmp')) == []


def test_clear_theme_leaves_the_others(tmp_path):
    tier = FilesystemCache(tmp_path)
    tier.set('default/GoogleMapsCompatible/png/3/4/5', b'a')
    tier.set('dark/GoogleMapsCompatible/png/3/4/5', b'b')
    tier.clear_theme('default')
    assert tier.get('default/GoogleMapsCompatible/png/3/4/5') is None
    assert tier.get('dark/GoogleMapsCompatible/png/3/4/5') == b'b'


def test_eviction_drops_the_least_recently_used(tmp_path):
    import os
    import time

    tier = FilesystemCache(tmp_path)
    for index in range(5):
        tier.set(f'default/GoogleMapsCompatible/png/3/4/{index}', b'x' * 100)
    # Make tile 0 the oldest and tile 4 the newest.
    now = time.time()
    for index in range(5):
        path = tmp_path / 'default' / 'GoogleMapsCompatible' / 'png' / '3' / '4' / f'{index}.png'
        os.utime(path, (now - (5 - index) * 100, now - (5 - index) * 100))

    removed = tier.evict_lru(250)
    assert removed >= 2
    assert tier.get('default/GoogleMapsCompatible/png/3/4/0') is None
    assert tier.get('default/GoogleMapsCompatible/png/3/4/4') == b'x' * 100


# --- the tier split ------------------------------------------------------

def test_web_mercator_is_precached_to_twelve(tiers):
    assert tiers.tier_for('GoogleMapsCompatible', 12) is tiers.precache
    assert tiers.tier_for('GoogleMapsCompatible', 13) is tiers.ondemand


def test_utm_is_precached_to_eight(tiers):
    """The reason the cutoff is per set.

    A single z12 constant would send UTM levels 9-12 to the pre-cache
    tier: looked for where nothing was ever written, and written where a
    later pre-cache run would overwrite them.
    """
    assert tiers.tier_for('DE_EPSG_25832_ADV', 8) is tiers.precache
    assert tiers.tier_for('DE_EPSG_25832_ADV', 9) is tiers.ondemand


def test_an_unconfigured_set_falls_back_to_the_default_depth(tiers):
    assert tiers.tier_for('SOMETHING', 12) is tiers.precache
    assert tiers.tier_for('SOMETHING', 13) is tiers.ondemand


def test_a_tile_is_read_from_the_tier_it_was_written_to(tiers):
    tiers.set('default', 'DE_EPSG_25832_ADV', 'png', 5, 1, 1, b'low')
    tiers.set('default', 'DE_EPSG_25832_ADV', 'png', 11, 1, 1, b'high')
    assert tiers.precache.get('default/DE_EPSG_25832_ADV/png/5/1/1') == b'low'
    assert tiers.ondemand.get('default/DE_EPSG_25832_ADV/png/11/1/1') == b'high'
    assert tiers.get('default', 'DE_EPSG_25832_ADV', 'png', 5, 1, 1) == b'low'
    assert tiers.get('default', 'DE_EPSG_25832_ADV', 'png', 11, 1, 1) == b'high'


def test_an_unaddressable_key_is_a_miss_not_an_error(tiers):
    # The routes look the cache up before they validate anything.
    assert tiers.get('../evil', 'GoogleMapsCompatible', 'png', 1, 1, 1) is None


def test_an_unaddressable_key_is_never_written(tiers, tmp_path):
    tiers.set('../evil', 'GoogleMapsCompatible', 'png', 1, 1, 1, b'x')
    assert list((tmp_path).rglob('*.png')) == []


# --- the depth table -----------------------------------------------------

GRIDS = {
    'GoogleMapsCompatible': {'crs': 'EPSG:3857',
                                 'origin': [-20037508.342789244, 20037508.342789244],
                                 'span': 40075016.685578488, 'levels': 19, 'centre_lat': 0},
    'DE_EPSG_25832_ADV': {'crs': 'EPSG:25832', 'origin': [-46133.17, 6301219.54],
                          'span': 1252344.2714243277, 'levels': 15, 'centre_lat': 51.0},
}


def test_a_crs_code_can_never_be_a_cache_key_component():
    """Which is why grids are keyed by identifier: a colon is not a legal
    path segment here, so a set named by its CRS could never be cached."""
    with pytest.raises(InvalidTileKey):
        check_component('tile_matrix_set', 'EPSG:25832')


def test_the_configured_depth_routes_the_set_it_names(tmp_path):
    from renderer import cache as cache_module
    from renderer import matrix

    sets = matrix.load(['GoogleMapsCompatible', 'DE_EPSG_25832_ADV'], GRIDS)
    facade = TileCacheFacade(
        FilesystemCache(tmp_path / 'precache'), FilesystemCache(tmp_path / 'ondemand'),
        cache_module.precache_depths({'GoogleMapsCompatible': 12, 'DE_EPSG_25832_ADV': 8}, sets))
    assert facade.tier_for('DE_EPSG_25832_ADV', 8) is facade.precache
    assert facade.tier_for('DE_EPSG_25832_ADV', 9) is facade.ondemand
    assert facade.tier_for('GoogleMapsCompatible', 12) is facade.precache
    assert facade.tier_for('GoogleMapsCompatible', 13) is facade.ondemand


def test_from_the_nocache_level_on_neither_tier_is_read_or_written(tmp_path):
    from renderer import cache as cache_module
    from renderer import matrix

    sets = matrix.load(['GoogleMapsCompatible', 'DE_EPSG_25832_ADV'], GRIDS)
    facade = TileCacheFacade(
        FilesystemCache(tmp_path / 'precache'), FilesystemCache(tmp_path / 'ondemand'),
        DEPTHS, nocache_from=cache_module.nocache_levels({'GoogleMapsCompatible': 17}, sets))
    assert facade.tier_for('GoogleMapsCompatible', 16) is facade.ondemand
    assert facade.tier_for('GoogleMapsCompatible', 17) is facade.uncached
    assert facade.tier_for('DE_EPSG_25832_ADV', 14) is facade.ondemand

    facade.set('default', 'GoogleMapsCompatible', 'png', 17, 1, 1, b'x')
    assert list(tmp_path.rglob('*.png')) == []
    assert facade.get('default', 'GoogleMapsCompatible', 'png', 17, 1, 1) is None


def test_an_uncached_tile_does_not_count_towards_a_sweep(tmp_path, monkeypatch):
    from web import serving

    facade = TileCacheFacade(FilesystemCache(tmp_path / 'precache'),
                             FilesystemCache(tmp_path / 'ondemand'), DEPTHS,
                             nocache_from={'GoogleMapsCompatible': 17})
    sweeper = serving.Sweeper()
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: 100)
    sweeper.note(facade, 'GoogleMapsCompatible', 17, 1000)
    assert sweeper._written == 0


def test_a_depth_for_a_grid_this_deployment_does_not_serve_is_ignored():
    from renderer import cache as cache_module
    from renderer import matrix

    sets = matrix.load(['GoogleMapsCompatible'], GRIDS)
    depths = cache_module.precache_depths(
        {'GoogleMapsCompatible': 12, 'DE_EPSG_25832_ADV': 8}, sets)
    assert depths == {'GoogleMapsCompatible': 12}


# --- a re-import ---------------------------------------------------------

def test_clearing_an_area_empties_both_tiers(tmp_path, monkeypatch):
    """`drop-cache`: nothing else empties the cache, so it has to empty all
    of it -- a pre-cache run keeps a tile that exists."""
    from renderer import cache as cache_module

    monkeypatch.setattr(cache_module, 'cache_root', lambda area=None: tmp_path / area)
    for tier in ('precache', 'ondemand'):
        tile = tmp_path / 'de_sh' / tier / 'default' / 'GoogleMapsCompatible' / 'png' / '8' / '1' / '2.png'
        tile.parent.mkdir(parents=True)
        tile.write_bytes(b'old')
    other = tmp_path / 'li' / 'precache' / 'default' / 'x.png'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'keep')

    assert cache_module.clear_area('de_sh') == 2
    assert not any(p.is_file() for p in (tmp_path / 'de_sh').rglob('*'))
    # Another area's cache is not touched.
    assert other.read_bytes() == b'keep'


def test_clearing_an_area_with_no_cache_is_nothing(tmp_path, monkeypatch):
    from renderer import cache as cache_module

    monkeypatch.setattr(cache_module, 'cache_root', lambda area=None: tmp_path / area)
    assert cache_module.clear_area('nowhere') == 0


# --- nocache -------------------------------------------------------------

def test_nocache_reads_and_writes_neither_tier(tmp_path, monkeypatch):
    from lib import config
    from renderer import cache as cache_module

    monkeypatch.setitem(config.load(), 'nocache', True)
    monkeypatch.setattr(cache_module, 'cache_root', lambda area=None: tmp_path)
    facade = cache_module.build('de_sh')
    for z in (8, 16):
        facade.set('default', 'GoogleMapsCompatible', 'png', z, 1, 2, b'tile')
        assert facade.get('default', 'GoogleMapsCompatible', 'png', z, 1, 2) is None
    assert not any(tmp_path.rglob('*'))


def test_nocache_refuses_a_precache_run(monkeypatch):
    from lib import config
    from renderer import precache

    monkeypatch.setitem(config.load(), 'nocache', True)
    with pytest.raises(RuntimeError, match='nocache'):
        precache.run('de_sh')
