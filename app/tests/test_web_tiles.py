"""The XYZ route, the cache headers, and the bound on the on-demand tier.

`/xyz` is thin on purpose -- it turns z/x/y into a bbox and calls the
renderer -- so what is worth testing here is everything *around* that: which
addresses are 404 rather than 500, whether a conditional request is honoured,
and whether the on-demand tier actually stays within its bound.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web import formats, httpcache, serving
from web.main import app

#: Vaduz, computed from the Web Mercator grid rather than guessed -- an
#: invented tile address renders an empty tile and passes a test that
#: proves nothing.
Z, X, Y = 14, 8624, 5749

#: The themes these tests name. Loading one is `map_pool_size` Mapnik
#: parses; loading all twelve for both grids measured 111 seconds.
THEMES = ('default_std', 'dark_max')


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    serving.reset()


@pytest.fixture(scope='module')
def served():
    """A client whose server is pointed at the imported `li` schema.

    Module-scoped, and that is not a style choice: loading the Map pool is
    `map_pool_size` Mapnik parses per (theme, TileMatrixSet), which for 12
    themes and two grids is 96 of them and **111 seconds** measured. Per
    test it is an afternoon; once per module it is the startup the server
    itself pays.

    The schema is patched *before* the TestClient is built, so the app's
    own lifespan does the loading -- the same path a real start takes.
    """
    from conftest import small_schema

    from lib import db
    from renderer import core

    schema = small_schema()
    if schema is None or not core.available_themes(schema):
        pytest.skip('no compiled styles for `li`; run manage.py compile-styles li')

    original = db.active_schema
    db.active_schema = lambda area=None: schema
    serving.reset()
    # The two themes these tests name, in the one grid `/xyz` serves --
    # not the app's own lifespan, which loads every theme for every grid.
    # That path is exercised by `test_web_meta.py`'s client; here it would
    # be 96 Mapnik parses to answer questions about four.
    core.get_registry().preload(
        THEMES, lambda theme, set_name: core.xml_path_for(theme, schema, set_name),
        core.DEFAULT_MATRIX_SET)
    try:
        yield TestClient(app)
    finally:
        db.active_schema = original
        serving.reset()


def url(theme='std', z=Z, x=X, y=Y, fmt='png'):
    return f'/xyz/{theme}/{z}/{x}/{y}.{fmt}'


# --- formats -------------------------------------------------------------

def test_every_accepted_spelling_normalises_to_one_form():
    """One spelling per format, so a cache key and a Content-Type cannot
    disagree about the same bytes."""
    assert formats.normalize('jpeg') == formats.normalize('jpg') == 'jpg'
    assert formats.normalize('image/png') == 'png'
    assert formats.normalize('application/vnd.mapbox-vector-tile') == 'pbf'


def test_an_unknown_format_passes_through_lower_cased():
    # Deciding whether a format is *servable* is the route's job, and it
    # wants to name the offender.
    assert formats.normalize('GIF') == 'gif'
    assert formats.normalize('image/gif') == 'gif'


def test_an_unservable_format_is_404_not_400():
    """A tile address is a path; an extension this service does not serve
    is an address that does not exist."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        serving.check_format('gif')
    assert excinfo.value.status_code == 404


def test_the_mapnik_encoder_name_is_not_the_canonical_one():
    """`Image.to_string('jpg')` raises `unknown file type: jpg`.

    Every layer above spells it `jpg`; Mapnik wants `jpeg`. Passing the
    format straight through fails only when something asks for a JPEG.
    """
    from renderer import core
    assert core.encoder_for('jpg') == 'jpeg'
    assert core.encoder_for('png') == 'png8'
    # A parameterised encoder passes through, to fail at Mapnik if wrong.
    assert core.encoder_for('png256') == 'png256'


# --- the route -----------------------------------------------------------

def test_a_tile_renders(served):
    response = served.get(url())
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content[:4] == b'\x89PNG'
    # Real content, not an empty tile: the address is computed, not guessed.
    assert len(response.content) > 10_000


@pytest.mark.parametrize('fmt,mime', [('png', 'image/png'), ('jpg', 'image/jpeg'),
                                      ('jpeg', 'image/jpeg')])
