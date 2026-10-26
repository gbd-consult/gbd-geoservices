"""Contour lines from a digital elevation model.

Two halves, because the heights do not change between imports and the
lines take far longer to draw than an area takes to import:

* `init()` -- `manage.py init-elevation`, run once: the GeoTIFFs named by the
  `elevation_sources` option are mosaicked, resampled to `contours.cell_m`
  in EPSG:3857, contoured, filtered and cut into pieces, into the schema
  `elevation`, which no import touches. A run builds a new table and swaps
  it in at the end, so an import running meanwhile copies the old one or the
  new one, never half of either.
* `load()` -- the import's `contours` step: the lines in the extract's bbox,
  into the new schema's osm_contour, like the water polygons
  (importer/water.py). Without `elevation.contour`, or outside it, the area
  gets none and the import goes on.

The source is Copernicus GLO-30, a *surface* model: it has the canopy and
the roofs in it. Averaging to `cell_m` damps them, and closed lines shorter
than `min_ring_m` -- a stand of trees, a building -- are dropped; what is
left at forest edges and in towns is the model's, not a bug here.

GDAL's command line tools do the raster work (gdal-bin in the image). They
reach the database as `PG:` with nothing after it: libpq takes the
connection from the environment lib.config set, so no credential is on a
command line or in a log.
"""

from __future__ import annotations

import functools
import logging
import subprocess
import time
from pathlib import Path

import yaml
from psycopg import sql

from importer import tables as t
from lib import db

log = logging.getLogger('importer')

SCHEMA = 'elevation'

#: Read here as well as by importer/params.py: the style check needs the
#: contour classes and has no Params to ask.
PARAMETERS = Path(__file__).resolve().parent.parent / 'model' / 'parameters.yaml'


def class_of(level: int) -> str:
    return f'cls_contour_{level}'


@functools.cache
def classes() -> tuple[str, ...]:
    """One class per interval of `contours.levels_m`, coarsest first. No
    classifier rule produces them: this module assigns them, as the water
    import assigns `cls_ocean`."""
    levels = yaml.safe_load(PARAMETERS.read_text())['contours']['levels_m']
    return tuple(class_of(int(m)) for m in levels)


class ElevationError(RuntimeError):
    """No source rasters, or a GDAL tool failed."""


def _run(*command: str) -> None:
    log.info('%s ...', command[0])
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ElevationError(f'{command[0]} failed: {error}') from error


def sources(data_dir: Path, patterns: list[str]) -> list[Path]:
    """The source rasters: every file the globs (relative to data_dir) match."""
    found = sorted({path for pattern in patterns for path in data_dir.glob(pattern)
                    if path.is_file()})
    if not found:
        raise ElevationError(f'no elevation rasters match {patterns} under {data_dir}')
    return found


def init(data_dir: Path, patterns: list[str], params) -> int:
    """Draw the contours of every source raster into `elevation.contour`;
    the number of rows written."""
    c = params.contours
    started = time.monotonic()
    rasters = sources(data_dir, patterns)
    work = data_dir / 'elevation'
    work.mkdir(parents=True, exist_ok=True)
    mosaic, dem = work / 'source.vrt', work / 'dem_3857.tif'
    raw, built = sql.Identifier(SCHEMA, '_contour_raw'), sql.Identifier(SCHEMA, '_contour_new')

    log.info('%d source rasters: %s', len(rasters), ', '.join(str(r) for r in rasters))
    try:
        # One mosaic, so the seam between two files is not a seam in the lines.
        _run('gdalbuildvrt', '-q', '-overwrite', str(mosaic), *map(str, rasters))
        # Projecting and averaging in one resampling: the damping of canopy
        # and roofs is the averaging.
        _run('gdalwarp', '-q', '-overwrite', '-multi', '-wo', 'NUM_THREADS=ALL_CPUS',
             '-t_srs', 'EPSG:3857', '-tr', str(c.cell_m), str(c.cell_m), '-r', 'average',
             '-ot', 'Float32', '-co', 'TILED=YES', '-co', 'COMPRESS=DEFLATE',
             '-co', 'BIGTIFF=IF_SAFER', str(mosaic), str(dem))
        with db.connection() as conn:
            conn.execute(sql.SQL('create schema if not exists {}').format(sql.Identifier(SCHEMA)))
            conn.execute(sql.SQL('drop table if exists {}').format(raw))
            conn.execute(sql.SQL('drop table if exists {}').format(built))
            conn.commit()
        _run('gdal_contour', '-q', '-i', str(c.levels_m[-1]), '-a', 'ele', '-f', 'PostgreSQL',
             '-nln', f'{SCHEMA}._contour_raw', '-lco', 'GEOMETRY_NAME=geom',
             '-lco', 'SPATIAL_INDEX=NONE', '-lco', 'FID=fid', str(dem), 'PG:')
    finally:
        mosaic.unlink(missing_ok=True)
        dem.unlink(missing_ok=True)

    with db.connection() as conn:
        count = _build(conn, raw, built, c)
        conn.execute(sql.SQL('drop table {}').format(raw))
        _swap(conn, built, rasters, c, count)
        conn.commit()
    log.info('elevation.contour: %d lines in %.0f s', count, time.monotonic() - started)
    return count


