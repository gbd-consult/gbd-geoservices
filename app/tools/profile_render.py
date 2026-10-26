"""Render-performance profile of the raster tile path.

Standalone: stdlib, `mapnik` and `psycopg2`, no imports from the
application. Talks only to the XYZ/WMTS HTTP routes, the compiled Mapnik XML
of one grid (`/data/styles/<schema>/<grid>`), Postgres and the area's tile
cache (`/data/cache/<area>`). Run inside the app container against the
running server, once per grid: `--styles-dir` is that grid's directory and
`--crs` its CRS. The compiled XML carries no connection parameters, so
Mapnik and psycopg2 connect through libpq's environment, which has to be set
for this process:

    docker compose -f docker-compose.local.yml exec -T \\
        -e PGHOST=postgres -e PGDATABASE=geoservices -e PGUSER=geoservices -e PGPASSWORD=geoservices \\
        app python tools/profile_render.py \\
        --styles-dir /data/styles/<schema>/GoogleMapsCompatible --cache-dir /data/cache/de_sh \\
        --crs EPSG:3857 --bbox 8.3,53.4,11.3,55.0 --api-key <tiles key> \\
        > profiles/render_<label>.md

The server must not run with `nocache`, or stage 1's second fetch is a
render too. The dev stack's config.local turns it on; start the app with
the cache for the run, and without the variable afterwards:

    GEOSERVICES_NOCACHE=false docker compose -f docker-compose.local.yml up -d app

`--quick` runs a representative subset in about two minutes.

Tiles are picked pseudo-randomly in the box, and a pick is kept only if the
tile holds a building: open sea and empty land render in milliseconds and
would pull every median down, and a map is looked at where people are.

Stage 1 empties the cache, then fetches that fixed set of tiles
per theme and zoom over HTTP (XYZ for EPSG:3857, WMTS GetTile for the
others, with `?key=`; first fetch = render, second = cache hit). Stage 2
loads one theme's XML with Mapnik, renders one of those tiles per zoom with
a single Mapnik layer active at a time -- only the layers Mapnik queries at
that scale -- rebuilds that layer's query the way
Mapnik does and runs it through EXPLAIN ANALYZE. Results go to stdout as
Markdown, progress to stderr.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import platform
import random
import re
import shutil
import statistics
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2

DEFAULT_ZOOMS = [8, 10, 12, 13, 14, 16, 18]
DEFAULT_LAYER_ZOOMS = [8, 10, 12, 14, 16]
WEB_MERCATOR_ORIGIN = 20037508.342789244
WEB_MERCATOR_SCALE0 = 559082264.0287178
PIXEL_SIZE_M = 0.00028
TILE_SIZE = 256
DEFAULT_PER_ZOOM = 5
MAX_PICKS_PER_ZOOM = 10000
OWS = '{http://www.opengis.net/ows/1.1}'
WMTS = '{http://www.opengis.net/wmts/1.0}'


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class TileMatrixSet:
    def __init__(self, identifier: str, crs: str, top_left: tuple[float, float],
                 scales: dict[str, float]) -> None:
        self.identifier = identifier
        self.crs = crs
        self.top_left = top_left
        self.scales = scales

    def level_for_zoom(self, zoom: int) -> str:
        target = WEB_MERCATOR_SCALE0 / 2**zoom
        return min(self.scales, key=lambda k: abs(math.log(self.scales[k] / target)))

    def tile_span(self, level: str) -> float:
        return TILE_SIZE * self.scales[level] * PIXEL_SIZE_M

    def tile_for(self, x: float, y: float, level: str) -> tuple[int, int]:
        span = self.tile_span(level)
        return int((x - self.top_left[0]) // span), int((self.top_left[1] - y) // span)

    def bbox(self, level: str, col: int, row: int) -> tuple[float, float, float, float]:
        span = self.tile_span(level)
        minx = self.top_left[0] + col * span
        maxy = self.top_left[1] - row * span
        return minx, maxy - span, minx + span, maxy


def fetch_capabilities(base_url: str, api_key: str = '') -> dict[str, TileMatrixSet]:
    url = f'{base_url}/wmts?SERVICE=WMTS&REQUEST=GetCapabilities' + (f'&key={api_key}' if api_key else '')
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    sets = {}
    for tms in root.iter(f'{WMTS}TileMatrixSet'):
        if tms.find(f'{OWS}Identifier') is None:
            continue
        identifier = tms.find(f'{OWS}Identifier').text
        crs = tms.find(f'{OWS}SupportedCRS').text
        crs = 'EPSG:' + crs.rsplit(':', 1)[-1]
        scales = {}
        top_left = None
        for tm in tms.findall(f'{WMTS}TileMatrix'):
            scales[tm.find(f'{OWS}Identifier').text] = float(tm.find(f'{WMTS}ScaleDenominator').text)
            if top_left is None:
                top_left = tuple(float(v) for v in tm.find(f'{WMTS}TopLeftCorner').text.split())
        sets[crs] = TileMatrixSet(identifier, crs, top_left, scales)
    return sets


def lonlat_to_xyz(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return min(x, n - 1), min(y, n - 1)


def xyz_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    span = 2 * WEB_MERCATOR_ORIGIN / 2**z
    minx = -WEB_MERCATOR_ORIGIN + x * span
    maxy = WEB_MERCATOR_ORIGIN - y * span
    return minx, maxy - span, minx + span, maxy


def themes_in(styles_dir: Path) -> list[str]:
    return sorted(p.stem for p in styles_dir.glob('*.xml'))


def datasource_tables(xml_path: Path) -> list[tuple[str, str, str]]:
    root = ET.parse(xml_path).getroot()
    found = []
    for layer in root.findall('Layer'):
        params = {p.get('name'): (p.text or '') for p in layer.find('Datasource').findall('Parameter')}
        for table in re.findall(r'\bFROM\s+([A-Za-z_][\w.]*)', params.get('table', ''), re.IGNORECASE):
            found.append((table, params['geometry_field'], params['srid']))
    return found


def data_extent(conn, tables: list[tuple[str, str, str]]) -> tuple[float, float, float, float]:
    with conn.cursor() as cur:
        smallest = None
        for table, geometry, srid in dict.fromkeys(tables):
            cur.execute('SELECT pg_total_relation_size(%s)', (table,))
            size = cur.fetchone()[0]
            if smallest is None or size < smallest[0]:
                smallest = (size, table, geometry, srid)
        _, table, geometry, srid = smallest
        log(f'extent from {table}')
        cur.execute(
            f'SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) FROM '
            f'(SELECT ST_Transform(ST_SetSRID(ST_Extent("{geometry}"), {srid}), 4326) AS e '
            f'FROM {table}) s'
        )
        return cur.fetchone()


def inner_box(extent: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minlon, minlat, maxlon, maxlat = extent
    dlon = (maxlon - minlon) / 4
    dlat = (maxlat - minlat) / 4
    return minlon + dlon, minlat + dlat, maxlon - dlon, maxlat - dlat


def building_check(conn, tables: list[tuple[str, str, str]]):
    found = [t for t in tables if t[0].rsplit('.', 1)[-1] == 'osm_building']
    if not found:
        raise SystemExit('no osm_building table in the layer XML')
    table, geometry, srid = found[0]

    def occupied(z: int, x: int, y: int) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT EXISTS (SELECT 1 FROM {table} WHERE "{geometry}" && '
                f'ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 3857), {srid}))',
                xyz_bbox(z, x, y),
            )
            return cur.fetchone()[0]

    return occupied


def pick_points(box, zooms: list[int], per_zoom: int, seed: int, occupied) -> dict[int, list[tuple[float, float]]]:
    rng = random.Random(seed)
    minlon, minlat, maxlon, maxlat = box
    out: dict[int, list[tuple[float, float]]] = {}
    for z in zooms:
        picked: list[tuple[float, float]] = []
        seen: set[tuple[int, int]] = set()
        for _ in range(MAX_PICKS_PER_ZOOM):
            if len(picked) == per_zoom:
                break
            lon, lat = rng.uniform(minlon, maxlon), rng.uniform(minlat, maxlat)
            t = lonlat_to_xyz(lon, lat, z)
            if t in seen:
                continue
            seen.add(t)
            if occupied(z, *t):
                picked.append((lon, lat))
        if len(picked) < per_zoom:
            raise SystemExit(f'z{z}: only {len(picked)} of {per_zoom} tiles with buildings found in {box}')
        out[z] = picked
    return out


class Projector:
    def __init__(self) -> None:
        import mapnik

        self._mapnik = mapnik
        self._wgs = mapnik.Projection('epsg:4326')
        self._cache: dict[str, object] = {}

    def to_crs(self, crs: str, lon: float, lat: float) -> tuple[float, float]:
        if crs not in self._cache:
            self._cache[crs] = self._mapnik.ProjTransform(
                self._wgs, self._mapnik.Projection(crs.lower())
            )
        c = self._cache[crs].forward(self._mapnik.Coord(lon, lat))
        return c.x, c.y


def tile_address(crs: str, tms: TileMatrixSet, projector: Projector, lon: float, lat: float, zoom: int):
    if crs == 'EPSG:3857':
        x, y = lonlat_to_xyz(lon, lat, zoom)
        return str(zoom), x, y
    level = tms.level_for_zoom(zoom)
    px, py = projector.to_crs(crs, lon, lat)
    col, row = tms.tile_for(px, py, level)
    return level, col, row


API_KEY = ''


def url_name(theme: str) -> str:
    """The server's `web.serving.url_name`: a theme's name in a URL."""
    palette, _, detail = theme.partition('_')
    if palette == 'default':
        return detail
    if detail == 'std':
        return palette
    return theme


def tile_url(base_url: str, theme: str, crs: str, tms: TileMatrixSet, level: str, col: int, row: int) -> str:
    if crs == 'EPSG:3857':
        return f'{base_url}/xyz/{url_name(theme)}/{level}/{col}/{row}.png' + (f'?key={API_KEY}' if API_KEY else '')
    params = dict(SERVICE='WMTS', REQUEST='GetTile', LAYER=url_name(theme), STYLE='default', FORMAT='image/png',
                  TILEMATRIXSET=tms.identifier, TILEMATRIX=level, TILEROW=row, TILECOL=col)
    if API_KEY:
        params['key'] = API_KEY
    return f'{base_url}/wmts?{urllib.parse.urlencode(params)}'


def clear_cache(cache_dir: Path) -> None:
    if not cache_dir.exists():
        return
    for child in cache_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    if any(cache_dir.iterdir()):
        raise SystemExit(f'cache not empty after clearing: {cache_dir}')
    log(f'cleared {cache_dir}')


def fetch(url: str) -> tuple[float, int]:
    t = time.perf_counter()
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    return time.perf_counter() - t, len(data)


def warm_up(base_url, themes, crss, sets, projector, box) -> None:
    lon, lat = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for crs in crss:
        for z in (8, 14):
            level, col, row = tile_address(crs, sets[crs], projector, lon, lat, z)
            render_s, _ = fetch(tile_url(base_url, themes[0], crs, sets[crs], level, col, row))
            log(f'warm-up {themes[0]} {crs} z{z} ({level}) {col}/{row}: {render_s*1000:.0f} ms (not reported)')


def stage_http(base_url, themes, crss, sets, projector, points) -> list[dict]:
    rows = []
    for theme in themes:
        for crs in crss:
            tms = sets[crs]
            seen: set[tuple[str, int, int]] = set()
            for z, coords in points.items():
                for lon, lat in coords:
                    level, col, row = tile_address(crs, tms, projector, lon, lat, z)
                    if (level, col, row) in seen:
                        log(f'{theme:14} {crs:10} z{z:2} ({level:>2}) {col}/{row}  duplicate, skipped')
                        continue
                    seen.add((level, col, row))
                    url = tile_url(base_url, theme, crs, tms, level, col, row)
                    render_s, size = fetch(url)
                    hit_s, _ = fetch(url)
                    rows.append(dict(theme=theme, crs=crs, z=z, level=level, x=col, y=row,
                                     render_ms=render_s * 1000, hit_ms=hit_s * 1000, size=size))
                    log(f'{theme:14} {crs:10} z{z:2} ({level:>2}) {col}/{row}  render {render_s*1000:8.0f} ms  '
                        f'hit {hit_s*1000:5.1f} ms  {size/1024:6.1f} KB')
    return rows


def stats(values: list[float]) -> str:
    if not values:
        return '-'
    return f'{min(values):.0f} / {statistics.median(values):.0f} / {max(values):.0f}'


def scan_summary(plan: dict) -> list[str]:
    found: list[str] = []

    def walk(node: dict) -> None:
        kind = node.get('Node Type', '')
        if kind.endswith('Scan') and kind != 'Subquery Scan':
            target = node.get('Index Name') or node.get('Relation Name') or ''
            entry = f'{kind} {target}'.strip()
            if entry not in found:
                found.append(entry)
        for child in node.get('Plans', []):
            walk(child)

    walk(plan)
    return found


def explain(conn, sql: str) -> dict:
    with conn.cursor() as cur:
        cur.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql)
        result = cur.fetchone()[0][0]
    plan = result['Plan']
    return dict(planning_ms=result.get('Planning Time', 0.0), execution_ms=result['Execution Time'],
                rows=plan['Actual Rows'], scans=scan_summary(plan), jit=bool(result.get('JIT')))


def layer_sql(layer, m, mapnik) -> str:
    params = layer.datasource.parameters()
    table = params['table']
    geometry = params['geometry_field']
    srid = params['srid']
    # The Map's buffer is 0 and each Layer carries its own, which is what
    # Mapnik widens that layer's query by.
    env = m.envelope()
    env.pad(m.scale() * (layer.buffer_size or 0))
    if layer.srs != m.srs:
        env = mapnik.ProjTransform(mapnik.Projection(m.srs), mapnik.Projection(layer.srs)).forward(env)
    envelope = f'ST_MakeEnvelope({env.minx!r},{env.miny!r},{env.maxx!r},{env.maxy!r},{srid})'
    table = table.replace('!bbox!', envelope)
    table = table.replace('!scale_denominator!', repr(m.scale_denominator()))
    columns = ''.join(f',"{f}"' for f in layer.datasource.fields())
    return (f'SELECT ST_AsBinary("{geometry}") AS geom{columns} FROM {table} '
            f'WHERE "{geometry}" && {envelope}')


def render_once(m, mapnik) -> tuple[float, float, int]:
    image = mapnik.Image(m.width, m.height)
    t = time.perf_counter()
    mapnik.render(m, image)
    render_s = time.perf_counter() - t
    t = time.perf_counter()
    # What the server sends for `png` (renderer/core.py MAPNIK_ENCODER);
    # not imported, the profiler is standalone.
    data = image.to_string('png8')
    return render_s, time.perf_counter() - t, len(data)


def queried(layer, m, sd: float) -> bool:
    """Whether Mapnik queries `layer` at scale denominator `sd`.

    The zoom ranges are on the style rules, not on the layers, and Mapnik
    skips a layer none of whose rules is active: running EXPLAIN on it would
    add queries the tile never makes.
    """
    if not (layer.minimum_scale_denominator <= sd < layer.maximum_scale_denominator):
        return False
    return any(rule.active(sd) for name in layer.styles for rule in m.find_style(name).rules)


def stage_layers(conn, xml_path: Path, crss, sets, projector, points, layer_zooms) -> list[dict]:
    import mapnik

    mapnik.register_fonts('/usr/share/fonts')
    m = mapnik.Map(TILE_SIZE, TILE_SIZE)
    mapnik.load_map(m, str(xml_path))
    base_srs = m.srs
    layers = list(m.layers)

    results = []
    for crs in crss:
        tms = sets[crs]
        m.srs = base_srs if crs == 'EPSG:3857' else mapnik.Projection(crs.lower()).params()
        for z in layer_zooms:
            lon, lat = points[z][0]
            level, col, row = tile_address(crs, tms, projector, lon, lat, z)
            bbox = xyz_bbox(z, col, row) if crs == 'EPSG:3857' else tms.bbox(level, col, row)
            m.zoom_to_box(mapnik.Box2d(*bbox))
            sd = m.scale_denominator()
            for layer in layers:
                layer.active = True
            render_once(m, mapnik)
            total_s, encode_s, size = render_once(m, mapnik)
            log(f'{crs} z{z} ({level}) {col}/{row}: render {total_s*1000:.0f} ms, encode {encode_s*1000:.1f} ms')

            per_layer = []
            for layer in layers:
                if not queried(layer, m, sd):
                    continue
                for other in layers:
                    other.active = other.name == layer.name
                layer_s, _, _ = render_once(m, mapnik)
                info = explain(conn, layer_sql(layer, m, mapnik))
                per_layer.append(dict(name=layer.name, render_ms=layer_s * 1000, **info))
                log(f'   {layer_s*1000:7.0f} ms  db {info["execution_ms"]:7.0f} ms  '
                    f'{info["rows"]:7d} rows  {layer.name}')
            for layer in layers:
                layer.active = True
            per_layer.sort(key=lambda r: -r['render_ms'])
            results.append(dict(crs=crs, z=z, level=level, x=col, y=row, total_ms=total_s * 1000,
                                encode_ms=encode_s * 1000, size=size, layers=per_layer))
    return results


def hardware() -> str:
    model = platform.processor() or platform.machine()
    mem = ''
    try:
        for line in open('/proc/cpuinfo'):
            if line.lower().startswith(('model name', 'hardware', 'cpu model')):
                model = line.split(':', 1)[1].strip()
                break
        for line in open('/proc/meminfo'):
            if line.startswith('MemTotal'):
                mem = f', {int(line.split()[1]) / 1024 / 1024:.1f} GB RAM'
                break
    except OSError:
        pass
    return f'{model} x {os.cpu_count()}{mem}, {platform.system().lower()} {platform.release()} {platform.machine()}'


def environment(conn) -> dict:
    import mapnik

    with conn.cursor() as cur:
        cur.execute('SELECT version()')
        pg_version = cur.fetchone()[0].split(' on ')[0]
        cur.execute(
            "SELECT name, current_setting(name) FROM pg_settings WHERE name IN "
            "('jit', 'shared_buffers', 'work_mem', 'effective_cache_size', "
            "'max_parallel_workers_per_gather', 'random_page_cost')"
        )
        settings = dict(cur.fetchall())
    return dict(mapnik=mapnik.version_string(), postgres=pg_version, pg_settings=settings,
                hardware=hardware())


def write_report(args, env, box, sets, http_rows, layer_results) -> None:
    out = print
    out(f'# Render profile -- {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC')
    out()
    out(f'- server {args.base_url}, styles `{args.styles_dir}`, mapnik {env["mapnik"]}, {env["postgres"]}')
    out('- postgres: ' + ', '.join(f'{k}={v}' for k, v in sorted(env['pg_settings'].items())))
    note = f' ({args.hardware_note})' if args.hardware_note else ''
    out(f'- hardware: {env["hardware"]}{note}')
    origin = 'given' if args.bbox else 'inner half of the data extent'
    out(f'- tile box (lon/lat, {origin}): {box[0]:.3f} {box[1]:.3f} -- {box[2]:.3f} {box[3]:.3f}, '
        f'seed {args.seed}, {args.per_zoom} tiles with buildings per zoom')
    out(f'- themes: {", ".join(args.themes)}')
    out('- crs: ' + ', '.join(f'{crs} ({sets[crs].identifier})' for crs in args.crs))
    out()

    out('## 1. HTTP: uncached render vs cache hit')
    out()
    out('Render ms are min / median / max over all themes and tiles at that zoom; hit ms and KB are '
        'medians. For a non-3857 CRS "zoom" is the 3857 zoom the tile was picked for; the level actually '
        'requested is the closest scale of that TileMatrixSet (in parentheses), and two picks that land '
        'in the same coarse tile are fetched once. The first render after a cache clear is consistently '
        'slow, so unreported warm-up tiles per CRS are fetched first.')
    out()
    for crs in args.crs:
        out(f'### {crs}')
        out()
        out('| zoom | level | tiles | render ms | hit ms | KB |')
        out('|---|---|---|---|---|---|')
        for z in args.zooms:
            rows = [r for r in http_rows if r['z'] == z and r['crs'] == crs]
            if not rows:
                continue
            out(f'| {z} | {rows[0]["level"]} | {len(rows)} | {stats([r["render_ms"] for r in rows])} | '
                f'{statistics.median(r["hit_ms"] for r in rows):.1f} | '
                f'{statistics.median(r["size"] for r in rows)/1024:.0f} |')
        out()
    out('| theme | crs | tiles | render ms | z<=12 render ms | z>12 render ms |')
    out('|---|---|---|---|---|---|')
    for theme in args.themes:
        for crs in args.crs:
            rows = [r for r in http_rows if r['theme'] == theme and r['crs'] == crs]
            low = [r['render_ms'] for r in rows if r['z'] <= 12]
            high = [r['render_ms'] for r in rows if r['z'] > 12]
            out(f'| {theme} | {crs} | {len(rows)} | {stats([r["render_ms"] for r in rows])} | '
                f'{stats(low)} | {stats(high)} |')
    out()
    total_s = sum(r['render_ms'] for r in http_rows) / 1000
    out(f'Total render time for the {len(http_rows)} tiles: {total_s:.1f} s.')
    out()
    out('<details><summary>Every tile</summary>')
    out()
    out('| theme | crs | zoom | level | col | row | render ms | hit ms | KB |')
    out('|---|---|---|---|---|---|---|---|---|')
    for r in http_rows:
        out(f'| {r["theme"]} | {r["crs"]} | {r["z"]} | {r["level"]} | {r["x"]} | {r["y"]} | '
            f'{r["render_ms"]:.0f} | {r["hit_ms"]:.1f} | {r["size"]/1024:.1f} |')
    out()
    out('</details>')
    out()

    out(f'## 2. Per layer, theme `{args.layer_theme}`, in-process')
    out()
    out('One tile per zoom and CRS, rendered with a single Mapnik layer active at a time; layers Mapnik '
        'does not query at that scale are left out. '
        '`render` is the wall time of that render (query + draw); `db` is planning + execution of the '
        'same query under EXPLAIN ANALYZE; `rows` is what the query returns; `scans` are the plan\'s '
        'scan nodes. Layers sorted by render time.')
    out()
    for result in layer_results:
        db_total = sum(r['planning_ms'] + r['execution_ms'] for r in result['layers'])
        out(f'### {result["crs"]} z{result["z"]} ({result["level"]}) {result["x"]}/{result["y"]}: '
            f'render {result["total_ms"]:.0f} ms, encode {result["encode_ms"]:.1f} ms, '
            f'{result["size"]/1024:.0f} KB, {len(result["layers"])} layers, db sum {db_total:.0f} ms')
        out()
        out('| layer | render ms | db ms | rows | scans |')
        out('|---|---|---|---|---|')
        for r in result['layers']:
            jit = ' (jit)' if r['jit'] else ''
            out(f'| {r["name"]} | {r["render_ms"]:.0f} | {r["planning_ms"] + r["execution_ms"]:.0f}{jit} | '
                f'{r["rows"]} | {"; ".join(r["scans"])} |')
        out()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--styles-dir', required=True, type=Path, help='compiled Mapnik XML directory')
    parser.add_argument('--cache-dir', required=True, type=Path, help='tile cache root; emptied before the run')
    parser.add_argument('--dsn', default='', help='libpq connection string; default: libpq\'s environment')
    parser.add_argument('--crs', default='EPSG:3857',
                        help='the CRS of the grid --styles-dir was compiled for; must be a WMTS TileMatrixSet')
    parser.add_argument('--api-key', default='',
                        help='a key with the tiles scope, sent as ?key= on every tile and capabilities request')
    parser.add_argument('--bbox', default=None,
                        help='lon/lat box to pick tiles from, "minlon,minlat,maxlon,maxlat"; default: the inner '
                             'half of the extent of the smallest datasource table in the XML')
    parser.add_argument('--themes', default='', help='comma-separated; default: every XML in --styles-dir')
    parser.add_argument('--zooms', default=None, help=f'default {",".join(map(str, DEFAULT_ZOOMS))}')
    parser.add_argument('--per-zoom', type=int, default=None, help=f'default {DEFAULT_PER_ZOOM}')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--layer-theme', default='', help='default: `default_std`, else the first XML in --styles-dir')
    parser.add_argument('--layer-zooms', default=None, help=f'default {",".join(map(str, DEFAULT_LAYER_ZOOMS))}')
    parser.add_argument('--hardware-note', default='', help='free text about the host, e.g. the machine a VM runs on')
    parser.add_argument('--quick', action='store_true',
                        help='representative subset: theme default_std, zooms 8/12/14/16, one tile per zoom, '
                             'layer stage at 8/12/14; explicit --themes/--zooms/--per-zoom/--layer-zooms still win')
    parser.add_argument('--skip-http', action='store_true')
    parser.add_argument('--skip-layers', action='store_true')
    parser.add_argument('--json', help='also dump raw results to this file')
    args = parser.parse_args()

    if args.quick:
        args.themes = args.themes or 'default_std'
        args.zooms = args.zooms or '8,12,14,16'
        args.per_zoom = args.per_zoom or 1
        args.layer_zooms = args.layer_zooms or '8,12,14'
    args.themes = args.themes.split(',') if args.themes else themes_in(args.styles_dir)
    args.crs = [args.crs]
    args.zooms = [int(z) for z in (args.zooms or ','.join(map(str, DEFAULT_ZOOMS))).split(',')]
    args.per_zoom = args.per_zoom or DEFAULT_PER_ZOOM
    available = themes_in(args.styles_dir)
    args.layer_theme = args.layer_theme or ('default_std' if 'default_std' in available else available[0])
    layer_zooms = [int(z) for z in (args.layer_zooms or ','.join(map(str, DEFAULT_LAYER_ZOOMS))).split(',')]

    global API_KEY
    API_KEY = args.api_key
    sets = fetch_capabilities(args.base_url, args.api_key)
    missing = [crs for crs in args.crs if crs not in sets]
    if missing:
        raise SystemExit(f'no TileMatrixSet for {missing}; server offers {sorted(sets)}')

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = True
    env = environment(conn)
    layer_xml = args.styles_dir / f'{args.layer_theme}.xml'
    tables = datasource_tables(layer_xml)
    if args.bbox:
        box = tuple(float(v) for v in args.bbox.split(','))
    else:
        box = inner_box(data_extent(conn, tables))
    points = pick_points(box, sorted(set(args.zooms) | set(layer_zooms)), args.per_zoom, args.seed,
                         building_check(conn, tables))
    projector = Projector()

    http_rows = []
    if not args.skip_http:
        clear_cache(args.cache_dir)
        warm_up(args.base_url, args.themes, args.crs, sets, projector, box)
        clear_cache(args.cache_dir)
        http_rows = stage_http(args.base_url, args.themes, args.crs, sets, projector,
                               {z: points[z] for z in args.zooms})

    layer_results = []
    if not args.skip_layers:
        layer_results = stage_layers(conn, layer_xml, args.crs, sets, projector, points, layer_zooms)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(dict(env=env, http=http_rows, layers=layer_results), f, indent=1)

    write_report(args, env, box, sets, http_rows, layer_results)


if __name__ == '__main__':
    main()
