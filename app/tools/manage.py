"""Management commands.

    python tools/manage.py init-elevation [--download]
    python tools/manage.py import <area> [--no-water] [--pass-workers 1|2|3]
    python tools/manage.py compile-styles [<area>]
    python tools/manage.py pre-cache [<area>] [--fast] [--force]
    python tools/manage.py drop-cache [<area>]
    python tools/manage.py key-add <name> [--customer C] [--scopes tiles search devtools]
                                  [--referrers P ...] [--rate N] [--trial | --expires DATE]
    python tools/manage.py key-register <name> [the same options] < key
    python tools/manage.py key-list
    python tools/manage.py key-disable <name> | key-enable <name>
    python tools/manage.py usage-export <yyyy-mm>
    python tools/manage.py stats-daily
    python tools/manage.py stats-export <yyyy-mm>

One small file of argparse subcommands that call functions of the modules.
Every task with logic lives in its module -- the extract and the import in
`importer`, style generation and pre-caching in `renderer`, config layering
in `lib` -- and this file never touches the database or the filesystem
itself.

Each command is one action, so an update is a sequence of them, run on the
host through `manage.sh`:

    ./manage.sh import de_sh
    ./manage.sh reload             # the app compiles the styles for the new import

`import` writes a new schema and leaves the served one alone; the server
changes to it when it is reloaded. The tile cache is never emptied as a side
effect -- `drop-cache` does that, and `pre-cache --force` overwrites.

An <area> defaults to `serve_area`. `update`, `vector`, `search`, `db` and
`deploy` arrive with the modules they drive.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path

from importer import extract, progress, run
from renderer import cache


def cmd_import(args: argparse.Namespace) -> int:
    """Import an area into a new schema; the served one is left alone."""
    started = time.monotonic()
    # An import runs for minutes to hours: its steps and progress show
    # without -v.
    logging.getLogger('importer').setLevel(logging.INFO)
    try:
        with progress.import_run(args.area, started):
            return import_logged(args, started)
    except progress.ImportRunning as exc:
        print(exc, file=sys.stderr)
        return 1


def import_logged(args: argparse.Namespace, started: float) -> int:
    log = logging.getLogger('importer')
    log.info(f'Starting import "{args.area}"')
    try:
        path = extract.ensure(args.area)
        result = run.import_area(path, args.area, water=not args.no_water,
                                 pass_workers=args.pass_workers)
        log.info(run.summary(path, result))
    except BaseException as exc:
        # The last line of the log says how the import ended, so a log read
        # in the morning with `tail` needs nothing above it.
        log.exception(f'{type(exc).__name__}: {exc}')
        log.error(f'Import "{args.area}" ERROR after {progress.duration(time.monotonic() - started)}')
        return 1
    log.info(f'Import "{args.area}" complete in {progress.duration(time.monotonic() - started)}')
    return 0


def cmd_init_elevation(args: argparse.Namespace) -> int:
    """Draw the contour lines once, into the `elevation` schema."""
    from importer import elevation, params
    from lib import config

    logging.getLogger('importer').setLevel(logging.INFO)
    started = time.monotonic()
    data_dir = Path(config.opt('data_dir', '/data'))
    try:
        if args.download:
            fetched, absent = elevation.download(data_dir, config.opt('elevation_base'),
                                                 config.opt('elevation_tiles'))
            print(f'{fetched} tiles downloaded, {absent} absent at the source (sea)')
        lines = elevation.init(data_dir,
                               config.opt('elevation_sources') or [],
                               params.load(run.MODEL, run.STYLES))
    except elevation.ElevationError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f'{lines} contour lines in {progress.duration(time.monotonic() - started)}; '
          f'the next import of an area copies its share')
    return 0


def cmd_compile_styles(args: argparse.Namespace) -> int:
    """Write the icons and compile the style files to Mapnik XML for the area's schema."""
    from lib import db
    from renderer import styles

    schema = db.active_schema(args.area)
    written = styles.run(schema)
    for path in written:
        print(path)
    print(f'\n{len(written)} themes written for {schema}', file=sys.stderr)
    print('loading themes into the server...', file=sys.stderr)
    print(reload_server(), file=sys.stderr)
    return 0


