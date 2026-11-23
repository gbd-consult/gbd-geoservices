"""The Map-object pool.

Rendering mutates the Map handle in place -- `srs`, `zoom_to_box` -- so a
handle can serve one render at a time and the pool is what makes
concurrency safe. Everything here runs against a fake backend, so none of
it needs libmapnik or a database; the one test that does is marked.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from conftest import small_schema

from renderer import core
from renderer.core import MapRegistry, MissingStyleError, ThemeNotFoundError


class FakeHandle:
    def __init__(self, xml: Path, generation: int):
        self.xml = xml
        self.generation = generation
        self.calls: list[tuple] = []


class FakeBackend:
    """Counts loads and records renders. Never touches Mapnik."""

    def __init__(self, fail_for: set[str] | None = None):
        self.loads = 0
        self.fail_for = fail_for or set()
        self.rendered: list[tuple] = []
        self.blocking: threading.Event | None = None

    def load_map(self, xml_path, width, height, buffer_size):
        if xml_path.stem in self.fail_for:
            raise RuntimeError(f'bad xml: {xml_path}')
        self.loads += 1
        return FakeHandle(xml_path, self.loads)

    def render(self, handle, bbox, fmt, crs, size, scale):
        if self.blocking is not None:
            self.blocking.wait(timeout=5)
        self.rendered.append((handle, bbox, fmt, crs, size))
        self.scale = scale
        return f'{handle.xml.stem}:{fmt}:{crs}'.encode()


@pytest.fixture
def xml(tmp_path) -> Path:
    path = tmp_path / 'default.xml'
    path.write_text('<Map/>')
    return path


# --- loading -------------------------------------------------------------

def test_a_missing_xml_is_loud(tmp_path):
    registry = MapRegistry(FakeBackend())
    with pytest.raises(MissingStyleError, match='manage.py compile-styles'):
        registry.load_theme('default', tmp_path / 'nope.xml')


def test_a_missing_style_never_falls_back(tmp_path, xml):
    # The point of the error: a theme whose XML vanished must not quietly
    # render as some other theme.
    registry = MapRegistry(FakeBackend())
    registry.load_theme('default', xml)
    with pytest.raises(MissingStyleError):
        registry.load_theme('dark', tmp_path / 'dark.xml')
    assert registry.loaded(core.DEFAULT_MATRIX_SET) == ['default']


def test_the_pool_holds_one_handle_per_slot(xml):
    backend = FakeBackend()
    MapRegistry(backend, pool_size=3).load_theme('default', xml)
    assert backend.loads == 3


def test_rendering_an_unloaded_theme_is_loud():
    registry = MapRegistry(FakeBackend())
    with pytest.raises(ThemeNotFoundError, match='never loaded'):
        registry.render('default', (0, 0, 1, 1), 'png')


def test_rendering_never_loads_xml_on_demand(xml):
    # Loading is a startup concern; doing it per request would parse the
    # XML and open every datasource inside a request.
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=2)
    registry.load_theme('default', xml)
    before = backend.loads
    for _ in range(5):
        registry.render('default', (0, 0, 1, 1), 'png')
    assert backend.loads == before


# --- the contract --------------------------------------------------------

def test_render_passes_the_bbox_format_and_crs_through(xml):
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    out = registry.render('default', (1.0, 2.0, 3.0, 4.0), 'jpg', 'epsg:25832')
    assert out == b'default:jpg:epsg:25832'
    _, bbox, fmt, crs, size = backend.rendered[0]
    assert (bbox, fmt, crs) == ((1.0, 2.0, 3.0, 4.0), 'jpg', 'epsg:25832')
    assert size == (core.TILE_SIZE, core.TILE_SIZE)


def test_a_size_reaches_the_backend(xml):
    """WMS GetMap renders its own WIDTH x HEIGHT on a pooled tile handle."""
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    registry.render('default', (0, 0, 1, 1), 'png', size=(800, 600))
    assert backend.rendered[0][4] == (800, 600)


def test_a_2x_tile_is_twice_the_size_at_scale_two(xml):
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    registry.render('default', (0, 0, 1, 1), 'png', scale=2)
    assert backend.rendered[0][4] == (2 * core.TILE_SIZE, 2 * core.TILE_SIZE)
    assert backend.scale == 2


def test_the_default_crs_is_the_one_the_xml_declares(xml):
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    registry.render('default', (0, 0, 1, 1), 'png')
    assert backend.rendered[0][3] == core.DEFAULT_CRS == 'epsg:3857'


# --- concurrency ---------------------------------------------------------

def test_the_pool_bounds_concurrent_renders(xml):
    """A handle serves one render at a time.

    With one slot, a second render must wait -- that is what makes
    mutating `srs` and `zoom_to_box` on a shared handle safe.
    """
    backend = FakeBackend()
    backend.blocking = threading.Event()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)

    started = threading.Event()
    done = []

    def render():
        started.set()
        done.append(registry.render('default', (0, 0, 1, 1), 'png'))

    first = threading.Thread(target=render)
    first.start()
    started.wait(timeout=5)

    second = threading.Thread(target=render)
    second.start()
    second.join(timeout=0.3)
    assert second.is_alive(), 'the second render should be waiting for the handle'

    backend.blocking.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert len(done) == 2


def test_a_render_that_queued_says_so(xml):
    """The access log times a tile from request to response, so a tile that
    waited for a handle looks like a slow render. `steps` gets the two apart.
    """
    from lib import timing

    backend = FakeBackend()
    backend.blocking = threading.Event()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)

    first = threading.Thread(target=registry.render, args=('default', (0, 0, 1, 1), 'png'))
    first.start()
    steps = timing.Steps()
    second = threading.Thread(target=registry.render,
                              args=('default', (0, 0, 1, 1), 'png'),
                              kwargs={'steps': steps})
    second.start()
    threading.Timer(0.2, backend.blocking.set).start()
    first.join(timeout=5)
    second.join(timeout=5)

    names = [name for name, _, _ in steps.steps]
    assert names == ['wait', 'render']
    assert steps.steps[0][1] >= 150


# --- reloading -----------------------------------------------------------

def test_reloading_bumps_the_generation(xml):
    registry = MapRegistry(FakeBackend(), pool_size=1)
    assert registry.generation('default') == 0
    registry.load_theme('default', xml)
    assert registry.generation('default') == 1
    registry.load_theme('default', xml)
    assert registry.generation('default') == 2


def test_a_reload_that_fails_leaves_the_old_pool_working(xml, tmp_path):
    """Every handle is built before the new pool is published.

    Otherwise a bad style takes a working theme down until the next
    restart.
    """
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=2)
    registry.load_theme('default', xml)

    broken = tmp_path / 'broken.xml'
    broken.write_text('<Map>')
    backend.fail_for = {'broken'}
    with pytest.raises(RuntimeError):
        registry.load_theme('default', broken)

    assert registry.render('default', (0, 0, 1, 1), 'png') == b'default:png:epsg:3857'
    assert registry.generation('default') == 1


def test_a_handle_from_the_old_pool_is_not_returned_to_the_new_one(xml, tmp_path):
    """A render in flight across a reload must not resurrect the old style.

    Returning its handle would also overfill the new queue.
    """
    backend = FakeBackend()
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)

    with registry._checkout('default', core.DEFAULT_MATRIX_SET):
        other = tmp_path / 'default2.xml'
        other.write_text('<Map/>')
        registry.load_theme('default', other)      # swaps the pool
    # The new pool is still full, not over-full.
    assert registry._pools[('default', core.DEFAULT_MATRIX_SET)].qsize() == 1
    assert registry.render('default', (0, 0, 1, 1), 'png') == b'default2:png:epsg:3857'


# --- preload -------------------------------------------------------------

def test_preload_skips_what_it_cannot_load(tmp_path):
    """A broken theme must not take the process down.

    Mapnik opens every layer's datasource while parsing, so against an
    empty database every theme raises -- and failing hard there is a
    restart loop no `docker exec` can get into to fix.
    """
    for name in ('default', 'dark'):
        (tmp_path / f'{name}.xml').write_text('<Map/>')
    backend = FakeBackend(fail_for={'dark'})
    registry = MapRegistry(backend, pool_size=1)

    loaded = registry.preload(['default', 'dark', 'missing'],
                              lambda t, s_: tmp_path / f'{t}.xml')
    assert loaded == ['default']
    assert registry.loaded(core.DEFAULT_MATRIX_SET) == ['default']


def test_a_theme_that_failed_to_preload_still_fails_loudly_per_request(tmp_path):
    registry = MapRegistry(FakeBackend(fail_for={'dark'}), pool_size=1)
    (tmp_path / 'dark.xml').write_text('<Map/>')
    registry.preload(['dark'], lambda t, s_: tmp_path / f'{t}.xml')
    with pytest.raises(ThemeNotFoundError):
        registry.render('dark', (0, 0, 1, 1), 'png')


# --- paths ---------------------------------------------------------------

def test_theme_names_come_from_the_compiled_xml(tmp_path, monkeypatch):
    from lib import config, db

    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'small')
    monkeypatch.setattr(config, 'opt', lambda key, default=None: {
        'data_dir': str(tmp_path)}.get(key, default))
    directory = tmp_path / 'styles' / 'small' / core.DEFAULT_MATRIX_SET
    directory.mkdir(parents=True)
    for name in ('default_std', 'dark_min', 'hico_std'):
        (directory / f'{name}.xml').write_text('<Map/>')
    assert core.available_themes() == ['dark_min', 'default_std', 'hico_std']
    assert core.xml_path_for('dark_min').name == 'dark_min.xml'
    # The set is a directory of its own, because a theme is compiled once
    # per grid and the two files are not interchangeable.
    assert core.xml_path_for('dark_min').parent.name == core.DEFAULT_MATRIX_SET


def test_a_set_with_no_compiled_styles_is_empty_not_the_other_sets(tmp_path, monkeypatch):
    """Each grid has its own directory, so asking for one that was never
    generated must not quietly answer with another one's themes."""
    from lib import config, db

    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'small')
    monkeypatch.setattr(config, 'opt', lambda key, default=None: {
        'data_dir': str(tmp_path)}.get(key, default))
    directory = tmp_path / 'styles' / 'small' / core.DEFAULT_MATRIX_SET
    directory.mkdir(parents=True)
    (directory / 'default_std.xml').write_text('<Map/>')
    assert core.available_themes() == ['default_std']
    assert core.available_themes(matrix_set='DE_EPSG_25832_ADV') == []


