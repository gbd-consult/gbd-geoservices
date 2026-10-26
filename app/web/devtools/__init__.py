"""The devtools viewer: a map, the tiles this server draws, and its search.

    GET /devtools                 the page
    GET /devtools/api/grids       what the page needs to build a Leaflet CRS per grid
    GET /devtools/api/extent      where the imported data is, to open the map on it
    GET /devtools/api/watch       the style watcher's state, which the page polls
    GET /devtools/static/...      its JavaScript and CSS

Mounted only when the `devtools` option is on -- "viewer only, never on a
public deployment" -- and it is a viewer plus a style watcher, no editor:
styles are edited in the repository. The `devtools_watch` option also starts
`watcher.py`, which recompiles the styles when a file under `styles/`
changes, and has the page poll it -- a request every 1.5 s per open page,
which on a deployment is only noise in the proxy's log. There is no vector
viewer yet; it waits for the renderer's vector half.

Everything else the page shows comes from the public API it is exercising --
`/metadata`, `/status`, `/xyz`, `/wmts`, `/search*` -- so it tests the routes a
client uses rather than a private copy of them. The two endpoints here exist
only because a browser cannot derive them: a Leaflet CRS needs a proj4
definition and a resolution per level, and the initial view needs the
imported extent.

NO KEY IN THE PAGE

A key rendered into the HTML would put a production key in the source of
any page that served it. The page has a key field instead, kept in the
viewer's own browser storage.
With no keys configured the server is open and the field stays empty.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lib import config, db, i18n
from lib.version import __version__
from web.devtools import watcher

_log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / 'templates'))

router = APIRouter(prefix='/devtools', tags=['devtools'], include_in_schema=False)

#: The CRS Leaflet knows natively. Every other grid is built with
#: Proj4Leaflet from the definition PostGIS holds.
WEB_MERCATOR = 'EPSG:3857'


class _Revalidated(StaticFiles):
    """The viewer's scripts, which the browser must ask about every time.

    StaticFiles sends an ETag and Last-Modified but no Cache-Control, so a
    browser keeps a file fresh by heuristic -- and a module that `main.js`
    imports is then taken from the cache without asking: an edited
    `search.js` ran as the old one after a plain reload. `no-cache` still
    caches, it only revalidates, which the ETag answers with a 304.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-cache'
        return response


def enabled() -> bool:
    return bool(config.opt('devtools'))


def mount(app) -> None:
    """Add the viewer to `app`, if the option allows it."""
    if not enabled():
        return
    app.include_router(router)
    app.mount('/devtools/static', _Revalidated(directory=str(HERE / 'static')),
              name='devtools-static')


def watching() -> bool:
    return enabled() and bool(config.opt('devtools_watch'))


def start_watcher() -> watcher.Watcher | None:
    """Watch `styles/`, if the options allow it. The lifespan stops it."""
    if not watching():
        return None
    from importer.run import STYLES

    return watcher.Watcher(STYLES).start()


#: The choices of the page's radio groups and the sort select, as its
#: controls carry them; the first of each is what a URL without one gets.
TABS = ('tiles', 'search', 'status')
DETAILS = ('std', 'min', 'nav', 'max', 'topographic', 'vegetation')
REQUEST_MODES = ('xyz', 'wmts-rest', 'wmts-kvp')
SEARCH_MODES = ('name', 'address', 'phrase', 'here')
SORTS = ('score', 'distance', 'name', 'address')


def _choice(value: str | None, choices: tuple[str, ...]) -> str:
    return value if value in choices else choices[0]


def _theme_parts(name: str | None) -> tuple[str, str]:
    """The palette and the detail a theme's URL name stands for: the inverse
    of `serving.url_name`, which leaves out the default of either."""
    from web import serving

    if not name:
        return serving.DEFAULT_PALETTE, serving.DEFAULT_DETAIL
    if name in DETAILS:
        return serving.DEFAULT_PALETTE, name
    palette, _, detail = name.partition('_')
    return palette, detail or serving.DEFAULT_DETAIL


def _category_name(category: str | None, lang: str) -> str | None:
    from search import api as search_api

    def find(nodes):
        for node in nodes:
            if node['id'] == category:
                return node['names'].get(lang, category)
            found = find(node.get('subcategories') or [])
            if found:
                return found
        return None

    return find(search_api.categories([lang])) if category else None


