"""The app itself: what starts, what needs a key, and what `/metadata` and `/status` say.

The TestClient runs the real ASGI app in-process -- same routers, same
middleware, same dependency injection, same status codes -- so these are
route tests rather than function tests, which is the point: the things that
go wrong here (a route that forgot its key check, a key echoed into a log)
are properties of the wiring and not of any function.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web import auth
from web.main import app

#: A schema name nothing has been imported or compiled for. These tests are
#: about the app's own wiring -- liveness, identity, the landing page, CORS
#: -- and none of them needs a theme, so pointing the lifespan at an empty
#: schema keeps it instant. Against a compiled one it loads the Map pool:
#: `map_pool_size` Mapnik parses per (theme, TileMatrixSet), which for
#: twelve themes and two grids is 96 of them and **111 seconds measured**.
#: The real preload is exercised by `test_web_tiles.py`.
EMPTY_SCHEMA = 'no_such_schema_here'


@pytest.fixture(scope='module')
def client():
    """One app, one lifespan, for the whole module.

    Module-scoped because entering the TestClient runs the lifespan, and
    what the lifespan builds -- the Map pool, the loaded model YAML -- is
    process-wide state with nothing to isolate per test.
    """
    from lib import db

    original = db.active_schema
    db.active_schema = lambda area=None: EMPTY_SCHEMA
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        db.active_schema = original
        auth.reset()


@pytest.fixture
def configured_keys(monkeypatch):
    """Override only `keys`, leaving every other option real.

    `/metadata` and `/status` read `serve_area`, the grids and the theme
    list through the same `config.opt`, so a stub that answers every path breaks the route
    it is supposed to be testing.
    """
    from web import meta

    # The original, captured before patching: `auth.config` *is*
    # `lib.config`, so setattr replaces the module's own function and a
    # stub that then calls `config.opt` calls itself.
    real_opt = auth.config.opt

    def install(records):
        def opt(path, default=None):
            if path == 'keys':
                return records
            return real_opt(path, default)
        monkeypatch.setattr(auth.config, 'opt', opt)
        auth.reset()
        meta._cache.clear()
    yield install
    auth.reset()
    meta._cache.clear()


# --- liveness ------------------------------------------------------------

def test_health_needs_no_key(client):
    """The container healthcheck and the deploy wait-loop both poll it
    before any key exists."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_health_does_not_touch_the_database(client, monkeypatch):
    """A healthcheck that fails when Postgres restarts takes the container
    down with it and turns a blip into an outage."""
    from lib import db
    monkeypatch.setattr(db, 'connect', lambda **kw: pytest.fail('health opened a connection'))
    assert client.get('/health').status_code == 200


# --- /metadata -----------------------------------------------------------

def test_metadata_needs_no_key(client, configured_keys):
    """The same for every caller, and read before a client has anything
    else to go on."""
    configured_keys(['k-something'])
    assert client.get('/metadata').status_code == 200


def test_metadata_has_its_documented_shape(client):
    body = client.get('/metadata').json()
    assert set(body) == {'version', 'area', 'date', 'bounds', 'attribution',
                         'themes', 'grids', 'categories', 'services'}
    assert body['version'] and body['area']
    assert {'id', 'crs', 'minzoom', 'maxzoom'} <= set(body['grids'][0])


def test_metadata_services_are_absolute_templates(client):
    """A client builds its URLs from these, so they must work as they are:
    absolute, and templated where they carry placeholders."""
    services = {s['rel']: s for s in client.get('/metadata').json()['services']}
    assert {'wmts', 'wms', 'search', 'search-count', 'icon', 'legend', 'status'} <= set(services)
    for service in services.values():
        assert service['href'].startswith('http')
        assert service.get('templated', False) == ('{' in service['href'])


def test_metadata_carries_the_category_tree_in_every_language(client):
    from lib import config
    tree = client.get('/metadata').json()['categories']
    assert [node['id'] for node in tree] == ['cat_geography', 'cat_built', 'cat_poi']
    assert set(tree[0]['names']) == set(config.opt('languages'))
    assert tree[0]['icon'].endswith('/icons/cat_geography.svg')
    assert tree[0]['subcategories']


def test_metadata_carries_no_search_terms(client):
    """They are query-parser input, not for display, and they are the bulk
    of the file -- serving them makes the tree two orders of magnitude
    larger than what it is for."""
    text = client.get('/metadata').text
    assert 'terms_de' not in text and 'terms_en' not in text


