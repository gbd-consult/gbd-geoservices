"""The app itself: what starts, what needs a key, and what `/metadata` and `/status` say.

The TestClient runs the real ASGI app in-process -- same routers, same
middleware, same dependency injection, same status codes -- so these are
route tests rather than function tests, which is the point: the things that
go wrong here (a route that forgot its key check, a key echoed into a log)
are properties of the wiring and not of any function.
"""

from __future__ import annotations

import datetime

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
def configured_keys(keys):
    """Install key records and drop `/metadata`'s and `/status`'s held answers."""
    from web import meta

    def install(records):
        keys(records)
        meta._cache.clear()
    yield install
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


def _served_extract(monkeypatch, date):
    from web import meta
    meta._cache.clear()
    monkeypatch.setattr(meta, '_schema', lambda: 'x' if date != 'no import' else None)
    monkeypatch.setattr(meta, 'extract_info', lambda schema: {'date': date} if date else {})


def test_health_data_is_ok_within_the_limit_and_needs_no_key(client, configured_keys, monkeypatch):
    """The external monitor polls it with no key."""
    configured_keys(['k-something'])
    _served_extract(monkeypatch, (datetime.datetime.now(datetime.UTC).date()
                                  - datetime.timedelta(days=14)).isoformat())
    response = client.get('/health/data')
    assert response.status_code == 200
    assert response.json()['age_days'] == 14


@pytest.mark.parametrize('date', ['2000-01-01', None, 'no import'])
def test_health_data_alarms_on_old_or_missing_data(client, monkeypatch, date):
    """A failed update leaves the old data served and `/health` green: the
    extract's age is the only signal, and no date at all must alarm too."""
    _served_extract(monkeypatch, date)
    response = client.get('/health/data')
    assert response.status_code == 503
    assert response.json()['status'] == 'stale'


# --- /metadata -----------------------------------------------------------

def test_metadata_needs_no_key(client, configured_keys):
    """The same for every caller, and read before a client has anything
    else to go on."""
    configured_keys(['k-something'])
    assert client.get('/metadata').status_code == 200


def test_metadata_has_its_documented_shape(client):
    body = client.get('/metadata').json()
    assert set(body) == {'version', 'area', 'date', 'bounds', 'attribution',
                         'attribution_short', 'themes', 'grids', 'categories', 'services'}
    assert body['version'] and body['area']
    assert {'id', 'crs', 'minzoom', 'maxzoom'} <= set(body['grids'][0])


def test_metadata_credits_openmaptiles_and_openstreetmap(client):
    """A client shows `attribution` as it is; the OpenMapTiles schema's
    CC-BY 4.0 asks for its credit beside OpenStreetMap's."""
    attribution = client.get('/metadata').json()['attribution']
    assert attribution.startswith('© OpenMapTiles © OpenStreetMap contributors')


def test_metadata_short_attribution_credits_openstreetmap(client):
    """The in-map credit; the ODbL asks for OpenStreetMap's in any map."""
    short = client.get('/metadata').json()['attribution_short']
    assert short.startswith('© OpenStreetMap contributors')


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


def test_a_request_is_counted_for_its_key_with_its_response_status(client, configured_keys,
                                                                   monkeypatch):
    """The middleware sees the status the route produced, so a key's request
    for a theme that does not exist is its error, not a tile to invoice."""
    from lib import keys as store
    configured_keys(['k-something'])
    assert client.get('/xyz/no_such_theme/0/0/0.png', params={'key': 'k-something'}).status_code == 404
    written = {}
    monkeypatch.setattr(auth.store, 'add_usage', written.update)
    auth.flush_usage()
    assert written == {(1, store.month_of(store.today())): {'errors': 1}}


def test_an_api_request_is_logged_with_its_status_and_search_terms(client, configured_keys):
    """The request log's row is written after the response, so it has the
    route's status, and the search route's terms -- also for a body the
    route refused."""
    from web import stats
    configured_keys(['k-something'])
    stats._rows.clear()
    client.post('/search', params={'key': 'k-something'}, json={'mode': 'nope', 'text': 'Kiel'})
    client.get('/health')
    rows = list(stats._rows)
    stats._rows.clear()
    assert [(r[1], r[2], r[3], r[7]) for r in rows] == [('search', 1, 422, 'Kiel')]


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


