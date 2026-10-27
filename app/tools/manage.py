"""Management commands.

    python tools/manage.py init-elevation [--download]
    python tools/manage.py import <area> [--no-water] [--pass-workers 1|2|3]
    python tools/manage.py compile-styles [<area>]
    python tools/manage.py pre-cache [<area>] [--fast] [--force]
    python tools/manage.py drop-cache [<area>]

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
    """Empty both tile-cache tiers of an area."""
    from lib import config

    area = args.area or config.opt('serve_area')
    print(f'{cache.clear_area(area)} cached tiles of {area} removed', file=sys.stderr)
    return 0


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
    drop.set_defaults(func=cmd_drop_cache)

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