def controls(params, lang: str) -> dict:
    """Every control of the page as the URL state sets it.

    The scripts apply the same state, but only once the map and the themes
    have loaded; a page rendered with the defaults showed them until then,
    on every reload and every language switch. Values the server cannot
    know -- which themes and grids are served -- are rendered as the URL
    names them and checked by the scripts.
    """
    from renderer import core, matrix
    from search.request import DEFAULT_SIMILARITY, MAX_SIMILARITY, MIN_SIMILARITY
    from web import formats

    palette, detail = _theme_parts(params.get('theme'))
    grids = matrix.load()
    request_mode = _choice(params.get('mode'), REQUEST_MODES)
    tab = _choice(params.get('tab'), TABS)
    try:
        similarity = int(params.get('sim', DEFAULT_SIMILARITY))
    except ValueError:
        similarity = DEFAULT_SIMILARITY
    return {
        'tab': tab,
        'palette': palette,
        'detail': detail if detail in DETAILS else DETAILS[0],
        'mode': request_mode,
        'grids': {identifier: tms.crs for identifier, tms in sorted(grids.items())},
        'grid': params.get('grid') if params.get('grid') in grids else core.DEFAULT_MATRIX_SET,
        # The search tab pins the map to Web Mercator (tiles.js).
        'grid_disabled': request_mode == 'xyz' or tab == 'search',
        'formats': formats.RASTER,
        'format': _choice(params.get('format'), formats.RASTER),
        'debug': params.get('debug') == '1',
        'smode': _choice(params.get('smode'), SEARCH_MODES),
        'text': {key: params.get(key, '') for key in ('q', 'street', 'hn', 'pc', 'city', 'radius')},
        'category': _category_name(params.get('cat'), lang),
        'geom': bool(params.get('geom')),
        'inview': params.get('inview') == '1',
        'within': params.get('within') != '0',
        'sort': _choice(params.get('sort'), SORTS),
        'similarity_range': (MIN_SIMILARITY, MAX_SIMILARITY),
        'default_similarity': DEFAULT_SIMILARITY,
        'similarity': (similarity if MIN_SIMILARITY <= similarity <= MAX_SIMILARITY
                       else DEFAULT_SIMILARITY),
        'fuzzy': params.get('fuzzy') == '1',
    }


@router.get('', response_class=HTMLResponse)
def page(request: Request, lang: str | None = None) -> HTMLResponse:
    from web import formats

    lang = i18n.pick(lang)
    return templates.TemplateResponse(request, 'devtools.html', {
        'lang': lang,
        'languages': i18n.switch_to(lang),
        'ui': controls(request.query_params, lang),
        't': lambda message_id, **values: i18n.t(message_id, lang, **values),
        # The scripts' texts, in the page like `formats`, so there is no
        # second copy of the catalogue to keep in step.
        'script_messages': i18n.texts('devtools.js.', lang),
        'version': __version__,
        'area': config.opt('serve_area'),
        'formats': {fmt: formats.mime_for(fmt) for fmt in formats.RASTER},
        'watch': watching(),
    })


@router.get('/api/grids')
def grids() -> dict:
    """One entry per configured TileMatrixSet, keyed by identifier.

    `resolutions` and the matrix sizes are indexed by level, which is the
    convention `L.Proj.CRS` requires. The sizes are how the page knows where
    a grid ends: a Proj4Leaflet CRS built without bounds reports itself
    infinite and would request tiles past the edge, which this server
    answers with a 404 -- correctly, but a map full of 404s is noise.

    `proj4` comes from PostGIS's `spatial_ref_sys` rather than a literal
    here, so the page projects with the same definition the database
    reprojects with.
    """
    from renderer import cache, matrix

    sets = matrix.load()
    depths = cache.precache_depths()
    definitions = _proj4(sorted({tms.crs for tms in sets.values()}))
    out = {}
    for identifier, tms in sorted(sets.items()):
        levels = range(tms.levels)
        out[identifier] = {
            'crs': tms.crs,
            'native': tms.crs == WEB_MERCATOR,
            'proj4': definitions.get(tms.crs),
            'origin': list(tms.origin),
            'resolutions': [tms.resolution(level) for level in levels],
            'matrix_widths': [tms.matrix(level).matrix_width for level in levels],
            'matrix_heights': [tms.matrix(level).matrix_height for level in levels],
            # Levels up to here come from the pre-cache; deeper ones are
            # rendered on demand. Shown in the page, because "why is this
            # zoom slow" is usually this.
            'precache_depth': depths.get(identifier),
        }
    return out


def _proj4(codes: list[str]) -> dict[str, str]:
    srids = {code: int(code.split(':', 1)[1]) for code in codes
             if code.upper().startswith('EPSG:')}
    try:
        with db.connection(autocommit=True) as conn:
            rows = conn.execute(
                'select auth_srid, proj4text from spatial_ref_sys'
                " where auth_name = 'EPSG' and auth_srid = any(%s)",
                (list(srids.values()),)).fetchall()
    except Exception as exc:                  # noqa: BLE001 - the page degrades to 3857
        _log.warning('proj4 definitions unavailable: %s', exc)
        return {}
    by_srid = {srid: text.strip() for srid, text in rows}
    return {code: by_srid[srid] for code, srid in srids.items() if srid in by_srid}


@router.get('/api/extent')
def extent() -> dict:
    """The imported area as [west, south, east, north] in EPSG:4326, or null.

    From `import_meta.bbox_3857`, which is the extract's header box -- not
    `ST_Extent` over a table, which maritime boundaries inflate.
    """
    area = config.opt('serve_area')
    try:
        schema = db.active_schema()
        with db.connection(autocommit=True) as conn:
            row = conn.execute(
                f'select ST_XMin(b), ST_YMin(b), ST_XMax(b), ST_YMax(b) from ('
                f' select ST_Transform(bbox_3857, 4326) as b'
                f' from "{schema}".import_meta) t').fetchone()
    except Exception as exc:                  # noqa: BLE001
        _log.warning('import extent unavailable for %s: %s', area, exc)
        row = None
    return {'area': area, 'bbox': list(row) if row and row[0] is not None else None}


@router.get('/api/watch')
def watch() -> dict:
    return watcher.state()