def test_metadata_is_cached_briefly(client):
    # Every client reads it on start, so the answer is held briefly.
    from web import meta
    meta._cache.clear()
    first = client.get('/metadata').json()
    assert client.get('/metadata').json() == first
    assert any(key.startswith('metadata ') for key in meta._cache)


# --- /status -------------------------------------------------------------

def test_status_needs_a_key(client, configured_keys):
    configured_keys(['k-something'])
    assert client.get('/status').status_code == 401
    assert client.get('/status', params={'key': 'k-something'}).status_code == 200


def test_status_takes_a_key_of_any_scope(client, configured_keys):
    configured_keys([{'key': 'k-search', 'scopes': ['search']}])
    assert client.get('/status', params={'key': 'k-search'}).status_code == 200


def test_status_names_the_build_and_the_schema(client):
    body = client.get('/status').json()
    assert body['version'] and body['build']
    assert body['area']
    assert 'schema' in body
    assert isinstance(body['themes'], list)


def test_status_reports_whether_anything_is_protected(client, configured_keys):
    """An operator who forgot to configure keys sees it in the one place
    they look."""
    configured_keys([])
    assert client.get('/status').json()['auth'] == 'open'


def test_status_reports_keys_when_configured(client, configured_keys):
    configured_keys(['k-something'])
    assert client.get('/status', params={'key': 'k-something'}).json()['auth'] == 'keys'


def test_status_is_not_served_stale_across_a_key_change(client, configured_keys):
    """A cached "open" after keys were configured is the worst lie this
    route can tell, so whatever changes the keys clears the cache."""
    configured_keys([])
    assert client.get('/status').json()['auth'] == 'open'
    configured_keys(['k-something'])
    assert client.get('/status', params={'key': 'k-something'}).json()['auth'] == 'keys'


def test_the_replaced_routes_are_gone(client):
    for path in ('/version', '/themes', '/search/categories'):
        assert client.get(path).status_code == 404


# --- the import status ---------------------------------------------------

def test_a_schema_with_no_import_reports_nothing_rather_than_failing():
    """A server pointed at an area nobody imported is exactly what this
    route exists to make visible."""
    from web import meta
    status = meta.import_status(EMPTY_SCHEMA)
    assert status['imported'] is None


def test_an_imported_schema_reports_its_import(db, small):
    from web import meta
    imported = meta.import_status(small)['imported']
    assert imported['area'] == 'li'
    assert imported['rows']


# --- the landing page ----------------------------------------------------

