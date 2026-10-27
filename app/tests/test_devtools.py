"""The devtools viewer.

Mostly JavaScript, driven by hand and by a headless browser rather than from
here; what is tested here is the server half -- that the page exists only
when the option says so, that it never carries a key, and that the two
endpoints the browser cannot do without give it what it needs to build a map.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web import devtools


def app_with(monkeypatch, enabled: bool, keys=None, watch: bool = False) -> FastAPI:
    """A bare app with only the devtools mounted, under a given option."""
    from lib import config

    real = config.opt

    def opt(path, default=None):
        if path == 'devtools':
            return enabled
        if path == 'devtools_watch':
            return watch
        if path == 'keys':
            return keys or []
        return real(path, default)

    monkeypatch.setattr(config, 'opt', opt)
    app = FastAPI()
    devtools.mount(app)
    return app


def test_off_by_default():
    """"Viewer only, never on a public deployment" -- so the versioned
    default must be off, and a deployment has to ask for it."""
    import yaml

    from lib.config import DEFAULTS_PATH
    assert yaml.safe_load(DEFAULTS_PATH.read_text())['devtools'] is False


def test_not_mounted_when_off(monkeypatch):
    client = TestClient(app_with(monkeypatch, False))
    assert client.get('/devtools').status_code == 404
    assert client.get('/devtools/api/grids').status_code == 404
    assert client.get('/devtools/static/main.js').status_code == 404



def test_the_scripts_are_revalidated_on_every_load(monkeypatch):
    """Without it a browser took an edited module from its cache after a
    plain reload, and the viewer showed a response shape that was gone."""
    client = TestClient(app_with(monkeypatch, True))
    response = client.get('/devtools/static/search.js')
    assert response.headers['cache-control'] == 'no-cache'
    etag = response.headers['etag']
    again = client.get('/devtools/static/search.js', headers={'if-none-match': etag})
    assert again.status_code == 304

def test_mounted_when_on(monkeypatch):
    client = TestClient(app_with(monkeypatch, True))
    response = client.get('/devtools')
    assert response.status_code == 200
    assert 'devtools' in response.text
    for asset in ('main.js', 'tiles.js', 'search.js', 'catpicker.js', 'mapview.js', 'api.js',
                  'urlstate.js', 'wkt.js', 'i18n.js', 'devtools.css'):
        assert client.get(f'/devtools/static/{asset}').status_code == 200, asset


def test_the_page_never_carries_a_key(monkeypatch):
    """A key rendered into the HTML puts a real key in the source of any
    page that serves it."""
    secret = 'k-production-do-not-leak-0123'
    client = TestClient(app_with(monkeypatch, True, keys=[secret]))
    assert secret not in client.get('/devtools').text


@pytest.mark.parametrize(('lang', 'field', 'button'), [('de', 'API-Schlüssel', 'Übernehmen'),
                                                       ('en', 'API key', 'Use')])
def test_the_key_notice_names_the_field_and_button_it_points_to(monkeypatch, lang, field, button):
    """The notice over the map is rendered hidden and shown by the script on
    a 401 from /status. It sends the viewer to the Status tab's key field, so
    it must name that field and its button as the tab labels them."""
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'lang': lang}).text
    notice = re.search(r'<div class="key-notice hidden" id="keyNotice"[^>]*>(.*?)</button>', text, re.S)
    assert notice, 'the notice is rendered, hidden'
    assert field in notice.group(1) and button in notice.group(1)
    assert f'<label class="field-label" for="apiKey">{field}</label>' in text
    assert f'id="apiKeyApply" type="submit">{button}</button>' in text


def test_the_page_carries_the_served_formats(monkeypatch):
    """From web/formats.py, so the page never keeps a second list."""
    import json
    import re

    from web import formats

    text = TestClient(app_with(monkeypatch, True)).get('/devtools').text
    meta = re.search(r'<meta name="formats" content=\'([^\']*)\'>', text).group(1)
    assert json.loads(meta) == {f: formats.mime_for(f) for f in formats.RASTER}


def test_the_page_is_german_by_default_and_english_on_request(monkeypatch):
    client = TestClient(app_with(monkeypatch, True))
    german = client.get('/devtools').text
    assert '<html lang="de">' in german
    assert 'Kartenstile neu laden' in german
    assert 'Reload themes' not in german

    english = client.get('/devtools', params={'lang': 'en'}).text
    assert '<html lang="en">' in english
    assert 'Reload themes' in english
    assert 'Kartenstile neu laden' not in english


@pytest.mark.parametrize(('lang', 'other', 'name'), [('de', 'en', 'English'), ('en', 'de', 'Deutsch')])
def test_the_language_switch_offers_only_the_other_language(monkeypatch, lang, other, name):
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'lang': lang}).text
    switch = re.search(r'<nav class="lang-switch">(.*?)</nav>', text).group(1)
    assert re.findall(r'data-lang="(\w+)"', switch) == [other]
    assert f'title="{name}"' in switch
    assert f'>{other.upper()}</a>' in switch


@pytest.mark.parametrize('tab', ['tiles', 'search', 'status'])
def test_the_requested_tab_is_rendered_in_front(monkeypatch, tab):
    """The script switches tabs only after the map has loaded; a page that
    left it to the script showed the tiles tab until then, on every reload
    and language switch from another tab."""
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'tab': tab}).text
    assert re.findall(r'name="tab" value="(\w+)" checked', text) == [tab]
    shown = re.findall(r'<div class="panel-controls" id="panel-(\w+)">', text)
    assert shown == [tab]


def test_an_unknown_tab_opens_the_first(monkeypatch):
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'tab': 'nope'}).text
    assert re.findall(r'name="tab" value="(\w+)" checked', text) == ['tiles']


def _checked(text: str, name: str) -> list[str]:
    return re.findall(rf'name="{name}" value="([\w-]+)" checked', text)


def test_every_control_is_rendered_as_the_url_sets_it(monkeypatch):
    """A language switch reloads the page with the state in the URL, and the
    scripts apply it only once the map has loaded: a control left to them
    showed its default until then -- and a field or checkbox the URL did not
    carry was lost."""
    from renderer import matrix

    grid = sorted(matrix.load())[-1]
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={
        'tab': 'search', 'theme': 'dark_max', 'mode': 'wmts-rest', 'grid': grid,
        'format': 'jpg', 'debug': '1', 'smode': 'address', 'q': 'kiel',
        'street': 'Holstenstraße', 'hn': '12', 'pc': '24103', 'city': 'Kiel', 'radius': '250',
        'cat': 'cat_geography', 'inview': '1', 'within': '0', 'sort': 'distance', 'sim': '7',
        'fuzzy': '1',
    }).text
    # Fuzzy is the name mode's alone, so the address mode disables the box.
    assert re.search(r'id="searchFuzzy" checked disabled>', text)
    assert '<option value="dark" selected>dark</option>' in text
    assert '<option value="max" selected>max</option>' in text
    assert _checked(text, 'mode') == ['wmts-rest']
    assert f'<option value="{grid}" selected>' in text
    assert '<option value="jpg" selected>' in text
    assert re.search(r'id="debugGrid" checked', text)
    assert _checked(text, 'smode') == ['address']
    assert 'class="panel-controls mode-address" id="panel-search"' in text
    for field, value in [('searchQuery', 'kiel'), ('addrStreet', 'Holstenstraße'),
                         ('addrNumber', '12'), ('addrPostcode', '24103'),
                         ('addrCity', 'Kiel'), ('hereRadius', '250')]:
        assert re.search(rf'id="{field}"[^>]* value="{value}"', text), field
    assert '>Geografie</span>' in text
    assert re.search(r'id="searchInView" checked', text)
    assert re.search(r'id="searchWithin" disabled', text)
    assert '<option value="distance" selected>' in text
    assert '<span id="searchSimilarityValue">7</span>' in text


def test_wms_is_a_request_mode_with_the_grid_picker(monkeypatch):
    """WMS renders in the grid's CRS, so unlike XYZ it keeps the grid picker."""
    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'mode': 'wms'}).text
    assert _checked(text, 'mode') == ['wms']
    assert re.search(r'<select id="grid">', text)


