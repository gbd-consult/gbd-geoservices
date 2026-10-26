"""Sequencing: schema, tables, passes, post-processing, import_meta.

`import_area()` is the whole import, and `tools/manage.py import <area>` is
what calls it. Every step with logic lives in its own module; this file
only puts them in order and times them, because every step is measured
(DESIGN.md "Principles") and a step that doubles the import time has to be
visible in the step that caused it.

Compiling the styles and pre-caching are `manage.py` commands of their
own; vector tiles do not exist yet.
"""

from __future__ import annotations

import datetime
import logging
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from psycopg import sql

from importer import changes, elevation, meta, passes, places, postprocess, water
from importer import tables as t
from lib import config, db

log = logging.getLogger('importer')

APP = Path(__file__).resolve().parent.parent
MODEL = APP / 'model'
STYLES = APP / 'styles'

#: Extensions the import and the queries depend on. No hstore: raw tags are
#: stored as jsonb.
EXTENSIONS = ('postgis', 'pg_trgm', 'fuzzystrmatch')

#: Complete imports kept per area: the one just made and the one it replaces,
#: which is still served until the reload and is the rollback after it.
KEEP_SCHEMAS = 2

#: Assigned by the water import; no rule produces it.
WATER_CLASS = 'cls_ocean'


class ClassDriftError(RuntimeError):
    """The rules and the style disagree about which classes exist."""


#: The steps of `import_area`, in order; the two water steps only with water.
STEPS = ('schema', 'passes', 'water', 'contours', 'merge streets', 'merge places', 'id_object', 'places',
         'dictionaries', 'bands', 'water bands', 'order', 'indexes', 'cluster', 'drop working tables',
         'finish')
WATER_STEPS = ('water', 'water bands')


class Steps:
    """Times each step and logs it as `[n/total] name`, so a long import
    says how far it is."""

    def __init__(self, names: tuple[str, ...]):
        self.names = names
        self.timings: dict[str, float] = {}

    @contextmanager
    def __call__(self, name: str):
        number = f'[{self.names.index(name) + 1}/{len(self.names)}]'
        started = time.monotonic()
        log.info('%s %s ...', number, name)
        yield
        self.timings[name] = time.monotonic() - started
        log.info('%s %s: %.1f s', number, name, self.timings[name])


def check_class_drift(classifier, params) -> None:
    """The classes the rules produce and the classes the style draws must be
    the same set.

    Both directions are silent and both are expensive to notice. A class in
    `classifier.yaml` that `classes.yaml` does not style gets no
    `minzoom_label` and no marker row, so it imports and is never labelled;
    a class in `classes.yaml` that no rule produces is a layer that draws
    nothing, on a map that renders without an error.

    Checked at import start (DESIGN.md "Import"). `ocean` and the contour
    classes are added because the water and contours steps assign them and no
    rule produces them.
    """
    ruled = classifier.classes | {WATER_CLASS, *elevation.classes()}
    styled = params.styled_classes
    missing = sorted(styled - ruled)
    unstyled = sorted(ruled - styled)
    if missing or unstyled:
        raise ClassDriftError(
            'classifier.yaml and styles/classes.yaml disagree; '
            f'styled but never produced: {missing or "none"}; '
            f'produced but never styled: {unstyled or "none"}')


def create_extensions(conn) -> None:
    for extension in EXTENSIONS:
        conn.execute(sql.SQL('create extension if not exists {}').format(sql.Identifier(extension)))


def create_schema(conn, schema: str) -> None:
    conn.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))


def drop_schema(conn, schema: str) -> None:
    conn.execute(sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(schema)))


@contextmanager
def area_lock(area: str):
    """One import per area at a time.

    A second import would drop the first one's schema as a leftover.
    """
    key = f'import:{area}'
    with db.connection(autocommit=True) as conn:
        if not conn.execute('select pg_try_advisory_lock(hashtext(%s))', (key,)).fetchone()[0]:
            raise RuntimeError(f'another import of {area!r} is running')
        try:
            yield
        finally:
            conn.execute('select pg_advisory_unlock(hashtext(%s))', (key,))