def test_xml_left_from_a_wider_compile_is_not_served(tmp_path, monkeypatch):
    """`serve_palettes`/`serve_details` narrow the loader too, not only the
    compile: a restart after narrowing them must not load what an earlier
    compile left on disk."""
    from lib import config, db

    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'small')
    monkeypatch.setattr(config, 'opt', lambda key, default=None: {
        'data_dir': str(tmp_path),
        'serve_palettes': ['default'], 'serve_details': ['max']}.get(key, default))
    directory = tmp_path / 'styles' / 'small' / core.DEFAULT_MATRIX_SET
    directory.mkdir(parents=True)
    for name in ('default_std', 'default_max', 'dark_max'):
        (directory / f'{name}.xml').write_text('<Map/>')
    assert core.available_themes() == ['default_max']


def test_no_compiled_styles_is_an_empty_list_not_a_crash(tmp_path, monkeypatch):
    from lib import config, db

    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'small')
    monkeypatch.setattr(config, 'opt', lambda key, default=None: {
        'data_dir': str(tmp_path)}.get(key, default))
    assert core.available_themes() == []


# --- the real thing ------------------------------------------------------

SMALL = small_schema()


def compiled():
    return core.available_themes(SMALL) if SMALL else []


@pytest.mark.skipif(not compiled(), reason='run tools/manage.py compile-styles li first')
def test_a_real_tile_renders_and_caches(tmp_path):
    """Registry, Mapnik, PostGIS and the cache, end to end.

    Everything above is a fake backend; this is the one that would catch a
    Mapnik API rename or an XML the generator writes but Mapnik refuses.
    """
    from renderer.cache import FilesystemCache, TileCacheFacade

    themes = compiled()
    registry = MapRegistry(pool_size=1, buffer_size=64)
    loaded = registry.preload(themes[:1],
                              lambda t, s_: core.xml_path_for(t, SMALL, s_))
    assert loaded, 'the compiled XML did not load in Mapnik'

    theme = loaded[0]
    bbox = (1060000.0, 5955000.0, 1065000.0, 5960000.0)     # z13 over Triesen
    data = registry.render(theme, bbox, 'png')
    assert data.startswith(b'\x89PNG')
    assert len(data) > 1000, 'a blank tile would be much smaller'

    tiers = TileCacheFacade(FilesystemCache(tmp_path / 'precache'),
                            FilesystemCache(tmp_path / 'ondemand'),
                            {'GoogleMapsCompatible': 12})
    tiers.set(theme, 'GoogleMapsCompatible', 'png', 13, 4321, 2859, data)
    # z13 is above the pre-cache depth, so it belongs to the on-demand tier.
    assert tiers.ondemand.get(f'{theme}/GoogleMapsCompatible/png/13/4321/2859') == data
    assert tiers.get(theme, 'GoogleMapsCompatible', 'png', 13, 4321, 2859) == data