def test_the_defaults_without_a_url_state(monkeypatch):
    from search.request import DEFAULT_SIMILARITY

    text = TestClient(app_with(monkeypatch, True)).get('/devtools').text
    assert '<option value="default" selected>default</option>' in text
    assert '<option value="std" selected>Standard</option>' in text
    assert _checked(text, 'mode') == ['xyz']
    assert re.search(r'<select id="grid" disabled>', text)
    assert _checked(text, 'smode') == ['name']
    assert re.search(r'id="searchInView">', text)
    assert re.search(r'id="searchWithin" checked disabled>', text)
    assert re.search(r'id="searchFuzzy">', text)
    assert 'Die unscharfe Suche ist noch in Entwicklung' in text
    assert f'<span id="searchSimilarityValue">{DEFAULT_SIMILARITY}</span>' in text


@pytest.mark.parametrize(('theme', 'palette', 'detail'), [
    ('max', 'default', 'max'), ('dark', 'dark', 'std'), ('dark_min', 'dark', 'min'),
    ('std', 'default', 'std'),
])
def test_a_theme_url_name_is_read_back_into_palette_and_detail(theme, palette, detail):
    """The inverse of `serving.url_name`, which leaves out a default
    palette or detail."""
    from web import serving

    assert devtools._theme_parts(theme) == (palette, detail)
    assert serving.url_name(f'{palette}_{detail}') == theme