def test_every_raster_format_serves(served, fmt, mime):
    response = served.get(url(fmt=fmt))
    assert response.status_code == 200
    assert response.headers['content-type'] == mime


def test_an_unknown_theme_is_404(served):
    """Validated against the compiled XML on disk, so a theme that was
    never generated is a 404 rather than a failure deep inside Mapnik."""
    assert served.get(url(theme='nosuchtheme')).status_code == 404


@pytest.mark.parametrize('theme,name', [
    ('default_std', 'std'),
    ('default_max', 'max'),
    ('dark_std', 'dark'),
    ('dark_max', 'dark_max'),
])
def test_a_url_leaves_out_the_default_palette_and_detail(theme, name):
    assert serving.url_name(theme) == name


@pytest.mark.parametrize('name', ['std', 'dark_max'])
def test_a_url_name_serves(served, name):
    assert served.get(url(theme=name)).status_code == 200


@pytest.mark.parametrize('name', ['default', 'default_std', 'default_max', 'dark_std'])
def test_a_theme_has_one_url_name(served, name):
    """A name that spells out the default palette or detail is not an
    alias: one name per theme, so a tile has one URL in each grid."""
    assert served.get(url(theme=name)).status_code == 404


def test_an_address_outside_the_pyramid_is_404(served):
    """Not a 500 and not an on-demand render."""
    assert served.get(url(x=99_999_999)).status_code == 404
    assert served.get(url(z=25, x=1, y=1)).status_code == 404


def test_a_tile_outside_the_data_is_an_empty_tile_not_an_error(served):
    # The pyramid is global; the import is not. An address with nothing in
    # it is a valid address.
    response = served.get(url(z=1, x=0, y=0))
    assert response.status_code == 200


def test_head_is_answered(served):
    """FastAPI's `.get()` registers only GET, unlike Starlette's plain
    routes -- so `curl -I` on a tile, and every monitor that probes with
    HEAD, got a 405."""
    response = served.head(url())
    assert response.status_code == 200
    assert response.headers['etag']
    assert response.content == b''


# --- caching -------------------------------------------------------------

def test_an_etag_is_over_the_bytes():
    """Not over the address plus a generation counter.

    The generation is per *process*, so two containers behind a proxy
    restart at different times and hand out different tags for identical
    tiles, making every client revalidation miss.
    """
    assert httpcache.tile_etag(b'abc') == httpcache.tile_etag(b'abc')
    assert httpcache.tile_etag(b'abc') != httpcache.tile_etag(b'abd')


def test_a_matching_etag_is_304_with_no_body(served):
    etag = served.get(url()).headers['etag']
    response = served.get(url(), headers={'If-None-Match': etag})
    assert response.status_code == 304
    assert response.content == b''


def test_a_weak_tag_matches_a_strong_one(served):
    """RFC 9110 8.2.2: `If-None-Match` uses weak comparison."""
    etag = served.get(url()).headers['etag']
    assert served.get(url(), headers={'If-None-Match': f'W/{etag}'}).status_code == 304


def test_a_star_matches_whatever_exists(served):
    assert served.get(url(), headers={'If-None-Match': '*'}).status_code == 304


def test_a_different_tag_sends_the_body(served):
    assert served.get(url(), headers={'If-None-Match': '"nope"'}).status_code == 200


def test_a_comma_in_a_client_tag_can_only_fail_to_match():
    """A 200 where a 304 would have done, never a 304 where the body
    differs -- which is why the naive split is safe."""
    etag = httpcache.tile_etag(b'x')
    assert httpcache.is_not_modified(f'"a,b", {etag}', etag)
    assert not httpcache.is_not_modified('"a,b"', etag)


def test_a_versioned_url_is_immutable(served):
    """The URL names one compiled-style generation, so its bytes can never
    change; `immutable` stops browsers revalidating on a plain reload."""
    control = served.get(url() + '?v=7').headers['cache-control']
    assert 'immutable' in control
    assert f'max-age={httpcache.IMMUTABLE_MAX_AGE}' in control