def cmd_drop_cache(args: argparse.Namespace) -> int:
    """Empty both tile-cache tiers of an area, or with --ondemand only that one."""
    from lib import config

    area = args.area or config.opt('serve_area')
    removed = (cache.clear_area(area, tiers=('ondemand',)) if args.ondemand
               else cache.clear_area(area))
    print(f'{removed} cached tiles of {area} removed', file=sys.stderr)
    return 0


def cmd_key_add(args: argparse.Namespace) -> int:
    """Generate a key as a Vaultwarden Send, register it, print only the link.

    The Send is made first, so a refused registration -- a name taken, an
    unknown scope -- leaves a link to a key that opens nothing.
    """
    import subprocess

    from lib import keys

    try:
        key, link = keys.generate(args.name)
    except subprocess.CalledProcessError:
        return 1                                  # the script has said why, on stderr
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    status = register(args, key)
    if status == 0:
        print(link)
    return status


def cmd_key_register(args: argparse.Namespace) -> int:
    """Register the key on stdin, for a key a client already has."""
    return register(args, sys.stdin.readline().strip())


def register(args: argparse.Namespace, key: str) -> int:
    from lib import keys

    try:
        keys.add(args.name, key, customer=args.customer,
                 scopes=args.scopes, referrers=args.referrers, rate=args.rate,
                 expires=args.expires, trial=args.trial)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f'key {args.name!r} registered; it is stored only as a hash', file=sys.stderr)
    return 0


def cmd_key_list(args: argparse.Namespace) -> int:
    """Every key's record, never the key."""
    from lib import keys

    print('name\tcustomer\tscopes\treferrers\trate\texpires\tdisabled\tcreated')
    for name, customer, scopes, referrers, rate, expires, disabled, created in keys.listing():
        print('\t'.join(str(v) for v in (
            name, customer or '', ','.join(scopes or keys.DEFAULT_SCOPES), ','.join(referrers) or 'any',
            rate or '', expires or '', 'yes' if disabled else 'no', f'{created:%Y-%m-%d}')))
    return 0


def cmd_key_disable(args: argparse.Namespace) -> int:
    """Disable or enable a key by name; the server notices within `auth.KEYS_TTL_S`."""
    from lib import keys

    if not keys.set_disabled(args.name, args.disabled):
        print(f'no key named {args.name!r}', file=sys.stderr)
        return 1
    print(f'key {args.name!r} {"disabled" if args.disabled else "enabled"}', file=sys.stderr)
    return 0


def cmd_usage_export(args: argparse.Namespace) -> int:
    """A month's requests per key, tiles and search apart, as CSV on stdout."""
    from lib import keys

    count = keys.export_usage(args.month, sys.stdout)
    print(f'{count} keys', file=sys.stderr)
    return 0


def cmd_stats_daily(args: argparse.Namespace) -> int:
    """Count the finished days, then drop the request log older than `request_log_days`."""
    from lib import stats

    counted, dropped = stats.daily()
    print(f'counted {", ".join(map(str, counted)) or "nothing new"}; '
          f'dropped {", ".join(dropped) or "nothing"}', file=sys.stderr)
    return 0


def cmd_stats_export(args: argparse.Namespace) -> int:
    """A month's requests, cache and host figures per day as CSV on stdout."""
    from lib import stats

    totals = stats.export(args.month, sys.stdout)
    print(f'{totals["requests"]} requests, {totals["errors"]} errors, cache hit rate '
          f'{totals["cache_hit_rate"] or "-"}, cost {totals["cost_eur"] or "-"} EUR, '
          f'{totals["eur_per_1000"] or "-"} EUR per 1000 requests', file=sys.stderr)
    return 0


def month(value: str) -> datetime.date:
    return datetime.datetime.strptime(value, '%Y-%m').date()