@pytest.mark.skipif(not compiled(), reason='run tools/manage.py compile-styles li first')
def test_every_compiled_theme_loads_in_mapnik():
    # The generator writes sixteen; a theme that does not load is a theme
    # that cannot be served.
    registry = MapRegistry(pool_size=1)
    themes = compiled()
    loaded = registry.preload(themes, lambda t, s_: core.xml_path_for(t, SMALL, s_))
    assert sorted(loaded) == sorted(themes)


# --- a database restart --------------------------------------------------

class DroppingBackend(FakeBackend):
    """Fails the first `dead` renders the way libpq does after a restart."""

    def __init__(self, dead: int, message: str = (
            'Postgis Plugin: FATAL:  terminating connection due to administrator '
            'command\nserver closed the connection unexpectedly')):
        super().__init__()
        self.dead = dead
        self.message = message
        self.attempts = 0

    def render(self, handle, bbox, fmt, crs, size, scale):
        self.attempts += 1
        if self.attempts <= self.dead:
            raise RuntimeError(self.message)
        return super().render(handle, bbox, fmt, crs, size, scale)


def test_the_first_tile_after_a_database_restart_renders(xml):
    """A lost connection is retried, not served as an error.

    Mapnik's PostGIS plugin pools its connections, and after Postgres
    restarts each one still looks open until a query fails on it. Measured
    on the dev stack: the first tile after `docker compose restart postgres`
    was a 500, the second a 200.
    """
    backend = DroppingBackend(dead=3)
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    assert registry.render('default', (0, 0, 1, 1), 'png')
    assert backend.attempts == 4


