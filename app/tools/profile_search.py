"""Search-performance and result-quality profile of the /search API.

Standalone: stdlib only, talks to the HTTP API and nothing else, so it runs
on the host as well as in the container. The key needs the search scope and
is sent as `Authorization: Bearer`:

    python3 app/tools/profile_search.py --base-url http://127.0.0.1:8003 --api-key <key> \\
        > profiles/search_<label>.md

Every query is sent `--repeat` times; the first request is reported as the
cold time, the median of the rest as warm. Every request nudges the ranking
point `near` (for `point`, the point itself) by a few millionths of a degree
-- a random offset per run plus 1e-7 per repeat -- so the server's response
cache, keyed on every field of the request, never answers: cold is the query
on whatever the database has cached, warm the query with warm database
caches. Each query may carry an `expect` string; the report shows at which
rank a result whose name or street contains it appears (1 = first), which is
a coarse relevance check next to the timing. `/search/count` is timed
separately for the same query. Queries live in a JSON file (`--queries`);
without one the built-in Schleswig-Holstein set is used.

Typos and fragments are sent as
phrases (`phrase_typo`, `phrase_prefix`, `phrase_partial`), which reach the
phrase mode's fuzzy step.

A "view" query filters with `bbox` and `within=false` (intersects); an "all"
query sends no spatial filter, only `near`; `point` queries use the point mode.
"""

from __future__ import annotations

import argparse
import datetime
import json
import platform
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

SH_BOX = (8.3, 53.4, 11.3, 55.0)
KIEL_BOX = (10.0, 54.25, 10.25, 54.4)