def test_a_typed_query_is_escaped_into_the_page(monkeypatch):
    text = TestClient(app_with(monkeypatch, True)).get(
        '/devtools', params={'q': '"><script>alert(1)</script>'}).text
    assert '<script>alert(1)' not in text
    assert 'value="&#34;&gt;&lt;script&gt;' in text


@pytest.mark.parametrize('lang', ['de', 'en'])
def test_the_page_carries_the_scripts_texts(monkeypatch, lang):
    """In an attribute quoted with ', so a text with an apostrophe ("what's
    here") must arrive escaped, or the JSON the scripts parse is cut off."""
    import json

    from lib import i18n

    text = TestClient(app_with(monkeypatch, True)).get('/devtools', params={'lang': lang}).text
    meta = re.search(r'<meta name="messages" content=\'([^\']*)\'>', text).group(1)
    assert json.loads(meta) == i18n.texts('devtools.js.', lang)


def _call_ids(source: str) -> set[str]:
    """The string literals in the first argument of every `t(...)` call --
    `t('id')`, `t(cond ? 'a' : 'b', {...})` -- in a script or the template."""
    ids = set()
    for match in re.finditer(r'(?<![\w.])t\(', source):
        depth, end = 1, match.end()
        while depth and end < len(source):
            char = source[end]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 1:
                break
            end += 1
        # The argument itself, or a branch of a conditional in it -- not the
        # literal a condition compares against.
        ids.update(re.findall(r"(?:^|[?:])\s*'([\w.]+)'", source[match.end():end]))
    return ids


def test_every_text_a_script_or_the_page_asks_for_is_in_the_catalogue():
    """A script's `t('id')` with no entry throws only when that line runs in
    a browser -- a tooltip, an error path -- which nothing here exercises."""
    from lib import i18n

    here = Path(devtools.__file__).resolve().parent
    catalogue = i18n.messages()
    for script in sorted((here / 'static').glob('*.js')):
        for message_id in _call_ids(script.read_text()):
            assert f'devtools.js.{message_id}' in catalogue, f'{script.name}: {message_id}'
    for message_id in _call_ids((here / 'templates' / 'devtools.html').read_text()):
        assert message_id in catalogue, f'devtools.html: {message_id}'


def test_the_viewer_is_not_in_the_api_reference(monkeypatch):
    app = app_with(monkeypatch, True)
    paths = TestClient(app).get('/openapi.json').json()['paths']
    assert not any(path.startswith('/devtools') for path in paths)


# --- the two endpoints the browser needs ---------------------------------

@pytest.fixture
def client(monkeypatch, db):
    return TestClient(app_with(monkeypatch, True))


def test_every_configured_grid_is_described(client):
    from renderer import matrix

    grids = client.get('/devtools/api/grids').json()
    assert set(grids) == {tms.identifier for tms in matrix.load().values()}


def test_a_grid_has_what_a_leaflet_crs_needs(client):
    for identifier, grid in client.get('/devtools/api/grids').json().items():
        levels = len(grid['resolutions'])
        assert levels > 0, identifier
        assert len(grid['matrix_widths']) == len(grid['matrix_heights']) == levels
        assert len(grid['origin']) == 2
        # Each level halves the resolution: a quadtree.
        assert grid['resolutions'][1] == pytest.approx(grid['resolutions'][0] / 2)


def test_web_mercator_is_native_and_the_rest_carry_proj4(client):
    """Leaflet knows EPSG:3857; every other grid is drawn through
    Proj4Leaflet with the definition PostGIS holds, so the browser projects
    with the same definition the database reprojects with."""
    grids = client.get('/devtools/api/grids').json()
    assert grids['GoogleMapsCompatible']['native'] is True
    for grid in grids.values():
        if not grid['native']:
            assert grid['proj4'] and grid['proj4'].startswith('+proj=')


def test_the_web_mercator_resolutions_are_the_standard_ones(client):
    grid = client.get('/devtools/api/grids').json()['GoogleMapsCompatible']
    assert grid['resolutions'][0] == pytest.approx(156_543.033928, rel=1e-9)


def test_the_precache_depth_is_reported(client):
    # Shown in the page, because "why is this zoom slow" is usually this.
    from renderer import cache
    grids = client.get('/devtools/api/grids').json()
    for identifier, depth in cache.precache_depths().items():
        assert grids[identifier]['precache_depth'] == depth


def test_the_extent_is_the_imported_area(monkeypatch, db, small):
    from lib import config
    from lib import db as db_module

    real = config.opt
    monkeypatch.setattr(config, 'opt', lambda path, default=None:
                        True if path == 'devtools' else real(path, default))
    monkeypatch.setattr(db_module, 'active_schema', lambda area=None: small)
    app = FastAPI()
    devtools.mount(app)
    body = TestClient(app).get('/devtools/api/extent').json()
    west, south, east, north = body['bbox']
    # Liechtenstein.
    assert 9.4 < west < east < 9.7
    assert 47.0 < south < north < 47.3