def test_nocache_stores_nothing_in_the_browser(monkeypatch):
    """The generation in `?v=` is per process: after a restart it repeats a
    number an `immutable` tile was already cached under, and the browser
    never asks for that tile again."""
    from lib import config

    real = config.opt
    monkeypatch.setattr(config, 'opt',
                        lambda path, default=None: True if path == 'nocache' else real(path, default))
    etag = httpcache.tile_etag(b'x')
    assert httpcache.headers(etag, versioned=True) == {'Cache-Control': 'no-store'}
    assert httpcache.headers(etag, versioned=False) == {'Cache-Control': 'no-store'}


def test_an_unversioned_url_gets_a_short_life(served):
    control = served.get(url()).headers['cache-control']
    assert 'immutable' not in control
    assert f'max-age={httpcache.max_age()}' in control


def test_an_error_carries_no_cache_headers(served):
    """A tile that starts working after a fix must not be shadowed by a
    cached failure."""
    response = served.get(url(theme='nosuchtheme'))
    assert response.status_code == 404
    assert 'cache-control' not in {k.lower() for k in response.headers}


# --- the on-demand cache bound -------------------------------------------

class FakeTier:
    def __init__(self):
        self.evicted_to = None

    def evict_lru(self, max_bytes):
        self.evicted_to = max_bytes
        return 3


class FakeCache:
    def __init__(self, ondemand, precached_depth=12):
        self.ondemand = ondemand
        self.precache = object()
        self._depth = precached_depth

    def tier_for(self, tile_matrix_set, z):
        return self.precache if z <= self._depth else self.ondemand


def test_the_precache_tier_is_never_swept(monkeypatch):
    """Evicting a pre-cached tile means rendering it again on demand --
    the exact cost the pre-cache exists to avoid."""
    sweeper = serving.Sweeper()
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: 1024)
    tier = FakeTier()
    cache = FakeCache(tier)
    sweeper.note(cache, 'GoogleMapsCompatible', 5, 10_000_000)
    assert tier.evicted_to is None


def test_a_sweep_is_scheduled_not_run_per_write(monkeypatch):
    """Walking the tier to total its size costs more than the render that
    produced the tile, so writes accumulate until a threshold."""
    sweeper = serving.Sweeper()
    limit = 1000
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: limit)
    tier = FakeTier()
    cache = FakeCache(tier)

    below = int(limit * serving.SWEEP_AFTER_FRACTION) - 1
    sweeper.note(cache, 'GoogleMapsCompatible', 14, below)
    assert tier.evicted_to is None


def test_crossing_the_threshold_sweeps(monkeypatch):
    sweeper = serving.Sweeper()
    limit = 1000
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: limit)
    # Run the sweep inline. Patching `serving.threading.Thread` instead
    # would replace threads for the whole process -- it is the stdlib
    # module -- and deadlock the test client.
    monkeypatch.setattr(sweeper, '_start', sweeper._sweep)
    tier = FakeTier()
    sweeper.note(FakeCache(tier), 'GoogleMapsCompatible', 14, limit)
    assert tier.evicted_to == int(limit * serving.SWEEP_TARGET_FRACTION)


def test_a_second_sweep_does_not_start_while_one_is_running(monkeypatch):
    """Two concurrent `evict_lru` walks would fight over the same files."""
    sweeper = serving.Sweeper()
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: 1000)
    starts = []
    monkeypatch.setattr(sweeper, '_start', lambda tier, limit: starts.append(limit))
    tier = FakeTier()
    cache = FakeCache(tier)
    sweeper.note(cache, 'GoogleMapsCompatible', 14, 1000)
    sweeper.note(cache, 'GoogleMapsCompatible', 14, 1000)
    assert len(starts) == 1


def test_a_sweep_evicts_below_the_limit_so_the_next_is_not_due_at_once(monkeypatch):
    assert serving.SWEEP_TARGET_FRACTION < 1.0


def test_no_limit_configured_means_no_sweep(monkeypatch):
    sweeper = serving.Sweeper()
    monkeypatch.setattr(sweeper, 'limit_bytes', lambda: 0)
    tier = FakeTier()
    sweeper.note(FakeCache(tier), 'GoogleMapsCompatible', 14, 10**9)
    assert tier.evicted_to is None