QUERIES = [
    {'id': 'city', 'mode': 'name', 'query': 'Kiel', 'expect': 'Kiel'},
    {'id': 'city_lowercase', 'mode': 'name', 'query': 'lübeck', 'expect': 'Lübeck'},
    {'id': 'landmark', 'mode': 'name', 'query': 'Holstentor', 'expect': 'Holstentor'},
    {'id': 'landmark_view', 'mode': 'name', 'query': 'Rathaus', 'bbox': KIEL_BOX, 'expect': 'Rathaus'},
    {'id': 'university', 'mode': 'name', 'query': 'Christian-Albrechts-Universität zu Kiel', 'expect': 'Christian-Albrechts'},
    {'id': 'station', 'mode': 'name', 'query': 'Hauptbahnhof', 'bbox': KIEL_BOX, 'expect': 'Hauptbahnhof'},
    {'id': 'street_name', 'mode': 'name', 'query': 'Holtenauer Straße', 'expect': 'Holtenauer Straße'},
    {'id': 'street_abbrev', 'mode': 'name', 'query': 'Holtenauer Str.', 'expect': 'Holtenauer Straße'},
    {'id': 'two_words', 'mode': 'name', 'query': 'Kieler Förde', 'expect': 'Kieler Förde'},
    {'id': 'nonsense', 'mode': 'name', 'query': 'xqzvw plorp', 'expect': None},
    {'id': 'address_full', 'mode': 'address', 'address': {'street': 'Holtenauer Straße', 'housenumber': '100', 'city': 'Kiel'}, 'expect': 'Holtenauer Straße'},
    {'id': 'address_short', 'mode': 'address', 'address': {'street': 'Breite Straße', 'housenumber': '1', 'city': 'Lübeck'}, 'expect': 'Breite Straße'},
    {'id': 'address_abbrev', 'mode': 'address', 'address': {'street': 'Holtenauer Str.', 'housenumber': '100'}, 'expect': 'Holtenauer Straße'},
    {'id': 'address_postcode', 'mode': 'address', 'address': {'street': 'Sophienblatt', 'housenumber': '25', 'postcode': '24114'}, 'expect': 'Sophienblatt'},
    {'id': 'address_many', 'mode': 'address', 'address': {'street': 'Breite Straße', 'housenumber': '1'}, 'expect': 'Breite Straße'},
    {'id': 'address_view', 'mode': 'address', 'address': {'street': 'Bahnhofstraße', 'housenumber': '1'}, 'bbox': KIEL_BOX, 'expect': 'Bahnhofstraße'},
    {'id': 'phrase_cat_place', 'mode': 'phrase', 'query': 'Restaurant Kiel', 'expect': None},
    {'id': 'phrase_cat_name', 'mode': 'phrase', 'query': 'Restaurant Maxim', 'expect': 'Maxim'},
    {'id': 'phrase_cat_street', 'mode': 'phrase', 'query': 'Bäckerei Holtenauer Straße', 'expect': 'Holtenauer'},
    {'id': 'phrase_cat_only', 'mode': 'phrase', 'query': 'Apotheke', 'bbox': KIEL_BOX, 'expect': 'Apotheke'},
    {'id': 'phrase_address', 'mode': 'phrase', 'query': 'Holtenauer Straße 100, 24105 Kiel', 'expect': 'Holtenauer Straße'},
    {'id': 'phrase_address_city_first', 'mode': 'phrase', 'query': 'Kiel Holtenauer Straße 100', 'expect': 'Holtenauer Straße'},
    {'id': 'phrase_name_place', 'mode': 'phrase', 'query': 'Universität Kiel', 'expect': 'Universität'},
    {'id': 'phrase_typo', 'mode': 'phrase', 'query': 'Lübek', 'expect': 'Lübeck'},
    {'id': 'phrase_prefix', 'mode': 'phrase', 'query': 'holsten', 'expect': 'Holsten'},
    {'id': 'phrase_partial', 'mode': 'phrase', 'query': 'flensb', 'expect': 'Flensburg'},
    {'id': 'point_kiel_hbf', 'mode': 'point', 'lon': 10.1319, 'lat': 54.3151, 'expect': None},
    {'id': 'point_luebeck', 'mode': 'point', 'lon': 10.6866, 'lat': 53.8663, 'expect': None},
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def request_body(q: dict, default_box) -> dict:
    if q['mode'] == 'point':
        return {'mode': 'point', 'near': [q['lon'], q['lat']]}
    box = tuple(q.get('bbox') or default_box)
    centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    body: dict = {'mode': q['mode'], 'page': 0, 'near': list(centre)}
    if q.get('address'):
        body.update(q['address'])
    else:
        body['text'] = q.get('query', '')
    if q.get('bbox'):
        body['bbox'] = list(box)
        body['within'] = False
    return body


def post(base_url: str, path: str, body: dict, api_key: str) -> tuple[float, int, dict | None, int]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(base_url + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    elapsed = time.perf_counter() - t
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    return elapsed, status, payload, len(raw)


def feature_label(f: dict) -> str:
    """The name, the street and number, and the city -- an address hit
    without an object has only the last two."""
    p = f.get('properties', {})
    street = p.get('address_street') or ''
    number = p.get('address_housenumber') or ''
    city = p.get('address_city') or ''
    parts = [p.get('name') or '', ' '.join(v for v in (street, number) if v), city]
    return ' | '.join(x for x in parts if x)


def expected_rank(features: list[dict], expect: str | None) -> int | None:
    if not expect:
        return None
    needle = expect.lower()
    for i, f in enumerate(features, 1):
        if needle in feature_label(f).lower():
            return i
    return 0


def run(queries: list[dict], base_url: str, api_key: str, repeat: int, default_box) -> list[dict]:
    rows = []
    nonce = random.uniform(1e-6, 9e-6)
    for q in queries:
        times = []
        payload = None
        status = 0
        size = 0
        body = request_body(q, default_box)
        for i in range(repeat):
            attempt = dict(body, near=[body['near'][0], body['near'][1] + nonce + i * 1e-7])
            elapsed, status, payload, size = post(base_url, '/search', attempt, api_key)
            times.append(elapsed * 1000)
        count_ms, _, count_payload, _ = post(base_url, '/search/count', body, api_key)
        features = ((payload or {}).get('results') or {}).get('features', []) \
            if isinstance(payload, dict) else []
        total = (payload or {}).get('total') if isinstance(payload, dict) else None
        row = dict(
            id=q['id'], mode=q['mode'],
            query=q.get('query') or ' '.join((q.get('address') or {}).values()) or f"{q['lon']},{q['lat']}",
            bbox='view' if q.get('bbox') else ('point' if q['mode'] == 'point' else 'all'),
            status=status, cold_ms=times[0], warm_ms=statistics.median(times[1:]) if len(times) > 1 else times[0],
            count_ms=count_ms * 1000, total=total,
            page=len(features), size=size, top=[feature_label(f) for f in features[:3]],
            expect=q.get('expect'), rank=expected_rank(features, q.get('expect')),
            count_total=(count_payload or {}).get('total') if isinstance(count_payload, dict) else None,
        )
        rows.append(row)
        log(f"{q['id']:20} {q['mode']:8} {row['cold_ms']:7.0f} ms cold {row['warm_ms']:7.0f} ms warm  "
            f"status {status}  total {row['total']}  rank {row['rank']}  top: {row['top'][:1]}")
    return rows


def write_report(args, rows: list[dict]) -> None:
    out = print
    out(f'# Search profile -- {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC')
    out()
    out(f'- server {args.base_url}, {len(rows)} queries, {args.repeat} requests each')
    out(f'- client {platform.system().lower()} {platform.machine()}' + (f' ({args.hardware_note})' if args.hardware_note else ''))
    out(f'- default box (lon/lat): {args.bbox[0]} {args.bbox[1]} -- {args.bbox[2]} {args.bbox[3]}; '
        f'"view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode')
    out()
    out('`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. '
        '`rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, '
        '- = nothing expected). `total` is the server\'s total for the query.')
    out()
    for mode in ('name', 'address', 'phrase', 'point'):
        sel = [r for r in rows if r['mode'] == mode]
        if not sel:
            continue
        out(f'## {mode}')
        out()
        out('| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |')
        out('|---|---|---|---|---|---|---|---|---|---|')
        for r in sel:
            rank = '-' if r['rank'] is None else str(r['rank'])
            top = r['top'][0] if r['top'] else ''
            out(f"| {r['id']} | {r['query']} | {r['bbox']} | {r['status']} | {r['cold_ms']:.0f} | {r['warm_ms']:.0f} | "
                f"{r['count_ms']:.0f} | {r['total'] if r['total'] is not None else '-'} | {rank} | {top} |")
        out()
    warm = [r['warm_ms'] for r in rows if r['status'] == 200]
    ranked = [r for r in rows if r['expect']]
    hits = sum(1 for r in ranked if r['rank'] == 1)
    found = sum(1 for r in ranked if r['rank'])
    out('## Summary')
    out()
    out(f'- warm ms over all successful queries: min {min(warm):.0f} / median {statistics.median(warm):.0f} / max {max(warm):.0f}')
    out(f'- expected result at rank 1: {hits} of {len(ranked)}; on the first page: {found} of {len(ranked)}')
    out()
    out('<details><summary>Top 3 per query</summary>')
    out()
    for r in rows:
        out(f"- **{r['id']}** ({r['query']}): " + ' ; '.join(r['top']) if r['top'] else f"- **{r['id']}** ({r['query']}): no results")
    out()
    out('</details>')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--api-key', required=True)
    parser.add_argument('--queries', help='JSON list of {id, mode, query|address|lon+lat, bbox?, expect?}; default: built-in set')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--bbox', default=','.join(map(str, SH_BOX)), help='default box, lon/lat; its centre is `near`')
    parser.add_argument('--hardware-note', default='')
    parser.add_argument('--json', help='also dump raw results to this file')
    args = parser.parse_args()
    args.bbox = tuple(float(v) for v in args.bbox.split(','))
    queries = json.load(open(args.queries)) if args.queries else QUERIES

    rows = run(queries, args.base_url, args.api_key, args.repeat, args.bbox)
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
    write_report(args, rows)


if __name__ == '__main__':
    main()
