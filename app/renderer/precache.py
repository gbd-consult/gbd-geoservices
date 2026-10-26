"""Seed the pre-cache tier: every configured set and theme, offline.

The z0-12 pre-cache is what the band tables exist to make affordable:
without them a low-zoom tile costs hundreds of milliseconds of database
time, and with them seeding the tier is a few minutes of offline work
instead of a permanent per-request cost.

For a non-3857 set this is also where the reprojection is paid, once
(DESIGN.md "Cache and pre-cache").

Threads, not processes: Mapnik releases the GIL while rendering, and the
MapRegistry pool already bounds how many tiles of one theme can render at
once. A thread per pool slot keeps every preloaded Map object busy without
loading the XML again in a second process.
"""

from __future__ import annotations

import itertools
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from renderer import cache as cache_module
from renderer import core, matrix

log = logging.getLogger('renderer')

_EPSG = re.compile(r'\AEPSG:(\d+)\Z', re.IGNORECASE)

BBox = tuple[float, float, float, float]


def srid_of(crs: str) -> int:
    match = _EPSG.match(crs.strip())
    if not match:
        raise ValueError(f'not an EPSG code: {crs!r}')
    return int(match.group(1))


@dataclass
class Result:
    rendered: int = 0
    cached: int = 0            # already present, left alone
    failed: int = 0
    seconds: float = 0.0
    per_level: dict[int, int] = field(default_factory=dict)

    @property
    def tiles(self) -> int:
        return self.rendered + self.cached + self.failed


def extent_for(conn, schema: str, crs: str) -> BBox:
    """The imported area's extent, in `crs`.

    From `import_meta`, which the importer fills from the pbf header --
    not `ST_Extent` over a table, whose extent is inflated by maritime
    boundaries and would have the pre-cache spend most of its time on open
    sea.
    """
    from psycopg import sql

    row = conn.execute(sql.SQL("""
        select st_xmin(g), st_ymin(g), st_xmax(g), st_ymax(g)
        from (select st_transform(bbox_3857, %(srid)s) g from {}) x
    """).format(sql.Identifier(schema, 'import_meta')),
        {'srid': srid_of(crs)}).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(
            f'{schema}.import_meta has no bbox; the import did not finish')
    return (row[0], row[1], row[2], row[3])


def plan(tms: matrix.TileMatrixSet, bbox: BBox, max_level: int):
    """Every (level, col, row) to seed, coarsest first.

    Coarsest first so an interrupted run leaves a usable map: the low
    zooms are the ones a client reaches for first and the ones that are
    expensive to render on demand.
    """
    for level in range(0, min(max_level, tms.levels - 1) + 1):
        for col, row in tms.tiles_in(level, bbox):
            yield level, col, row


def fast_depth(tms: matrix.TileMatrixSet, bbox: BBox, max_tiles: int) -> int:
    """The deepest level before the first one with more than `max_tiles`
    tiles over `bbox`; -1 when level 0 has more."""
    level = -1
    while level + 1 < tms.levels:
        tiles = itertools.islice(tms.tiles_in(level + 1, bbox), max_tiles + 1)
        if sum(1 for _ in tiles) > max_tiles:
            break
        level += 1
    return level


def seed(registry, tiers, tms: matrix.TileMatrixSet, theme: str, bbox: BBox,
         max_level: int, *, fmt: str = 'png', workers: int = 4,
         force: bool = False) -> Result:
    """Render and store every tile of one theme in one set."""
    result = Result()
    started = time.monotonic()
    work = list(plan(tms, bbox, max_level))

    def one(task) -> str:
        level, col, row = task
        if not force and tiers.get(theme, tms.identifier, fmt, level, col, row) is not None:
            return 'cached'
        try:
            data = registry.render(theme, tms.bbox(level, col, row), fmt,
                                   tms.crs.lower(), tms.identifier)
        except Exception:
            log.warning('%s %s %s/%s/%s failed to render',
                        theme, tms.identifier, level, col, row, exc_info=True)
            return 'failed'
        tiers.set(theme, tms.identifier, fmt, level, col, row, data)
        return 'rendered'

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for task, outcome in zip(work, pool.map(one, work), strict=True):
            setattr(result, outcome, getattr(result, outcome) + 1)
            if outcome == 'rendered':
                result.per_level[task[0]] = result.per_level.get(task[0], 0) + 1

    result.seconds = time.monotonic() - started
    return result


def run(schema: str | None = None, themes=None, grid_ids=None, *, fmt: str = 'png',
        workers: int | None = None, force: bool = False, fast: bool = False) -> dict:
    """Seed every configured set and theme. What `manage.py pre-cache` calls.

    `fast` stops each set at `fast_depth` with `pre_cache_fast_max`: the
    levels that are cheap enough to seed right after an import.
    """
    from lib import config, db

    if config.opt('nocache'):
        raise RuntimeError('the nocache option is on; there is no cache to seed')
    schema = schema or db.active_schema()
    sets = matrix.load(grid_ids)
    themes = list(themes or core.available_themes(schema))
    if not themes:
        raise RuntimeError(
            f'no compiled styles for {schema!r}; run `manage.py compile-styles` first')

    pool_size = int(config.opt('map_pool_size', 4))
    workers = workers or pool_size
    buffer_px = int(config.opt('buffer_px', 64))

    tiers = cache_module.build(db.area_of(schema))
    with db.connection() as conn:
        extents = {identifier: extent_for(conn, schema, tms.crs)
                   for identifier, tms in sets.items()}

    out: dict[str, dict[str, Result]] = {}
    for identifier, tms in sets.items():
        # A registry per set, not per run: each set has its own compiled
        # XML (the scale arithmetic differs -- see renderer.styles), and
        # holding every set's pools at once would be `sets x themes x
        # pool_size` Mapnik Maps in memory for a job that visits one set
        # at a time.
        registry = core.MapRegistry(buffer_size=buffer_px, pool_size=pool_size,
                                    db_pool_size=int(config.opt('db.mapnik_pool_size', 40)))
        loaded = registry.preload(
            themes, lambda t, s_, schema=schema: core.xml_path_for(t, schema, s_),
            tms.identifier)
        if not loaded:
            raise RuntimeError(
                f'no theme loaded for {tms.identifier}; nothing can be pre-cached')

        # One answer to "how deep is this set pre-cached", shared with the
        # cache facade that has to route the same levels to the same tier.
        depth = tiers.depth_for(tms.identifier)
        if fast:
            depth = min(depth, fast_depth(tms, extents[identifier],
                                          int(config.opt('pre_cache_fast_max'))))
        for theme in loaded:
            result = seed(registry, tiers, tms, theme, extents[identifier], depth,
                          fmt=fmt, workers=workers, force=force)
            out.setdefault(tms.identifier, {})[theme] = result
            log.info('%s %s: %d tiles, %d rendered, %d already cached, %.1f s',
                     tms.identifier, theme, result.tiles, result.rendered,
                     result.cached, result.seconds)
    return out