def test_an_area_nobody_imported_has_no_extent_rather_than_an_error(monkeypatch, db):
    from lib import config

    real = config.opt
    monkeypatch.setattr(config, 'opt', lambda path, default=None:
                        True if path == 'devtools' else
                        'no_such_area_here' if path == 'serve_area' else real(path, default))
    app = FastAPI()
    devtools.mount(app)
    response = TestClient(app).get('/devtools/api/extent')
    assert response.status_code == 200
    assert response.json()['bbox'] is None


# --- the style watcher --------------------------------------------------------

@pytest.fixture
def recompile_steps(monkeypatch):
    """The watcher's three steps replaced by a record of their calls."""
    from lib import db as db_module
    from renderer import cache, styles
    from web import meta
    from web.devtools import watcher

    calls = []
    monkeypatch.setattr(styles, 'run', lambda schema: calls.append('styles'))
    monkeypatch.setattr(cache, 'clear_area', lambda area: calls.append('cache'))
    monkeypatch.setattr(db_module, 'active_schema', lambda area=None: 'area_1_20260101_000000')
    monkeypatch.setattr(meta, 'reload_all', lambda: calls.append('reload'))
    monkeypatch.setattr(watcher, '_state', dict(watcher._state, compiles=0, error=None))
    return calls


def test_a_recompile_compiles_clears_the_cache_and_reloads(recompile_steps):
    """In that order: a reload before the cache is cleared serves the old
    tiles under the new generation."""
    from web.devtools import watcher

    watcher.recompile(['palettes.yaml'])
    assert recompile_steps == ['styles', 'cache', 'reload']
    state = watcher.state()
    assert state['compiles'] == 1
    assert state['error'] is None
    assert state['running'] is False
    assert state['changed'] == ['palettes.yaml']


def test_a_failed_recompile_is_reported_and_serves_the_old_styles(recompile_steps, monkeypatch):
    """The page redraws when `compiles` moves, so a failure must not move it."""
    from renderer import styles
    from web.devtools import watcher

    def fail(schema):
        raise styles.GenerationError('problem_1\nproblem_2')

    monkeypatch.setattr(styles, 'run', fail)
    watcher.recompile(['details.yaml'])
    state = watcher.state()
    assert state['compiles'] == 0
    assert state['error'] == 'problem_1\nproblem_2'
    assert state['running'] is False
    assert recompile_steps == []


def test_a_change_under_the_directory_is_recompiled(tmp_path, monkeypatch):
    """The icons are in a subdirectory, and a change there is a change."""
    import threading

    from web.devtools import watcher

    seen = []
    done = threading.Event()

    def recompile(changed):
        seen.append(changed)
        if changed != watcher.STARTUP:
            done.set()

    monkeypatch.setattr(watcher, 'recompile', recompile)
    (tmp_path / 'icons').mkdir()
    running = watcher.Watcher(tmp_path).start()
    try:
        for _ in range(20):
            if watcher.state()['watching']:
                break
            threading.Event().wait(0.1)
        # watchfiles subscribes just after the thread says it is watching.
        threading.Event().wait(0.3)
        (tmp_path / 'icons' / 'file_1.svg').write_text('<svg/>')
        assert done.wait(10), 'no recompile after a change'
    finally:
        running.stop()
    # Compiled once at start, whatever changed while the server was down.
    assert seen == [watcher.STARTUP, ['icons/file_1.svg']]
    assert watcher.state()['watching'] is False


def test_no_watcher_when_off(monkeypatch):
    app_with(monkeypatch, False)
    assert devtools.start_watcher() is None


def test_the_watcher_is_off_by_default():
    """The page polls it every 1.5 s, which on a deployment only fills the
    proxy's access log."""
    import yaml

    from lib.config import DEFAULTS_PATH
    assert yaml.safe_load(DEFAULTS_PATH.read_text())['devtools_watch'] is False


def test_no_watcher_with_the_viewer_alone(monkeypatch):
    app_with(monkeypatch, True, watch=False)
    assert devtools.start_watcher() is None


@pytest.mark.parametrize('watch', [True, False])
def test_the_page_says_whether_to_poll_the_watcher(monkeypatch, watch):
    client = TestClient(app_with(monkeypatch, True, watch=watch))
    expected = 'on' if watch else 'off'
    assert f'<meta name="watch" content="{expected}">' in client.get('/devtools').text


def test_the_page_reads_the_watcher_state(monkeypatch):
    client = TestClient(app_with(monkeypatch, True))
    state = client.get('/devtools/api/watch').json()
    assert {'watching', 'running', 'compiles', 'changed', 'error'} <= set(state)