def publish(conn, area: str, schema: str, *, keep: int, data_dir: Path) -> list[str]:
    """Give the temp schema its final name, then drop all but the newest `keep`.

    The schema pinned by `force_schema` is never dropped, however old: it is
    being served. Each dropped schema's compiled styles go with it. Returns
    the dropped schemas.
    """
    conn.execute(sql.SQL('alter schema {} rename to {}').format(
        sql.Identifier(db.temp_name(schema)), sql.Identifier(schema)))
    pinned = config.opt('force_schema')
    dropped = [old for old in db.complete_schemas(conn, area)[keep:] if old != pinned]
    for old in dropped:
        drop_schema(conn, old)
    conn.commit()
    for old in dropped:
        shutil.rmtree(data_dir / 'styles' / old, ignore_errors=True)
    return dropped


def render_tables(params) -> list:
    bands = [t.band_table(base, band.suffix)
             for base in t.BANDED for band in params.bands]
    return [*t.RENDER_TABLES, *bands]


def all_tables(params) -> list:
    """Everything the passes write, including the merge input.

    _street_ends is created with the rest and dropped after the merge; it is
    a working table, not a product.
    """
    return [*render_tables(params), *t.SEARCH_TABLES, t.STREET_ENDS, t.IMPORT_META]


def create_tables(conn, schema: str, tables: list) -> None:
    for table in tables:
        conn.execute(t.ddl(schema, table))


def extract_box(extract: Path):
    """The extract's header box, in degrees."""
    import osmium

    reader = osmium.io.Reader(str(extract), osmium.osm.NOTHING)
    try:
        return reader.header().box()
    finally:
        reader.close()


def water_inputs(extract: Path, params):
    """The clip box and where the osmdata sets live."""
    downloads = Path(config.opt('data_dir', '/data')) / 'downloads'
    return (water.area_bbox(extract_box(extract), params.water_bbox_margin_deg), downloads,
            config.opt('water_polygons_base'))


def load_contours(conn, schema: str, extract: Path, params) -> dict[str, int]:
    bbox = water.area_bbox(extract_box(extract), params.contours.bbox_margin_deg)
    return {t.OSM_CONTOUR.name: elevation.load(conn, schema, bbox, params)}


def load_water(conn, schema: str, extract: Path, params) -> dict[str, int]:
    bbox, downloads, base = water_inputs(extract, params)
    shp = water.fetch(base, water.FULL, downloads)
    return {'osm_polygon': water.load(conn, schema, shp, bbox, params.copy_batch)}


def load_water_bands(conn, schema: str, extract: Path, params) -> dict[str, int]:
    bbox, downloads, base = water_inputs(extract, params)
    shp = water.fetch(base, water.SIMPLIFIED, downloads)
    return water.load_bands(conn, schema, shp, bbox, params, params.copy_batch)


def report_changes(conn, area: str, schema: str, params) -> list[str]:
    """The counts that moved against the area's previous complete import, as
    log lines (`importer/changes.py`); nothing to say for the first import."""
    previous = db.complete_schemas(conn, area)
    if not previous:
        return []
    old = changes.counts(meta.read(conn, previous[0]) or {})
    new = changes.counts(meta.read(conn, schema) or {})
    moved = changes.compare(old, new, change_pct=params.report_change_pct,
                            min_rows=params.report_min_rows)
    return changes.report(previous[0], moved, len(old.keys() | new.keys()),
                          params.report_change_pct)