def test_a_failing_sweep_never_reaches_the_request(monkeypatch, caplog):
    """It runs on a background thread, but a bug in it must not take the
    process with it."""
    sweeper = serving.Sweeper()

    class Broken:
        def evict_lru(self, max_bytes):
            raise OSError('disk gone')

    with caplog.at_level('WARNING'):
        sweeper._sweep(Broken(), 1000)
    assert any('sweep failed' in record.getMessage() for record in caplog.records)


def test_the_limit_comes_from_the_option():
    """`ondemand_cache_max_mb` described a limit nothing enforced:
    `evict_lru` existed with no caller."""
    from lib import config
    expected = int(config.opt('ondemand_cache_max_mb')) * 1024 * 1024
    assert serving.Sweeper().limit_bytes() == expected


# --- themes in /metadata and /status -------------------------------------

def test_metadata_lists_what_is_compiled(served):
    """So a client does not have to parse WMTS capabilities to populate a
    theme switcher."""
    themes = served.get('/metadata').json()['themes']
    assert themes
    assert 'std' in {entry['id'] for entry in themes}
    for entry in themes:
        assert set(entry) == {'id', 'palette', 'detail'}


def test_a_theme_name_splits_into_palette_and_detail(served):
    themes = {entry['id']: entry for entry in served.get('/metadata').json()['themes']}
    assert themes['std']['palette'] == 'default'
    assert themes['std']['detail'] == 'std'
    assert themes['max']['palette'] == 'default'
    assert themes['max']['detail'] == 'max'
    assert themes['dark']['palette'] == 'dark'
    assert themes['dark']['detail'] == 'std'
    assert themes['dark_max']['palette'] == 'dark'
    assert themes['dark_max']['detail'] == 'max'


def test_status_reports_each_themes_generation(served):
    """The `?v=` a tile URL carries: it changes when a theme is reloaded."""
    themes = served.get('/status').json()['themes']
    assert {entry['id'] for entry in themes} == {
        entry['id'] for entry in served.get('/metadata').json()['themes']}
    for entry in themes:
        assert set(entry) == {'id', 'generation'}


# --- which compiled XML a tile is rendered from --------------------------

class Recorder:
    """Stands in for `renderer.core`, to record what `serve` asks for."""

    def __init__(self):
        self.calls = []

    def render_tile(self, theme, bbox, fmt, crs=None, matrix_set=None, steps=None):
        self.calls.append({'theme': theme, 'crs': crs, 'matrix_set': matrix_set})
        return b'tile-bytes'

    def available_themes(self, schema=None, matrix_set=None):
        return ['default_std']


@pytest.mark.parametrize('crs,identifier', [
    ('EPSG:3857', 'GoogleMapsCompatible'),
    ('EPSG:25832', 'DE_EPSG_25832_ADV'),
    ('EPSG:25833', 'DE_EPSG_25833_ADV'),
])
def test_serve_names_the_set_it_was_asked_for(monkeypatch, tmp_path, crs, identifier):
    """A theme is compiled once per grid, so the render has to say which
    file it wants -- the CRS alone does not pick one.

    `serve` passed only `tms.crs`, leaving `matrix_set` at its default, so
    every EPSG:25832 tile was rendered from the Web Mercator XML: one zoom
    too fine and reading the unbanded tables where the band was meant. It
    renders, it caches, and it is the wrong tile -- which is why
    `test_the_reprojected_set_serves` in test_web_wmts.py passed all along.
    """
    from renderer import cache as cache_module
    from renderer import core, matrix

    recorder = Recorder()
    monkeypatch.setattr(core, 'render_tile', recorder.render_tile)
    monkeypatch.setattr(serving, '_caches', {})
    monkeypatch.setattr(cache_module, 'cache_root', lambda area=None: tmp_path)

    tms = matrix.by_crs(matrix.load(), crs)
    assert tms.identifier == identifier

    class Req:
        query_params = {}
        headers = {}

    serving.serve(Req(), theme='default_std', tms=tms, level=4, col=1, row=1,
                  fmt='png', schema='probe')
    assert recorder.calls == [{'theme': 'default_std', 'crs': tms.crs,
                               'matrix_set': identifier}]