def _build(conn, raw, built, c) -> int:
    """Classify, filter, simplify and cut the raw lines into the new table,
    in the render tables' order (importer/tables.py RENDER_ORDER).

    A line's class is the first level of `levels_m` its height is a multiple
    of. gdal_contour writes the heights as exact multiples of the finest
    level, but as floats: rounding first keeps 999.9999999 a 1000 m line.

    The 0 m line is dropped. It would be a 1000 m line, drawn from z9, but
    the coast is OSM's coastline and water, drawn better, and on land it is
    the model's noise around the marshes: 46 060 of the 49 926 pieces of
    that level, 70 000 km of blobs across the north.
    """
    conn.execute(sql.SQL(
        'create table {} (class text not null, ele integer not null,'
        ' geom geometry(LineString, 3857) not null)').format(built))
    conn.execute(sql.SQL("""
        insert into {built} (class, ele, geom)
        select case {levels} else {finest} end, round(ele)::integer, piece
        from (select ele, st_subdivide(st_simplify(geom, %(simplify)s), %(vertices)s) as piece
              from {raw}
              where round(ele) <> 0
                and not (st_isclosed(geom) and st_length(geom) < %(min_ring)s)) as lines
        where geometrytype(piece) = 'LINESTRING' and st_npoints(piece) > 1
        order by {order}
    """).format(built=built, raw=raw, order=sql.SQL(t.RENDER_ORDER.replace('geom', 'piece')),
                 levels=sql.SQL(' ').join(
                     sql.SQL('when round(ele)::integer %% {} = 0 then {}').format(
                         sql.Literal(level), sql.Literal(class_of(level)))
                     for level in c.levels_m[:-1]),
                 finest=sql.Literal(class_of(c.levels_m[-1]))), {
        'simplify': c.simplify_m, 'vertices': c.subdivide_vertices, 'min_ring': c.min_ring_m,
    })
    conn.execute(sql.SQL('create index on {} using gist (geom)').format(built))
    return conn.execute(sql.SQL('select count(*) from {}').format(built)).fetchone()[0]


def _swap(conn, built, rasters: list[Path], c, count: int) -> None:
    """The new table becomes `elevation.contour` in the caller's transaction."""
    conn.execute(sql.SQL('drop table if exists {}').format(sql.Identifier(SCHEMA, 'contour')))
    conn.execute(sql.SQL('alter table {} rename to contour').format(built))
    meta = sql.Identifier(SCHEMA, 'meta')
    # Made anew each time: one row, describing the table just swapped in.
    conn.execute(sql.SQL('drop table if exists {}').format(meta))
    conn.execute(sql.SQL(
        'create table {} (written timestamptz not null, sources text[] not null,'
        ' levels_m integer[], cell_m real, min_ring_m real, lines bigint)').format(meta))
    conn.execute(sql.SQL(
        'insert into {} values (now(), %s, %s, %s, %s, %s)').format(meta),
        ([str(r) for r in rasters], list(c.levels_m), c.cell_m, c.min_ring_m, count))


def available(conn) -> bool:
    return conn.execute("select to_regclass('elevation.contour') is not null").fetchone()[0]


def load(conn, schema: str, bbox, params) -> int:
    """The contours inside `bbox` (3857) into `<schema>.osm_contour`, cut at
    its edge; the number of rows written, 0 without `elevation.contour`."""
    if not available(conn):
        log.info('no elevation.contour (manage.py init-elevation has not run): no contours')
        return 0
    zooms = sql.SQL(', ').join(
        sql.SQL('({}, {}, {})').format(sql.Literal(cls), sql.Literal(params.minzoom(cls)),
                                     sql.Literal(params.label_minzoom(cls)))
        for cls in classes())
    written = conn.execute(sql.SQL("""
        insert into {target} (osm_id, class, name, label, z_order, minzoom, minzoom_label, geom)
        select 0, c.class, null, c.ele::text, 0, z.minzoom::smallint, z.minzoom_label::smallint, part.geom
        from (select st_makeenvelope(%(xmin)s, %(ymin)s, %(xmax)s, %(ymax)s, 3857) as geom) as box
        join {source} c on c.geom && box.geom
        join (values {zooms}) as z (class, minzoom, minzoom_label) on z.class = c.class
        cross join lateral (select case when st_within(c.geom, box.geom) then c.geom
                                        else st_intersection(c.geom, box.geom) end as geom) as cut
        cross join lateral st_dump(cut.geom) as part
        where geometrytype(part.geom) = 'LINESTRING'
    """).format(target=sql.Identifier(schema, t.OSM_CONTOUR.name),
                source=sql.Identifier(SCHEMA, 'contour'), zooms=zooms),
        dict(zip(('xmin', 'ymin', 'xmax', 'ymax'), bbox))).rowcount
    conn.commit()
    return written