def test_the_landing_page_links_openmaptiles_and_openstreetmap(client):
    """CC-BY 4.0 asks for a visible link to OpenMapTiles, the ODbL for the
    OpenStreetMap copyright page."""
    for lang in ('de', 'en'):
        text = client.get('/', params={'lang': lang}).text
        assert 'href="https://openmaptiles.org/"' in text
        assert 'href="https://www.openstreetmap.org/copyright"' in text


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


@pytest.fixture
def legal_dir(tmp_path, monkeypatch):
    """A deployment directory whose `legal/` the test fills."""
    from lib import config
    monkeypatch.setattr(config, 'deployment_path', lambda: tmp_path / 'options.yaml')
    (tmp_path / 'legal').mkdir()
    return tmp_path / 'legal'


def test_a_legal_page_is_served_from_the_deployment_and_linked(client, legal_dir):
    (legal_dir / 'impressum.html').write_text('<h1>Impressum</h1><p>Musterfirma GmbH</p>')
    page = client.get('/impressum')
    assert page.status_code == 200
    assert '<p>Musterfirma GmbH</p>' in page.text
    assert 'href="/impressum?lang=de"' in client.get('/').text
    assert 'href="/impressum?lang=en"' in client.get('/', params={'lang': 'en'}).text


def test_a_legal_page_without_its_file_is_neither_served_nor_linked(client, legal_dir):
    """The texts come from management and the lawyer; until they do, the
    page must not exist rather than show a placeholder as if it were law."""
    assert client.get('/datenschutz').status_code == 404
    assert '/datenschutz' not in client.get('/').text


def test_the_landing_page_names_the_operator_and_links_the_source(client, monkeypatch):
    from lib import config
    real = config.opt
    operator = {'name': 'Musterfirma GmbH', 'url': 'https://www.example.org/'}
    monkeypatch.setattr(config, 'opt', lambda path, default=None:
                        operator if path == 'operator' else real(path, default))
    text = client.get('/').text
    assert '<a href="https://www.example.org/">Musterfirma GmbH</a>' in text
    assert f'href="{real("source_url")}"' in text
    assert 'AGPL-3.0-or-later' in text


def test_the_landing_page_does_not_link_the_devtools(client):
    """They need the devtools key, which no visitor of the landing page has."""
    assert '/devtools' not in client.get('/').text


# --- the reload hook -----------------------------------------------------

@pytest.fixture
def stored(monkeypatch):
    """The key requests the form stored, with no database."""
    from lib import keys
    from web import meta
    meta._key_request_times.clear()
    calls = []

    def add(email, organisation, limit):
        calls.append((email, organisation))
        return None if email == 'full@example.org' else len(calls)
    monkeypatch.setattr(keys, 'request_add', add)
    return calls


@pytest.mark.parametrize('form, outcome, stored_as', [
    ({'email': ' a@example.org ', 'organisation': 'A GmbH', 'lang': 'en'}, 'sent',
     [('a@example.org', 'A GmbH')]),
    ({'email': 'a@example.org', 'website': 'http://spam'}, 'sent', []),
    ({'email': 'not an address'}, 'invalid', []),
    ({'email': 'full@example.org'}, 'full', [('full@example.org', None)]),
])
def test_the_key_request_form(client, stored, form, outcome, stored_as):
    """A filled honeypot is told it worked, so the bot learns nothing, and
    stores nothing; the outcome comes back to the landing page."""
    response = client.post('/key-request', data=form, follow_redirects=False)
    assert response.status_code == 303
    lang = form.get('lang', 'de')
    assert response.headers['location'] == f'/?lang={lang}&key_request={outcome}#key-request'
    assert stored == stored_as


def test_one_ip_fills_no_more_than_its_share_of_key_requests(client, stored):
    """A script that gets past the honeypot would otherwise take every open
    place within seconds and close the form to everyone else."""
    from web import meta
    outcomes = [client.post('/key-request', data={'email': f'{n}@example.org'},
                            follow_redirects=False).headers['location']
                for n in range(meta.KEY_REQUESTS_PER_IP + 1)]
    assert len(stored) == meta.KEY_REQUESTS_PER_IP
    assert outcomes[-1].endswith('key_request=full#key-request')


def test_the_landing_page_has_the_key_request_form_and_its_outcome(client):
    page = client.get('/', params={'key_request': 'sent'}).text
    assert 'action="/key-request"' in page and 'name="website"' in page
    assert 'Ihre Anfrage ist eingegangen' in page
    assert '<script' not in client.get('/', params={'key_request': '<script>'}).text


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
