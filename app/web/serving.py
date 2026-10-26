"""Serving one tile: cache, render, headers -- and bounding the cache.

Shared by `/xyz` and `/wmts`, which differ only in how a request becomes a
(set, level, col, row) and not at all in what happens next.

WHY THE ROUTES ARE SYNCHRONOUS

A Mapnik render is blocking C++ that holds the GIL's owner for tens of
milliseconds. A route declared `async def` runs on the event loop and would
stall every other request for that time; a route declared `def` is run by
FastAPI in a worker thread, which is what makes `map_pool_size` concurrent
renders actually concurrent. So the handlers here and in `tiles.py` are
deliberately not `async`.

BOUNDING THE ON-DEMAND TIER

`ondemand_cache_max_mb` (10 GiB by default) is enforced here, in the serve
path, which calls `cache.evict_lru()`: the renderer renders one tile and
knows nothing about the directory's total size.

The sweep is *scheduled*, not per-write. Walking the tier to total its size
costs more than the render that produced the tile, so instead this counts
the bytes it has written since the last sweep and only walks when that
exceeds `SWEEP_AFTER_FRACTION` of the limit. The count is an over-estimate
(a rewritten tile is counted twice), which is the safe direction: it sweeps
early rather than late.
"""

from __future__ import annotations

import logging
import threading

from fastapi import HTTPException, Request, Response

from lib import config, timing
from web import formats, httpcache

log = logging.getLogger(__name__)

#: Sweep once this much of the limit has been written since the last one.
#: A quarter: four sweeps per cache-full of writes, each a directory walk.
SWEEP_AFTER_FRACTION = 0.25

#: Evict down to this much of the limit, so a sweep does real work and the
#: next one is not immediately due again.
SWEEP_TARGET_FRACTION = 0.9


