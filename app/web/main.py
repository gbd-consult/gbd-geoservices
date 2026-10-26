"""The FastAPI app: lifespan, routers, CORS, and the access log.

A route only translates. `/xyz/{theme}/{z}/{x}/{y}.png` becomes
`renderer.render_tile(...)`; a `/search` body becomes `search.api.find(...)`.
`manage.py`, the devtools reload and the two profilers call the same
functions with no HTTP in between, which is what keeps the profilers honest
-- they measure the renderer and the search, not this file.

WHAT THE LIFESPAN IS FOR

The compiled styles, for the schema this process serves; then three things
that are each a first-request cost otherwise, and one warning:

- the Map-object pool. `DESIGN.md` "Map pool": a Mapnik Map
  is loaded once per theme at process start and reused, never per request.
- the model YAML. `generated/categories.yaml` is 400 KB and the search module reads it,
  `parameters.yaml` and `classes.yaml`, lazily; measured, the first search in
  a fresh process paid ~800 ms for all of them and every one after it paid
  nothing. That belongs at startup, not on whoever arrives first.
- the tile matrix sets, for the same reason.
- and a warning when no keys are configured, so an unprotected deployment
  is not silent.

None of it is fatal. A server that cannot preload still answers `/health`
and `/metadata`, and `/status` is where the reason shows up -- a container
that refuses to start because one theme's XML is missing is harder to
diagnose than one that says so.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lib import config, db
from lib.version import __version__
from web import auth, devtools, icons, legend, meta, tiles, wms, wmts
from web import search as search_routes

_log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / 'templates'))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=getattr(logging, str(config.opt('log_level', 'info')).upper(), logging.INFO),
        format='%(levelname)s %(name)s %(message)s',
    )
    auth.warn_if_open()
    _preload()
    style_watcher = devtools.start_watcher()
    yield
    if style_watcher:
        style_watcher.stop()


def _compile_styles(schema: str) -> None:
    """Compile the styles for the schema about to be served.

    At every start, so a new image, new style files or a new import are
    served without a separate step, and the XML always belongs to the
    schema this process resolved. A compile that fails -- a style check,
    a class that needs a re-import -- is logged and the XML already on disk
    is served.
    """
    from renderer import styles

    try:
        styles.run(schema)
    except Exception as exc:                  # noqa: BLE001 - serve what is there
        _log.error('could not compile the styles for %s; serving the XML on disk: %s',
                   schema, exc)


def _preload() -> None:
    try:
        from renderer import core, matrix

        matrix.load()
        schema = db.active_schema()
        _compile_styles(schema)
        loaded = core.preload_all(schema)
        total = sum(len(themes) for themes in loaded.values())
        if not total:
            # A server with no compiled styles answers every tile with a
            # 404 and looks healthy. Say so once, loudly, at startup.
            _log.warning("no compiled styles for schema %r -- run "
                         "`manage.py compile-styles %s`", schema, db.area_of(schema))
        else:
            for matrix_set, themes in sorted(loaded.items()):
                _log.info('loaded %d themes for %r in %s',
                          len(themes), schema, matrix_set)
    except Exception as exc:                  # noqa: BLE001 - startup must not die here
        _log.warning('could not preload the renderer: %s', exc)

    try:
        # The ~800 ms of YAML the first search would otherwise pay for.
        from search import place, rank, rules, shape
        from search import point as point_mode

        rank.weights()
        rules.steps()
        shape.names(str(config.opt('lang', 'de')))
        place.radii()
        point_mode.radii()
    except Exception as exc:                  # noqa: BLE001
        _log.warning('could not preload the search model: %s', exc)


async def no_import(request: Request, exc: db.NoImportError) -> JSONResponse:
    """The served area has no complete import: nothing to serve yet, which is
    not the client's fault and not a crash."""
    return JSONResponse({'detail': str(exc)}, status_code=503)


def create_app() -> FastAPI:
    app = FastAPI(
        title='gbd-geoservices',
        version=__version__,
        description='OSM tiles and search.',
        lifespan=lifespan,
    )

    origins = list(config.opt('cors_origins') or ['*'])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=['GET', 'POST', 'OPTIONS'],
        # The key header, so a browser client can send it. Without it the
        # preflight fails and the only carrier left is `?key=`, which is the
        # one that ends up in logs.
        allow_headers=['Authorization', 'Content-Type'],
        max_age=86400,
    )

    app.middleware('http')(access_log)
    app.add_exception_handler(db.NoImportError, no_import)

    app.include_router(meta.router)
    app.include_router(tiles.router)
    app.include_router(wmts.router)
    app.include_router(wms.router)
    app.include_router(search_routes.router)
    app.include_router(icons.router)
    app.include_router(legend.router)
    # Only when the `devtools` option is on; never on a public deployment.
    devtools.mount(app)

    static = HERE / 'static'
    if static.is_dir():
        app.mount('/static', StaticFiles(directory=str(static)), name='static')

    return app


#: The devtools page polls its style watcher every 1.5 s.
QUIET_PATHS = frozenset({'/devtools/api/watch'})


async def access_log(request: Request, call_next):
    """One line per request, with `key` stripped.

    The key must appear in no response body, no error, no
    `Location` header, no access-log line and no cache key. The query
    parameter carrier is the only one that can reach a log at all, and this
    is where it would -- so it is removed here rather than left to the
    proxy, which is a second place to get it wrong.
    """
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path in QUIET_PATHS:
        return response
    _log.info('%s %s %s %.1fms',
              request.method, safe_path(request), response.status_code,
              (time.perf_counter() - started) * 1000)
    return response


def safe_path(request: Request) -> str:
    """The request path with the key removed from the query string."""
    params = [(name, value) for name, value in request.query_params.multi_items()
              if name.lower() != auth.QUERY_PARAM]
    if not params:
        return request.url.path
    query = '&'.join(f'{name}={value}' for name, value in params)
    return f'{request.url.path}?{query}'


app = create_app()
