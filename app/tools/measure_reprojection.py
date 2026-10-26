"""What reprojecting a tile actually costs: the same ground, twice.

    docker compose -f docker-compose.local.yml exec app \\
        python tools/measure_reprojection.py --schema de_sh > profiles/reprojection_de_sh.md

`profile_render.py` cannot measure what reprojecting costs (DESIGN.md
"Database" has the result): comparing its two grids compares tiles of
different *size*. The profiler pairs a UTM level with a Web Mercator zoom by
nominal scale denominator, which is in Web Mercator units -- metres only at
the equator. At 54 N a z14 tile's ground scale is
about 20 000, and the level it is paired with is about 43 600, so the "UTM
z14" tile covers ~4.7x the ground and draws ~4.7x the data.

This holds everything but the projection fixed. For each sample point and
DE_EPSG_25832_ADV level it takes the UTM tile, transforms its bbox into EPSG:3857 and
renders **the same ground at the same 256 px** twice: natively (Map srs
3857, the Web Mercator XML) and reprojected (Map srs 25832, the DE_EPSG_25832_ADV XML
-- which is what `/wmts/.../DE_EPSG_25832_ADV/...` renders). Same tables, same rows,
same styles; the difference is Mapnik reprojecting every vertex and label.

Sample points are the centres of real search objects, seeded, so the tiles
have content -- the cost of reprojecting an empty tile is nothing and says
nothing. Each pair is warmed once, then timed alternately, median of
`--repeats`.

Run in the app container: it uses the renderer's own backend, so it times
exactly the call a tile request makes.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from pathlib import Path

from lib import config, db
from renderer import core, matrix

UTM = 'EPSG:25832'
WEB_MERCATOR = 'EPSG:3857'
#: Web Mercator units per pixel at zoom 0.
Z0_RESOLUTION = 156_543.033_928_041


def sample_points(schema: str, count: int, seed: int) -> list[tuple[float, float, float]]:
    """(x, y) in EPSG:25832 and the latitude, for `count` real objects."""
    with db.connection(autocommit=True) as conn:
        conn.execute('select setseed(%s)', (seed / 1000.0,))
        rows = conn.execute(
            f'select ST_X(p), ST_Y(p), lat from ('
            f' select ST_Transform(geom_center, 25832) as p, ST_Y(geom_center) as lat'
            f' from "{schema}".osm_search_object order by random() limit %s) t',
            (count,)).fetchall()
    return [(x, y, lat) for x, y, lat in rows]


def to_web_mercator(bbox, mapnik):
    """The 3857 envelope of a 25832 bbox, and how much larger it is.

    UTM zone 32 is centred on 9 E and Schleswig-Holstein runs 8.3-11.3 E,
    so the grid is rotated against Web Mercator by at most ~1.7 degrees and
    the envelope of the rotated square is a few percent larger than the
    square. The ratio is reported so a reader can see it is small.
    """
    transform = mapnik.ProjTransform(mapnik.Projection('epsg:25832'),
                                     mapnik.Projection('epsg:3857'))
    box = transform.forward(mapnik.Box2d(*bbox))
    return (box.minx, box.miny, box.maxx, box.maxy)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--schema', default=None,
                        help='an area (its active schema) or a schema; defaults to serve_area')
    parser.add_argument('--theme', default='default_std')
    parser.add_argument('--levels', default='7,8,9,10,11,12,13')
    parser.add_argument('--points', type=int, default=24)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)

    import mapnik

    schema = db.schema_for(args.schema)
    sets = matrix.load()
    utm, mercator = matrix.by_crs(sets, UTM), matrix.by_crs(sets, WEB_MERCATOR)
    backend = core.RealMapnikBackend()
    buffer = int(config.opt('buffer_px', 64))

    def load(identifier):
        path = core.xml_path_for(args.theme, schema, identifier)
        return backend.load_map(Path(path), 256, 256, buffer)

    native_map, reprojected_map = load(mercator.identifier), load(utm.identifier)

    def timed(handle, bbox, crs):
        started = time.perf_counter()
        data = backend.render(handle, bbox, 'png', crs.lower())
        return (time.perf_counter() - started) * 1000, len(data)

    points = sample_points(schema, args.points, args.seed)
    levels = [int(level) for level in args.levels.split(',')]
    print(f'# Reprojection cost on `{schema}`: the same ground, native and reprojected\n')
    print(f'`tools/measure_reprojection.py --schema {schema} --theme {args.theme} '
          f'--points {args.points} --repeats {args.repeats} --seed {args.seed}`, '
          f'{time.strftime("%Y-%m-%d %H:%M")}.\n')
    print('Each row: the DE_EPSG_25832_ADV tile at that level around each sample point, and '
          'the same ground rendered natively in EPSG:3857 at the same 256 px. '
          'Medians over points of the per-point median of the repeats.\n')
    print('| UTM level | ground m/px | ~3857 zoom at the point | native ms | '
          'reprojected ms | added | per-tile added, p10 / median / p90 | envelope area |')
    print('|---|---|---|---|---|---|---|---|')

    details = []
    for level in levels:
        natives, reprojecteds, ratios, areas, zooms = [], [], [], [], []
        for x, y, lat in points:
            col, row = utm.tile_for(level, x, y)
            try:
                utm_bbox = utm.bbox(level, col, row)
            except ValueError:
                continue
            web_bbox = to_web_mercator(utm_bbox, mapnik)
            span_utm = utm_bbox[2] - utm_bbox[0]
            # Ground metres in the 3857 envelope, to compare areas.
            ground = [(web_bbox[2] - web_bbox[0]) * math.cos(math.radians(lat)),
                      (web_bbox[3] - web_bbox[1]) * math.cos(math.radians(lat))]
            areas.append(ground[0] * ground[1] / span_utm**2)
            zooms.append(math.log2(Z0_RESOLUTION / ((web_bbox[2] - web_bbox[0]) / 256)))

            timed(native_map, web_bbox, WEB_MERCATOR)          # warm both
            timed(reprojected_map, utm_bbox, UTM)
            n_times, r_times = [], []
            for _ in range(args.repeats):
                n_times.append(timed(native_map, web_bbox, WEB_MERCATOR)[0])
                r_times.append(timed(reprojected_map, utm_bbox, UTM)[0])
            native, reprojected = statistics.median(n_times), statistics.median(r_times)
            natives.append(native)
            reprojecteds.append(reprojected)
            ratios.append(reprojected / native)
            details.append((level, lat, native, reprojected))
            print(f'level {level} lat {lat:.2f}: native {native:6.1f} ms  '
                  f'reprojected {reprojected:6.1f} ms', file=sys.stderr)
        if not natives:
            continue
        deciles = statistics.quantiles(ratios, n=10)
        native_m, reproj_m = statistics.median(natives), statistics.median(reprojecteds)
        print(f'| {level} | {utm.resolution(level):.2f} | {statistics.median(zooms):.1f} | '
              f'{native_m:.1f} | {reproj_m:.1f} | '
              f'**{(reproj_m / native_m - 1) * 100:+.0f} %** | '
              f'{(deciles[0] - 1) * 100:+.0f} / {(statistics.median(ratios) - 1) * 100:+.0f} / '
              f'{(deciles[-1] - 1) * 100:+.0f} % | {statistics.median(areas):.3f}x |')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