def import_area(extract: Path, area: str, *, params=None, water: bool = True,
                pass_workers: int = 1) -> dict:
    """The whole import, into a new schema of the area.

    Returns per-step timings, row counts and the schema's name.
    """
    from importer import params as params_module
    params = params or params_module.load(MODEL, STYLES)
    from importer import rules as rules_module
    classifier = rules_module.load(MODEL)
    check_class_drift(classifier, params)

    step = Steps(STEPS if water else tuple(n for n in STEPS if n not in WATER_STEPS))
    timings = step.timings
    started = time.monotonic()
    final = db.schema_name(area, datetime.datetime.now())
    schema = db.temp_name(final)
    data_dir = Path(config.opt('data_dir', '/data'))

    with area_lock(area):
        with db.connection() as conn, step('schema'):
            create_extensions(conn)
            # Left by an import that failed; the lock says none is running.
            for leftover in db.temp_schemas(conn, area):
                log.info('dropping %s, left by an incomplete import', leftover)
                drop_schema(conn, leftover)
            create_schema(conn, schema)
            create_tables(conn, schema, all_tables(params))
            conn.commit()

        # The passes open their own connections, in their own processes.
        with step('passes'):
            counts = passes.run(extract, schema, MODEL, STYLES, pass_workers)

        with db.connection() as conn:
            if water:
                with step('water'):
                    counts['water'] = load_water(conn, schema, extract, params)
            with step('contours'):
                counts['contours'] = load_contours(conn, schema, extract, params)
            with step('merge streets'):
                counts['merged_streets'] = postprocess.merge_streets(conn, schema, classifier)
            with step('merge places'):
                counts['merged_places'] = places.merge_nodes(conn, schema)
            with step('id_object'):
                counts['id_object'] = postprocess.resolve_id_object(conn, schema)
            with step('places'):
                counts['places'] = places.resolve(conn, schema, params)
            with step('dictionaries'):
                street_classes = [cls for cls in classifier.classes
                                  if params.is_merge_class(cls)]
                counts['dictionaries'] = postprocess.build_dictionaries(
                    conn, schema, classifier, config.opt('languages', ['de', 'en']),
                    street_classes)
            with step('bands'):
                counts['bands'] = postprocess.build_bands(conn, schema, params)
            if water:
                with step('water bands'):
                    counts['water'].update(load_water_bands(conn, schema, extract, params))
                conn.commit()
            with step('order'):
                postprocess.order_tables(conn, schema, [*t.RENDER_TABLES, *t.SEARCH_TABLES])
            with step('indexes'):
                # Band tables are deliberately not in this list: cluster_bands
                # builds their GiST and then CLUSTERs on it, and a second
                # identical index would be built here for nothing.
                statements = postprocess.all_index_statements(
                    conn, schema, params, [*t.RENDER_TABLES, *t.SEARCH_TABLES])
                # Inside the block, not after it. The build is the expensive
                # half -- minutes on a real extract against milliseconds of
                # planning -- and outside it `timings['indexes']` would report
                # the planning, and the longest step of the whole
                # post-processing would be the one step nothing measured.
                counts['indexes'] = postprocess.create_indexes(
                    schema, statements, params.index_workers, params.progress_s)
            with step('cluster'):
                postprocess.cluster_bands(conn, schema, params)

        with db.connection() as conn, step('drop working tables'):
            postprocess.drop_working_tables(conn, schema)

        # VACUUM cannot run inside a transaction block.
        with db.connection(autocommit=True) as conn, step('finish'):
            postprocess.finish(conn, schema, [*render_tables(params), *t.SEARCH_TABLES])

        timings['total'] = time.monotonic() - started

        with db.connection() as conn:
            # Counted once here, where the rows are made; the style run reads
            # it at every app start, and counting there takes 22 s on de.
            meta.write(conn, schema, area=area, extract=extract,
                       row_counts=counts, duration_s=timings['total'],
                       style_zooms=params.style_zooms(),
                       table_classes=postprocess.table_classes(conn, schema))
            # Before the rename, while the newest complete schema is still the previous import.
            for line in report_changes(conn, area, schema, params):
                log.info(line)
            # Last: until the rename the schema is `_<name>`, which nothing
            # serves and the next import drops.
            dropped = publish(conn, area, final, keep=KEEP_SCHEMAS, data_dir=data_dir)
        log.info('%s complete%s', final, f'; dropped {", ".join(dropped)}' if dropped else '')

        return {'schema': final, 'timings': timings, 'counts': counts}


#: The render tables whose rows are the map's features, as the passes count them.
FEATURES = ('point', 'line', 'polygon', 'building')


def summary(extract: Path, result: dict) -> str:
    """One line for the end of the import log: the input, what came out, how fast."""
    counts = result['counts']
    features = {name: sum(counts.get(pass_name, {}).get(name, 0)
                          for pass_name in ('nodes', 'ways', 'areas'))
                for name in FEATURES}
    total = sum(features.values())
    seconds = result['timings']['total']
    places = counts.get('places', {})
    return (f'{extract.stat().st_size / 1e6:,.1f} MB pbf, {total:,} features ('
            + ', '.join(f'{name} {count:,}' for name, count in features.items())
            + f'), {places.get("objects", 0):,} search objects, '
            f'{places.get("addresses", 0):,} addresses, '
            f'{total / seconds if seconds else 0:,.0f} features/s')
