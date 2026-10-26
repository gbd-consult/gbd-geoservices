"""What this server serves, how it is doing, and the reload hook.

    GET  /            the landing page
    GET  /health      liveness, no key
    GET  /metadata    what a client needs to use the server, no key
    GET  /status      what an operator needs, any valid key
    POST /internal/reload   loopback only

`/metadata` is the one document a client reads first: version, area, the
extract's date and bounds, the themes, the grids, the category tree with
names in every served language and icon URLs, and the services as URL
templates (RFC 6570 placeholders, `templated: true`) with a `rel` to pick
them by. The same for every caller, so it takes no key; tile and search
URLs still need theirs.

`/status` is the operator's: build, schema, whether keys are configured,
`import_meta`'s extract, replication position, time and row counts, and
each theme's generation, the Map pool's reload counter that tile URLs
carry as `?v=`; no `import_meta` row means an incomplete import
(`DESIGN.md` "Schemas and imports"). Any valid key, whatever its scopes: it reports no data,
but it is not a client's business.

`/health` takes no key because the container healthcheck polls it before
any key exists.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from lib import config, db, i18n
from lib.version import __version__, build_id
from web import auth, serving
from web import icons as icon_routes
from web import legend as legend_routes

_log = logging.getLogger(__name__)

router = APIRouter(tags=['meta'])

#: `/metadata` and `/status` read the database and walk the category tree.
#: Cheap, but a client reads `/metadata` on every start and a monitor polls
#: `/status`, so each answer is held briefly -- `/metadata` per base URL,
#: since its URLs are absolute.
CACHE_SECONDS = 30.0

#: Shown with every map built from these tiles.
ATTRIBUTION = '© OpenStreetMap contributors'
#: Added where the served schema has contour lines (importer/elevation.py):
#: Copernicus GLO-30 is free on the condition that it is credited so.
ELEVATION_ATTRIBUTION = ('© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 '
                         'provided under COPERNICUS by the European Union and ESA')

_cache: dict[str, Any] = {}


def _cached(key: str, build) -> Any:
    now = time.monotonic()
    entry = _cache.get(key)
    if entry is None or now - entry[0] > CACHE_SECONDS:
        entry = (now, build())
        _cache[key] = entry
    return entry[1]


@router.get('/health')
def health() -> dict:
    """Liveness only: the process is up and serving.

    Deliberately not readiness -- it does not touch the database, because a
    healthcheck that fails when Postgres restarts takes the container down
    with it and turns a recoverable blip into an outage. `/status` is where
    you look for whether the data is there.
    """
    return {'status': 'ok'}


@router.get('/metadata')
def metadata(request: Request) -> dict:
    """Version, area, extract date and bounds, themes, grids, categories, services."""
    base = str(request.base_url).rstrip('/')
    return _cached(f'metadata {base}', lambda: collect_metadata(base))


def collect_metadata(base: str) -> dict:
    """Everything `/metadata` reports, read fresh."""
    from renderer import core, matrix
    from search import api as search_api

    schema = _schema()
    extract = extract_info(schema) if schema else {}
    grids = matrix.load()
    return {
        'version': __version__,
        'area': config.opt('serve_area'),
        'date': extract.get('date'),
        'bounds': extract.get('bounds'),
        'attribution': attribution(schema),
        'themes': [_theme(name) for name in (core.available_themes(schema) if schema else [])],
        'grids': [{'id': tms.identifier, 'crs': tms.crs, 'minzoom': 0, 'maxzoom': tms.levels - 1}
                  for tms in grids.values()],
        'categories': search_api.categories(icon=lambda category: icon_routes.url(base, category)),
        'services': services(base, grids),
    }


def _theme(name: str) -> dict:
    palette, _, detail = name.partition('_')
    return {'id': serving.url_name(name), 'palette': palette, 'detail': detail}


def services(base: str, grids: dict) -> list[dict]:
    """The routes a client calls, as links. Tile links need `?key=` added."""
    from renderer import matrix
    from web import formats

    out = []
    if matrix.by_crs(grids, 'EPSG:3857') is not None:
        out.append({'rel': 'tiles', 'href': f'{base}/xyz/{{theme}}/{{z}}/{{x}}/{{y}}.{{format}}',
                    'templated': True, 'formats': list(formats.RASTER)})
    out += [
        {'rel': 'wmts-tiles',
         'href': f'{base}/wmts/{{theme}}/{{grid}}/{{level}}/{{col}}/{{row}}.{{format}}',
         'templated': True, 'formats': list(formats.RASTER)},
        {'rel': 'wmts', 'href': f'{base}/wmts?SERVICE=WMTS&REQUEST=GetCapabilities'},
        {'rel': 'wms', 'href': f'{base}/wms?SERVICE=WMS&REQUEST=GetCapabilities'},
        {'rel': 'search', 'href': f'{base}/search', 'method': 'POST'},
        {'rel': 'search-count', 'href': f'{base}/search/count', 'method': 'POST'},
        {'rel': 'icon', 'href': icon_routes.url(base, '{category}'), 'templated': True},
        {'rel': 'legend', 'href': legend_routes.url(base, '{theme}'), 'templated': True},
        {'rel': 'status', 'href': f'{base}/status'},
    ]
    return out


@router.get('/status', dependencies=[Depends(auth.requires_key)])
def status() -> dict:
    """Build, schema, auth, the import, and each theme's generation."""
    return _cached('status', collect_status)


def collect_status() -> dict:
    """Everything `/status` reports, read fresh."""
    from renderer import core

    schema = _schema()
    registry = core.get_registry()
    out: dict[str, Any] = {
        'version': __version__,
        'build': build_id(),
        'area': config.opt('serve_area'),
        'schema': schema,
        # Not "is a key required" -- "is anything protected". An operator
        # who forgot to configure keys sees it here.
        'auth': 'open' if auth.open_access() else 'keys',
        'themes': [{'id': serving.url_name(name), 'generation': registry.generation(name)}
                   for name in (core.available_themes(schema) if schema else [])],
    }
    out.update(import_status(schema) if schema else {'imported': None})
    return out