def test_a_full_pool_of_dead_connections_is_cleared_in_one_request(xml):
    registry = MapRegistry(DroppingBackend(dead=11), pool_size=1, db_pool_size=10)
    registry.load_theme('default', xml)
    assert registry.render('default', (0, 0, 1, 1), 'png')


def test_retrying_is_bounded(xml):
    backend = DroppingBackend(dead=100)
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    with pytest.raises(RuntimeError, match='closed the connection'):
        registry.render('default', (0, 0, 1, 1), 'png')
    assert backend.attempts == registry.lost_connection_retries + 1


def test_a_database_that_is_down_is_not_retried(xml):
    """Still down fails fast: retrying a refused connection only makes the
    error slower."""
    backend = DroppingBackend(dead=100, message=(
        'Postgis Plugin: connection to server at "postgres" (172.28.0.2), port '
        '5432 failed: Connection refused'))
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    with pytest.raises(RuntimeError, match='refused'):
        registry.render('default', (0, 0, 1, 1), 'png')
    assert backend.attempts == 1


def test_any_other_render_error_is_not_retried(xml):
    backend = DroppingBackend(dead=100, message='unknown file type: jpg')
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    with pytest.raises(RuntimeError, match='unknown file type'):
        registry.render('default', (0, 0, 1, 1), 'jpg')
    assert backend.attempts == 1


def test_the_handle_goes_back_to_the_pool_after_a_retried_render(xml):
    backend = DroppingBackend(dead=2)
    registry = MapRegistry(backend, pool_size=1)
    registry.load_theme('default', xml)
    registry.render('default', (0, 0, 1, 1), 'png')
    # With a pool of one, a leaked handle would block this second render.
    assert registry.render('default', (0, 0, 1, 1), 'png')


# --- the 2x tile, against real Mapnik ------------------------------------

#: A z14 tile over Vaduz, in 3857, and what one of its 1x pixels spans.
_HALF = 20037508.342789244
_SPAN = 2 * _HALF / 2 ** 14
_Z14 = (-_HALF + 8607 * _SPAN, _HALF - 5763 * _SPAN, -_HALF + 8608 * _SPAN, _HALF - 5762 * _SPAN)
_PIXEL = _SPAN / core.TILE_SIZE

#: Between the z14 (34 124) and z15 (17 062) scale denominators.
_BETWEEN = 25000