def day(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


#: The server in this container. /internal/reload is loopback-only, which is
#: exactly where this runs -- `docker compose exec app python tools/manage.py`.
RELOAD_URL = 'http://127.0.0.1:8000/internal/reload'


def reload_server(url: str = RELOAD_URL) -> str:
    """Ask the running server to load the new XML; say what happened.

    `compile-styles` generates, then reloads; the reload
    also picks up a newer complete import. A server that is not
    running is not an error -- it loads the XML when it starts.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='POST'),
                                    timeout=600) as response:
            loaded = json.loads(response.read()).get('reloaded', {})
    except urllib.error.URLError as exc:
        return f'no server answered on {url} ({exc.reason}); it loads the styles when it starts'
    count = sum(len(themes) for themes in loaded.values())
    return f'the server reloaded {count} theme/grid pairs'


def cmd_pre_cache(args: argparse.Namespace) -> int:
    """Seed the pre-cache tier for every configured set and theme."""
    from lib import db
    from renderer import precache

    results = precache.run(db.active_schema(args.area), themes=args.themes or None,
                           workers=args.workers, force=args.force, fast=args.fast)
    total = rendered = 0
    for tms, themes in sorted(results.items()):
        for theme, result in sorted(themes.items()):
            total += result.tiles
            rendered += result.rendered
            print(f'{tms:24} {theme:14} {result.tiles:7} tiles  '
                  f'{result.rendered:7} rendered  {result.seconds:7.1f} s')
    print(f'\n{rendered} rendered of {total} tiles', file=sys.stderr)
    return 0


def parser() -> argparse.ArgumentParser:
    from lib import keys

    main = argparse.ArgumentParser(prog='manage.py', description=__doc__.split('\n\n')[0])
    main.add_argument('-v', '--verbose', action='store_true', help='log every step as it runs')
    commands = main.add_subparsers(dest='command', required=True)

    area_help = 'area; defaults to the `serve_area` option'

    import_ = commands.add_parser(
        'import', help='import an area into a new schema',
        description='Download the extract if needed, then import it into a new schema '
                    '<area>_<yyyymmdd>_<hhmmss>. The served schema is left alone; the '
                    'server changes to the new one when it is reloaded. The two newest '
                    'complete imports of the area are kept.')
    import_.add_argument('area', choices=sorted(extract.areas()), help='area to import')
    import_.add_argument('--no-water', action='store_true',
                         help='skip the osmdata water polygons (no sea, and empty low-zoom bands)')
    import_.add_argument('-pw', '--pass-workers', type=int, choices=(1, 2, 3), default=1,
                         help='pbf passes run at a time; each of the ways and areas passes '
                              'holds every node location of the file (default 1)')
    import_.set_defaults(func=cmd_import)

    init_elevation = commands.add_parser(
        'init-elevation', help='draw the contour lines once, from the elevation rasters',
        description='Mosaic the GeoTIFFs the elevation_sources option names, resample, '
                    'contour and filter them into the schema `elevation`, replacing what '
                    'is there. Run once, and again only when the rasters or the contours '
                    'parameters change; every import after it copies its area\'s lines.')
    init_elevation.add_argument('--download', action='store_true',
                                help='first fetch the elevation_tiles not yet on disk '
                                     'from elevation_base')
    init_elevation.set_defaults(func=cmd_init_elevation)

    compile_styles = commands.add_parser(
        'compile-styles', help='compile the style files to Mapnik XML',
        description='Generate one Mapnik XML per theme (palette x detail) and grid from '
                    'styles/*.yaml into <data_dir>/styles/<schema>/<grid>/, for the area\'s '
                    'newest complete import (or force_schema). Refuses to write '
                    'anything if a style check fails. Leaves the tile cache alone.')
    compile_styles.add_argument('area', nargs='?', default=None, help=area_help)
    compile_styles.set_defaults(func=cmd_compile_styles)

    seed = commands.add_parser(
        'pre-cache', help='seed the pre-cache tier',
        description='Render every tile of every configured TileMatrixSet and theme '
                    'up to that set\'s precache depth, over the imported extent. '
                    'Already-cached tiles are left alone unless --force.')
    seed.add_argument('area', nargs='?', default=None, help=area_help)
    seed.add_argument('--fast', action='store_true',
                      help='only the levels with at most pre_cache_fast_max tiles per grid')
    seed.add_argument('--themes', nargs='*', default=None,
                      help='themes to seed; defaults to every compiled one')
    seed.add_argument('--workers', type=int, default=None,
                      help='concurrent renders; defaults to map_pool_size')
    seed.add_argument('--force', action='store_true',
                      help='re-render tiles that are already cached')
    seed.set_defaults(func=cmd_pre_cache)

    drop = commands.add_parser(
        'drop-cache', help='empty the tile cache of an area',
        description='Remove every cached tile of the area, both tiers.')
    drop.add_argument('area', nargs='?', default=None, help=area_help)
    drop.add_argument('--ondemand', action='store_true',
                      help='only the on-demand tier; `pre-cache --force` overwrites the other, '
                           'which keeps serving the old tiles until then (manage.sh update)')
    drop.set_defaults(func=cmd_drop_cache)

    for command, func, help_text, description in (
            ('key-add', cmd_key_add, 'generate an API key, send it, register it',
             'Generate a key with scripts/vaultwarden-send.sh, which puts it into a Vaultwarden '
             'Send, store its SHA-256 and print the Send link -- never the key. Runs in the '
             '`keys` container, which has the Bitwarden CLI: `manage.sh key-add`.'),
            ('key-register', cmd_key_register, 'register the API key on stdin',
             'Read a key from stdin and store its SHA-256: for a key a client already has. '
             'New keys are made by key-add.')):
        key_add = commands.add_parser(command, help=help_text, description=description)
        key_add.add_argument('name', help='unique name, the key\'s id in the usage export')
        key_add.add_argument('--customer', help='who is invoiced for it')
        key_add.add_argument('--scopes', nargs='+', default=[], metavar='SCOPE',
                             help='tiles, search and/or devtools; none means tiles and search')
        key_add.add_argument('--referrers', nargs='+', default=[], metavar='PATTERN',
                             help='glob patterns for Origin/Referer, e.g. https://maps.example.de/*')
        key_add.add_argument('--rate', type=int, help='requests per minute')
        expiry = key_add.add_mutually_exclusive_group()
        expiry.add_argument('--trial', action='store_true',
                            help=f'valid for {keys.TRIAL_DAYS} days from today')
        expiry.add_argument('--expires', type=day, metavar='YYYY-MM-DD',
                            help='the last day the key is valid (UTC)')
        key_add.set_defaults(func=func)

    key_list = commands.add_parser('key-list', help='list the API keys, without the keys')
    key_list.set_defaults(func=cmd_key_list)

    for name, disabled in (('key-disable', True), ('key-enable', False)):
        toggle = commands.add_parser(name, help=f'{name.split("-")[1]} an API key')
        toggle.add_argument('name')
        toggle.set_defaults(func=cmd_key_disable, disabled=disabled)

    usage = commands.add_parser(
        'usage-export', help='export a month\'s requests per key as CSV',
        description='Write key;customer;month;tiles;search;errors for every key to stdout, a key '
                    'without requests with zeros.')
    usage.add_argument('month', type=month, metavar='YYYY-MM')
    usage.set_defaults(func=cmd_usage_export)

    stats_daily = commands.add_parser(
        'stats-daily', help='count yesterday, drop the request log older than request_log_days',
        description='Create the request log\'s coming partitions, count every finished day '
                    'into service.daily_stats and daily_host, then drop the request log and '
                    'host samples older than request_log_days -- the IP addresses and search '
                    'terms with them. The app does this itself at start and daily; this is '
                    'the same run by hand.')
    stats_daily.set_defaults(func=cmd_stats_daily)

    stats_export = commands.add_parser(
        'stats-export', help='export a month\'s load figures as CSV',
        description='One line per day: requests by kind, errors, tile cache hit rate, '
                    '95th percentile durations, distinct IPs, CPU, RAM and disk. The totals '
                    'with monthly_cost_eur per 1000 requests go to stderr.')
    stats_export.add_argument('month', type=month, metavar='YYYY-MM')
    stats_export.set_defaults(func=cmd_stats_export)

    return main


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s %(message)s',
    )
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