def _schema() -> str | None:
    try:
        return db.active_schema()
    except db.NoImportError:
        return None


def extract_info(schema: str) -> dict:
    """The extract's date and its bounds in WGS 84, from `import_meta`."""
    from psycopg import sql

    try:
        with db.connection() as conn:
            row = conn.execute(sql.SQL(
                'select extract_timestamp,'
                ' st_xmin(b), st_ymin(b), st_xmax(b), st_ymax(b)'
                ' from (select extract_timestamp, st_transform(bbox_3857, 4326) as b'
                ' from {} limit 1) m'
            ).format(sql.Identifier(schema, 'import_meta'))).fetchone()
    except Exception as exc:                  # noqa: BLE001 - any failure is "unknown"
        _log.warning('import_meta unreadable for schema %s: %s', schema, exc)
        return {}
    if row is None:
        return {}
    timestamp, *box = row
    return {
        'date': timestamp.date().isoformat() if timestamp is not None else None,
        'bounds': [round(v, 4) for v in box] if None not in box else None,
    }


def has_contours(schema: str) -> bool:
    """Whether the schema's import copied any contour lines (`table_classes`)."""
    from psycopg import sql

    try:
        with db.connection() as conn:
            row = conn.execute(sql.SQL(
                "select coalesce(table_classes->'osm_contour' <> '{{}}'::jsonb, false) from {}"
            ).format(sql.Identifier(schema, 'import_meta'))).fetchone()
    except Exception as exc:                  # noqa: BLE001 - unreadable is "none"
        _log.warning('import_meta unreadable for schema %s: %s', schema, exc)
        return False
    return bool(row and row[0])


def attribution(schema: str | None) -> str:
    """OpenStreetMap's credit, and Copernicus's where contours are drawn."""
    if schema and has_contours(schema):
        return f'{ATTRIBUTION}; {ELEVATION_ATTRIBUTION}'
    return ATTRIBUTION


def import_status(schema: str) -> dict:
    """`import_meta` for this schema.

    A schema with no `import_meta` row is not an error here: it is a server
    pointed at an area nobody has imported, which is exactly what this
    route exists to make visible.
    """
    blank = {'imported': None}
    from psycopg import sql

    try:
        with db.connection() as conn:
            # sql.Identifier, not an f-string. The schema is configuration
            # rather than request input, so this was never reachable from
            # outside -- but every other module in the tree quotes an
            # identifier this way, and one place that does not is the one
            # somebody copies.
            row = conn.execute(sql.SQL(
                'select area, source, extract_timestamp, replication_base_url,'
                ' replication_sequence, imported_at, duration_s, row_counts'
                ' from {} limit 1'
            ).format(sql.Identifier(schema, 'import_meta'))).fetchone()
    except Exception as exc:                  # noqa: BLE001 - any failure is "unknown"
        _log.warning('import_meta unreadable for schema %s: %s', schema, exc)
        return {**blank, 'error': 'import_meta unreadable'}

    if row is None:
        return blank

    (area, source, extract_timestamp, replication_base_url, replication_sequence,
     imported_at, duration_s, row_counts) = row
    return {
        'imported': {
            'area': area,
            'source': source,
            'extract_timestamp': _iso(extract_timestamp),
            'replication': {'base_url': replication_base_url,
                            'sequence': replication_sequence},
            'at': _iso(imported_at),
            'duration_s': duration_s,
            'rows': row_counts,
        },
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


@router.post('/internal/reload')
def reload(request: Request) -> dict:
    """Reload compiled styles and configuration after `manage.py compile-styles`
    or an import: the served schema, the themes, the options and the key
    records.

    Loopback only, and checked here rather than left to the proxy: this
    route changes what the server serves, and "the proxy will not forward
    it" is a configuration fact that a second deployment gets wrong.
    """
    require_loopback(request)
    return reload_all()


def reload_all() -> dict:
    """What the reload route does: also the devtools style watcher's last step."""
    config.load(refresh=True)
    # A newer complete import is picked up here.
    db.reset_active_schema()
    auth.reset()
    _cache.clear()

    from renderer import core
    from web import serving

    # The cache facades hold the pre-cache depths and the tile grids, both
    # of which the options can change, so a reload that left them built
    # would keep routing tiles to the tier the *old* configuration named.
    serving.reset()

    schema = db.active_schema()
    return {'reloaded': core.preload_all(schema), 'schema': schema}


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else None
    try:
        address = ipaddress.ip_address(host or '')
    except ValueError:
        raise HTTPException(status_code=403, detail='loopback only') from None
    if not address.is_loopback:
        raise HTTPException(status_code=403, detail='loopback only')


@router.get('/', response_class=HTMLResponse)
def landing(request: Request, lang: str | None = None) -> HTMLResponse:
    """What this server is, and a URL of each kind that works, in `?lang=`."""
    from web.main import templates

    try:
        schema = db.active_schema()
    except db.NoImportError:
        schema = None
    from renderer import core, matrix

    lang = i18n.pick(lang)
    return templates.TemplateResponse(request, 'landing.html', {
        'lang': lang,
        'languages': i18n.switch_to(lang),
        't': lambda message_id, **values: i18n.t(message_id, lang, **values),
        'version': __version__,
        'area': config.opt('serve_area'),
        'themes': [serving.url_name(name) for name in core.available_themes(schema)] if schema else [],
        'grids': matrix.load(),
        'devtools': bool(config.opt('devtools')),
    })