class Sweeper:
    """Keeps the on-demand tier under `ondemand_cache_max_mb`.

    One background thread at a time. A second request that crosses the
    threshold while a sweep is running does nothing rather than queueing:
    the running sweep will take the newer tiles into account by the time it
    stats them, and two concurrent `evict_lru` walks over the same tree
    would fight over the same files.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._written = 0
        self._running = False

    def limit_bytes(self) -> int:
        try:
            return max(0, int(config.opt('ondemand_cache_max_mb', 0))) * 1024 * 1024
        except (TypeError, ValueError):
            return 0

    def note(self, cache, tile_matrix_set: str, z: int, written: int) -> None:
        """Record a write, and sweep if enough has accumulated."""
        limit = self.limit_bytes()
        if not limit or cache.tier_for(tile_matrix_set, z) is not cache.ondemand:
            # The pre-cache tier is bounded by the pre-cache, not by this:
            # evicting a pre-cached tile would mean rendering it again on
            # demand, which is the cost the pre-cache exists to avoid.
            return
        with self._lock:
            self._written += written
            if self._running or self._written < limit * SWEEP_AFTER_FRACTION:
                return
            self._written = 0
            self._running = True
        self._start(cache.ondemand, limit)

    def _start(self, tier, limit: int) -> None:
        """Run the sweep off the request thread.

        Its own method so a test can replace *this* rather than
        `threading.Thread` -- `serving.threading` is the stdlib module, so
        patching it there replaces threads for the whole process and
        deadlocks the test client.
        """
        threading.Thread(target=self._sweep, args=(tier, limit),
                         name='cache-sweep', daemon=True).start()

    def _sweep(self, tier, limit: int) -> None:
        try:
            target = int(limit * SWEEP_TARGET_FRACTION)
            removed = tier.evict_lru(target)
            if removed:
                log.info('on-demand cache: evicted %d tiles to stay under %d MiB',
                         removed, limit // (1024 * 1024))
        except Exception as exc:              # noqa: BLE001 - a sweep must never fail a request
            log.warning('on-demand cache sweep failed: %s', exc)
        finally:
            with self._lock:
                self._running = False

    def reset(self) -> None:
        with self._lock:
            self._written = 0


sweeper = Sweeper()


def check_format(fmt: str, allowed: tuple[str, ...] = formats.RASTER) -> str:
    """The canonical short form, or 404.

    404 rather than 400: a tile address is a path, and an extension this
    service does not serve is an address that does not exist.
    """
    canonical = formats.normalize(fmt)
    if canonical not in allowed:
        raise HTTPException(status_code=404,
                            detail=f'unsupported format {fmt!r}; '
                                   f'this service serves {", ".join(allowed)}')
    return canonical


#: The palette and the detail a theme's URL name leaves out.
DEFAULT_PALETTE = 'default'
DEFAULT_DETAIL = 'std'


def url_name(theme: str) -> str:
    """A theme's name in a URL: `default_max` is `max`, `dark_std` is `dark`,
    `default_std` is `std`. One name per theme, so a tile has one URL in each
    grid; `styles.check` refuses a name that is both a palette and a detail."""
    palette, _, detail = theme.partition('_')
    if palette == DEFAULT_PALETTE:
        return detail
    if detail == DEFAULT_DETAIL:
        return palette
    return theme


def check_theme(name: str, schema: str) -> str:
    """The theme a URL name stands for, or 404."""
    from renderer import core

    themes = {url_name(theme): theme for theme in core.available_themes(schema)}
    if name not in themes:
        raise HTTPException(status_code=404, detail=f'unknown theme {name!r}')
    return themes[name]


def serve(request: Request, *, theme: str, tms, level: int, col: int, row: int,
          fmt: str, schema: str) -> Response:
    """One tile: cache, else render; then the conditional-request dance.

    The cache is consulted before the address is validated, because a hit
    proves the address was valid when it was written and a miss costs
    nothing. `bbox()` is what actually rejects a tile outside the pyramid.
    """
    from renderer import core

    steps = timing.Steps()
    cache = _cache(schema)
    with steps.step('cache'):
        data = cache.get(theme, tms.identifier, fmt, level, col, row)

    if data is None:
        try:
            bbox = tms.bbox(level, col, row)
        except ValueError as exc:
            # Outside the pyramid: a 404, not a 500 and not a render.
            raise HTTPException(status_code=404, detail=str(exc)) from None
        try:
            # `tms.identifier`, not just `tms.crs`. The CRS repoints the Map;
            # the identifier picks *which compiled XML* is repointed, and
            # they are two different facts. A theme is compiled once per
            # grid because the scale arithmetic differs between them (see
            # `renderer.styles`), so leaving the set at its default served
            # every EPSG:25832 tile from the Web Mercator file -- one zoom
            # too fine, and reading the unbanded tables where the band was
            # meant. It renders, it caches, and it is the wrong tile.
            data = core.render_tile(theme, bbox, fmt, tms.crs, tms.identifier, steps=steps)
        except Exception as exc:              # noqa: BLE001
            log.exception('render failed for %s/%s/%s/%s/%s',
                          theme, tms.identifier, level, col, row)
            raise HTTPException(status_code=500, detail='tile render failed') from exc
        with steps.step('store'):
            cache.set(theme, tms.identifier, fmt, level, col, row, data)
        sweeper.note(cache, tms.identifier, level, len(data))
    timing.report(log, steps, f'tile {theme}/{tms.identifier}/{level}/{col}/{row}.{fmt}')

    etag = httpcache.tile_etag(data)
    versioned = 'v' in request.query_params
    if httpcache.enabled() and httpcache.is_not_modified(request.headers.get('if-none-match'),
                                                         etag):
        return Response(status_code=304, headers=httpcache.headers(etag, versioned=versioned))
    return Response(content=data, media_type=formats.mime_for(fmt),
                    headers=httpcache.headers(etag, versioned=versioned))


_caches: dict[str, object] = {}


def _cache(schema: str):
    """The cache facade for a schema's area, built once.

    Built lazily and kept, because `build()` reads the options and the
    configured tile grids; doing that per tile would be the most expensive
    part of a cache hit.
    """
    if schema not in _caches:
        from lib import db
        from renderer import cache as cache_module
        _caches[schema] = cache_module.build(db.area_of(schema))
    return _caches[schema]


def reset() -> None:
    """Drop the built caches. `/internal/reload` and tests."""
    _caches.clear()
    sweeper.reset()