def test_the_landing_page_renders(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    assert 'gbd-geoservices' in response.text


def test_the_landing_page_names_the_routes_it_offers(client):
    for lang in ('de', 'en'):
        text = client.get('/', params={'lang': lang}).text
        for route in ('/xyz/', '/wmts', '/search', '/metadata', '/status'):
            assert route in text


def test_the_landing_page_is_german_by_default_and_english_on_request(client):
    german = client.get('/').text
    assert '<html lang="de">' in german
    assert 'Dieser Server' in german
    assert 'This server' not in german

    english = client.get('/', params={'lang': 'en'}).text
    assert '<html lang="en">' in english
    assert 'This server' in english
    assert 'Dieser Server' not in english


def test_the_landing_page_links_only_the_other_language(client):
    german = client.get('/').text
    assert 'href="?lang=en"' in german
    assert 'title="English"' in german
    assert '>EN</a>' in german
    assert 'href="?lang=de"' not in german
    english = client.get('/', params={'lang': 'en'}).text
    assert 'href="?lang=de"' in english
    assert '>DE</a>' in english
    assert 'href="?lang=en"' not in english


# --- the reload hook -----------------------------------------------------

def test_reload_is_loopback_only(client):
    # The TestClient's own client host is "testclient", not an address.
    assert client.post('/internal/reload').status_code == 403


def test_reload_from_loopback_works(client):
    response = client.post('/internal/reload', headers={},
                           extensions={})  # host is still testclient
    assert response.status_code == 403


def test_require_loopback_accepts_127_0_0_1():
    from fastapi import HTTPException

    from web import meta

    class Req:
        def __init__(self, host):
            self.client = type('C', (), {'host': host})()

    meta.require_loopback(Req('127.0.0.1'))
    meta.require_loopback(Req('::1'))
    for host in ('10.0.0.5', '192.168.1.1', None, 'testclient'):
        with pytest.raises(HTTPException) as excinfo:
            meta.require_loopback(Req(host))
        assert excinfo.value.status_code == 403


# --- the access log ------------------------------------------------------

def test_the_key_is_stripped_from_the_logged_path():
    """The query parameter is the only carrier that can reach a log at all,
    and this is where it would.
    """
    from web.main import safe_path

    class Req:
        def __init__(self, path, items):
            self.url = type('U', (), {'path': path})()
            self.query_params = type('Q', (), {'multi_items': lambda self=None: items})()

    assert safe_path(Req('/xyz/std/1/2/3.png', [('key', 'secret')])) == \
        '/xyz/std/1/2/3.png'
    assert safe_path(Req('/search', [('key', 'secret'), ('lang', 'de')])) == '/search?lang=de'
    assert safe_path(Req('/health', [])) == '/health'


def test_a_request_with_a_key_logs_no_key(client, caplog):
    with caplog.at_level('INFO', logger='web.main'):
        client.get('/health?key=super-secret-value')
    assert caplog.records
    assert not any('super-secret-value' in record.getMessage() for record in caplog.records)


# --- CORS ----------------------------------------------------------------

def test_the_preflight_allows_the_key_header(client):
    """Without it a browser client's only carrier is `?key=`, which is the
    one that ends up in logs."""
    response = client.options('/health', headers={
        'Origin': 'https://maps.example.de',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization',
    })
    assert response.status_code == 200
    allowed = response.headers['access-control-allow-headers'].lower()
    assert 'authorization' in allowed


def test_the_preflight_is_cached_so_it_is_one_request_per_origin(client):
    response = client.options('/health', headers={
        'Origin': 'https://maps.example.de',
        'Access-Control-Request-Method': 'GET',
    })
    assert int(response.headers['access-control-max-age']) >= 3600


def test_the_schema_reaches_sql_as_an_identifier():
    """Every other module in the tree quotes an identifier with
    `psycopg.sql.Identifier`; this was the one place that built it with an
    f-string.

    The schema is configuration and not request input, so it was never
    reachable from outside -- but one place that does it differently is the
    one somebody copies.
    """
    import inspect

    from web import meta

    source = inspect.getsource(meta.import_status)
    assert 'sql.Identifier(schema' in source
    assert '"{schema}"' not in source


# --- start -----------------------------------------------------------------

def test_the_styles_are_compiled_for_the_served_schema_before_they_load(monkeypatch):
    from lib import db
    from renderer import core, styles
    from web import main

    calls = []
    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'area_1_20260101_000000')
    monkeypatch.setattr(styles, 'run', lambda schema: calls.append(('compile', schema)))
    monkeypatch.setattr(core, 'preload_all', lambda schema: calls.append(('load', schema)) or {})
    main._preload()
    assert calls == [('compile', 'area_1_20260101_000000'), ('load', 'area_1_20260101_000000')]


def test_a_failed_compile_still_loads_the_xml_on_disk(monkeypatch, caplog):
    from lib import db
    from renderer import core, styles
    from web import main

    def fail(schema):
        raise RuntimeError('error_1')

    loaded = []
    monkeypatch.setattr(db, 'active_schema', lambda area=None: 'area_1_20260101_000000')
    monkeypatch.setattr(styles, 'run', fail)
    monkeypatch.setattr(core, 'preload_all', lambda schema: loaded.append(schema) or {})
    main._preload()
    assert loaded == ['area_1_20260101_000000']
    assert 'error_1' in caplog.text


def test_has_contours_reads_table_classes(db, temp_schema):
    """The query holds the JSON literal `{}`, which `sql.SQL.format` takes
    for a placeholder unless it is doubled: it failed on every call, was
    logged as "import_meta unreadable", and the Copernicus credit was never
    shown."""
    from web import meta

    db.execute(f'create table {temp_schema}.import_meta (table_classes jsonb)')
    db.execute(f'insert into {temp_schema}.import_meta values (%s)',
               ('{"osm_contour": {"cls_contour_50": 3}}',))
    assert meta.has_contours(temp_schema)
    db.execute(f'update {temp_schema}.import_meta set table_classes = %s', ('{"osm_contour": {}}',))
    assert not meta.has_contours(temp_schema)