def _render(xml: str, scale: int) -> int:
    """The colour at the middle of the right edge of the z14 tile, rendered
    at `scale` the way `RealMapnikBackend` does."""
    mapnik = pytest.importorskip('mapnik', reason='libmapnik is installed in the container')
    size = core.TILE_SIZE * scale
    handle = mapnik.Map(size, size)
    mapnik.load_map_from_string(handle, xml)
    handle.zoom_to_box(mapnik.Box2d(*_Z14))
    image = mapnik.Image(size, size)
    mapnik.render(handle, image, scale)
    return image.get_pixel(size - 2, size // 2)


#: `get_pixel` packs RGBA little-endian: opaque red.
RED = 0xff0000ff


@pytest.mark.parametrize('scale', core.SCALES)
def test_a_2x_tile_selects_and_queries_what_its_1x_twin_does(db, scale):
    """Mapnik divides the scale factor back out of the scale denominator, for
    the rules and for `!scale_denominator!` in the SQL alike.

    Every zoom boundary depends on it -- the rule ranges and the zoom the
    queries derive from `!scale_denominator!` (`renderer.queries`). Without
    it a 512 px tile reads as one zoom finer: more detail, the next band's
    table, and nothing that fails. The colour says which rule (red/yellow
    above the boundary) and which value the SQL saw (red/blue above it).
    """
    xml = f'''<Map srs="epsg:3857" background-color="white">
      <Style name="s">
        <Rule><MinScaleDenominator>{_BETWEEN}</MinScaleDenominator>
          <Filter>[sd] &gt; {_BETWEEN}</Filter><PolygonSymbolizer fill="#ff0000"/></Rule>
        <Rule><MinScaleDenominator>{_BETWEEN}</MinScaleDenominator>
          <Filter>[sd] &lt;= {_BETWEEN}</Filter><PolygonSymbolizer fill="#ffff00"/></Rule>
        <Rule><MaxScaleDenominator>{_BETWEEN}</MaxScaleDenominator>
          <Filter>[sd] &gt; {_BETWEEN}</Filter><PolygonSymbolizer fill="#0000ff"/></Rule>
        <Rule><MaxScaleDenominator>{_BETWEEN}</MaxScaleDenominator>
          <Filter>[sd] &lt;= {_BETWEEN}</Filter><PolygonSymbolizer fill="#00ff00"/></Rule>
      </Style>
      <Layer name="l" srs="epsg:3857"><StyleName>s</StyleName><Datasource>
        <Parameter name="type">postgis</Parameter>
        <Parameter name="table">(select st_expand(!bbox!, 10) as geom,
                                 !scale_denominator!::float8 as sd) t</Parameter>
        <Parameter name="geometry_field">geom</Parameter>
        <Parameter name="srid">3857</Parameter>
        <Parameter name="extent">-{_HALF},-{_HALF},{_HALF},{_HALF}</Parameter>
      </Datasource></Layer>
    </Map>'''
    assert _render(xml, scale) == RED


@pytest.mark.parametrize('scale', core.SCALES)
@pytest.mark.parametrize('outside,seen', [(40, True), (70, False)])
def test_a_2x_tile_fetches_the_ground_its_1x_twin_does(scale, outside, seen):
    """Mapnik scales each layer's `buffer-size` by the scale factor, so the
    64 px the styles write (`buffer_px`) reach as far at 2x as at 1x.

    If it did not, a 2x tile would fetch half the margin: labels and icons
    just outside it would vanish at its edges and nowhere in a 1x tile. A
    point `outside` 1x pixels to the right of the tile carries a marker
    that reaches into it -- drawn when 64 px of buffer cover it (40), not
    when they do not (70), at either ratio.
    """
    x = _Z14[2] + outside * _PIXEL
    y = (_Z14[1] + _Z14[3]) / 2
    xml = f'''<Map srs="epsg:3857" background-color="white" buffer-size="0">
      <Style name="s"><Rule><MarkersSymbolizer marker-type="ellipse" width="160" height="160"
        fill="#ff0000" stroke-width="0" allow-overlap="true"/></Rule></Style>
      <Layer name="l" srs="epsg:3857" buffer-size="64"><StyleName>s</StyleName><Datasource>
        <Parameter name="type">csv</Parameter>
        <Parameter name="inline">x,y
{x},{y}
</Parameter>
      </Datasource></Layer>
    </Map>'''
    assert (_render(xml, scale) == RED) is seen
