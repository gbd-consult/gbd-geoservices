"""Every table the import writes, defined once.

The column list here is what `CREATE TABLE` is built from *and* what the
`COPY` statement names, so the two cannot drift apart -- a row tuple that
does not match its table is a length mismatch at the first flush rather
than a column silently shifted by one.

Geometry is EPSG:3857 in the render tables and EPSG:4326 in the search
tables (DESIGN.md "Database"). Everything is created UNLOGGED and
switched to logged at the end of the import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from psycopg import sql

Column = tuple[str, str]


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    indexes: tuple[str, ...] = ()          # index bodies, e.g. 'using gist (geom)'
    unlogged: bool = True
    cluster_on: str | None = None          # index body to CLUSTER on, for the bands
    order_by: str | None = None            # expression the rows are physically sorted by


def column_names(table: Table) -> tuple[str, ...]:
    return tuple(name for name, _ in table.columns)


def copy_columns(table: Table) -> tuple[Column, ...]:
    """The columns a COPY supplies.

    A `serial` is filled by its sequence, so it is not in the stream -- and
    it cannot be: the three passes write the search tables concurrently, so
    nothing on the Python side can hand out ids that do not collide.
    """
    return tuple((name, kind) for name, kind in table.columns if 'serial' not in kind)


def copy_names(table: Table) -> tuple[str, ...]:
    return tuple(name for name, _ in copy_columns(table))


def geometry_columns(table: Table) -> tuple[tuple[int, int], ...]:
    """(position in the COPY row, srid) for each geometry column.

    The writer buffers shapely objects in those positions and converts a
    whole batch in one vectorised call, so the SRID has to come from the
    same declaration the column was created with rather than being passed
    in alongside.
    """
    out = []
    for index, (_, kind) in enumerate(copy_columns(table)):
        if kind.startswith('geometry('):
            srid = kind.split(',')[-1].split(')')[0].strip()
            out.append((index, int(srid)))
    return tuple(out)


def ddl(schema: str, table: Table) -> sql.Composed:
    body = sql.SQL(', ').join(
        sql.SQL('{} {}').format(sql.Identifier(name), sql.SQL(kind))
        for name, kind in table.columns
    )
    return sql.SQL('create {} table {} ({})').format(
        sql.SQL('unlogged' if table.unlogged else ''),
        sql.Identifier(schema, table.name),
        body,
    )


def copy_sql(schema: str, table: Table) -> sql.Composed:
    return sql.SQL('copy {} ({}) from stdin').format(
        sql.Identifier(schema, table.name),
        sql.SQL(', ').join(sql.Identifier(name) for name in copy_names(table)),
    )


#: Postgres identifiers are 63 bytes; longer names are silently truncated,
#: which would put two of ours back in collision.
NAME_MAX = 63


def index_name(table: str, body: str) -> str:
    """A deterministic, explicit name for an index.

    Auto-naming is not usable here for two reasons. `(geom_center)` and
    `((geom_center::geography))` both derive `<table>_geom_center_idx`, and
    so does every partial index on the same column, so the names collide.
    And because the indexes are built over four connections at once, two
    workers can pick the same free name before either has inserted it --
    a race that surfaces as a unique violation on pg_class.
    """
    words = re.findall(r'[a-z_][a-z0-9_]*', body.lower())
    skip = {'using', 'gist', 'gin', 'btree', 'where', 'class', 'any', 'is', 'not', 'null'}
    parts = [w for w in words if w not in skip]
    name = '_'.join([table, *parts, 'idx'])
    return name[:NAME_MAX]


def index_statements(schema: str, table: Table) -> list[sql.Composed]:
    """Every index of one table.

    `if not exists`, so that building a table's indexes twice is harmless.
    """
    return [
        sql.SQL('create index if not exists {} on {} {}').format(
            sql.Identifier(index_name(table.name, body)),
            sql.Identifier(schema, table.name),
            sql.SQL(body),
        )
        for body in table.indexes
    ]


# --- render tables ------------------------------------------------------

#: Shared by osm_point/line/polygon/building and every band table. In the
#: unioned bands (_z9, _z6) one row is many objects, so osm_id is 0 and
#: name, label and minzoom_label are NULL there.
RENDER_COLUMNS: tuple[Column, ...] = (
    ('osm_id', 'bigint not null'),           # negative for relations; not unique
    ('class', 'text not null'),
    ('name', 'text'),
    ('label', 'text'),                       # road ref, house number, elevation
    ('z_order', 'integer not null'),         # population for place_*, see params.z_order
    ('minzoom', 'smallint not null'),
    ('minzoom_label', 'smallint'),           # on osm_line this drives the line-label layers
)


#: A b-tree on `class`, alongside the partial GiST per layer. It is worth
#: having where the column discriminates --
#: 36 to 86 distinct values in the line, polygon, point and label tables --
#: and worth skipping on osm_building, which by construction holds exactly
#: one class and where the index would be 1.35 M pointers to every row.
CLASS_INDEX = ('using btree (class)',)


#: The rows of a full render table in the order of a Hilbert curve over
#: their bbox centres -- PostGIS sorts geometries that way. A tile's layer
#: query then reads a few contiguous pages instead of one page per row: on
#: de, as written by the passes, a z13 road layer read 2 576 heap
#: pages for 2 485 rows, 3.1 s on the server's volume. The centre of the
#: bbox and not the geometry itself, because a btree entry cannot hold a
#: large polygon.
RENDER_ORDER = 'st_centroid(st_envelope(geom))'


def _render(name: str, geometry: str, *, extra: tuple[Column, ...] = (),
            cluster: bool = False, class_index: bool = True) -> Table:
    if cluster:
        # A band is small and clustered on its geometry; a layer reads it
        # nearly whole, so a class index earns nothing.
        indexes: tuple[str, ...] = ('using gist (geom)',)
    else:
        indexes = CLASS_INDEX if class_index else ()
    return Table(
        name=name,
        columns=RENDER_COLUMNS + extra + (('geom', f'geometry({geometry}, 3857) not null'),),
        indexes=indexes,
        cluster_on='using gist (geom)' if cluster else None,
        order_by=None if cluster else RENDER_ORDER,
    )


#: `category` is the object's own category, the finest one (Result.category).
#: `icon` is not the importer's: `manage.py compile-styles` sets it from `category` and
#: styles/icons.yaml -- the icon file's key, or NULL where the category is not
#: drawn -- so changing an icon, or whether it is drawn, never needs a
#: re-import. `importance` is the category's (model/importance.yaml): the
#: marker query draws a row from the zoom its theme's detail gives that
#: importance, and orders by it, because markers do not overlap -- the first one
#: placed keeps its spot and the more important POI has to come first.
OSM_POINT = _render('osm_point', 'Point', extra=(
    ('category', 'text'),
    ('icon', 'text'),
    ('importance', 'smallint'),
))
OSM_LINE = _render('osm_line', 'LineString')
OSM_POLYGON = _render('osm_polygon', 'Polygon')
OSM_BUILDING = _render('osm_building', 'Polygon', class_index=False, extra=(
    ('height', 'real'),
    ('height_src', 'text'),                  # tag | levels | est
))

#: Point-placed labels only -- area, place, POI and building text. Line
#: labels and shields are not here: they need `placement: line`, which
#: Mapnik cannot do on a point geometry, so those layers read osm_line on
#: its own minzoom_label instead.
#:
#: `category`, `icon` and `importance` as on osm_point: an object that gets
#: an icon is labelled here only below the zoom its icon starts at, and
#: from there by the icon. `icon` is set by the style run, like osm_point's.
OSM_LABEL = Table('osm_label', (
    ('osm_id', 'bigint not null'),
    ('class', 'text not null'),
    ('name', 'text'),
    ('label', 'text'),
    ('z_order', 'integer not null'),
    ('minzoom_label', 'smallint not null'),
    ('category', 'text'),
    ('icon', 'text'),
    ('importance', 'smallint'),
    ('geom', 'geometry(Point, 3857) not null'),
), indexes=CLASS_INDEX, order_by='geom')

#: Contour lines, copied from the `elevation` schema by the import
#: (importer/elevation.py), `label` the height. A table of their own, not
#: osm_line: in hill country a tile holds tens of thousands of them, and every
#: line layer of every theme would read them through the GiST index only to
#: drop them on the class. Not banded: each level is a layer of its own with
#: its own partial index (styles/layers.yaml), so a low zoom reads only the
#: coarse levels, which are few lines. No class index either: the layers'
#: partial indexes are the class filter.
OSM_CONTOUR = _render('osm_contour', 'LineString', class_index=False)

RENDER_TABLES = (OSM_POINT, OSM_LINE, OSM_POLYGON, OSM_BUILDING, OSM_LABEL, OSM_CONTOUR)

#: Band tables are generated from the two banded geometry types and the
#: suffixes in parameters.yaml, so adding a band is a parameter change.
BANDED = {'osm_polygon': 'Polygon', 'osm_line': 'LineString'}


def band_table(base: str, suffix: str) -> Table:
    return _render(base + suffix, BANDED[base], cluster=True)


# --- search tables ------------------------------------------------------

OSM_SEARCH_OBJECT = Table('osm_search_object', (
    ('id', 'serial primary key'),
    ('osm_ids', 'bigint[] not null'),        # several for a merged street
    ('name', 'text not null'),               # no row without a name
    ('search_name', 'text'),
    ('search_text', 'text'),
    ('phon_name', 'text'),
    ('search_city', 'text'),
    ('categories', 'text[] not null'),       # matched leaves plus all ancestors
    ('category', 'text'),                    # the first rule that matched
    ('importance', 'smallint'),              # NULL without a category; 0 never gets a row
    ('class', 'text'),
    ('addr_street', 'text'),
    ('addr_housenumber', 'text'),
    ('addr_postcode', 'text'),
    ('addr_city', 'text'),
    # Exactly one of the three is set. GiST does not index NULLs, so each
    # index holds only rows of its own type. Multi- so that one object is
    # always one row: a merged street that does not connect is still one
    # highlight geometry.
    ('geom_point', 'geometry(Point, 4326)'),
    ('geom_line', 'geometry(MultiLineString, 4326)'),
    ('geom_polygon', 'geometry(MultiPolygon, 4326)'),
    ('geom_center', 'geometry(Point, 4326) not null'),
    ('tags', 'jsonb'),                       # display and debugging only, never queried
    ('id_places', 'integer[]'),              # the address path, see importer/places.py
), indexes=(
    'using gist (geom_point)',
    'using gist (geom_line)',
    'using gist (geom_polygon)',
    'using gist (geom_center)',
    # Distance ranking is specified in metres, and <-> on a 4326 geometry
    # returns degrees -- anisotropically wrong at 54 N, where a degree of
    # longitude is 0.59 of one of latitude. The functional index makes
    # `geom_center::geography <-> point` a metre-accurate KNN scan.
    'using gist ((geom_center::geography))',
    'using gin (categories)',
    # The fuzzy name search's two hot probes are `search_name %% q` and
    # `q <%% search_name`, which a btree cannot answer. search_text is
    # deliberately *not* trigram-indexed: nothing probes it, because it
    # carries each row's city and a probe for a bare city name would match
    # every row in that city. It is only scored, and scoring runs on rows a
    # probe already selected.
    'using gin (search_name gin_trgm_ops)',
    'using gin (phon_name gin_trgm_ops)',
    'using btree (search_name)',
    'using btree (phon_name)',
    'using btree (category)',
    # `location IN query.place` ANDs `id_places && places` into every text
    # probe. Without this index the place is a filter on the heap: on
    # de, "kita dormagen" rechecked 146 k rows for `% 'kita'` and
    # 844 k for the phonetic code to keep 7, 40 s from a cold cache.
    'using gin (id_places)',
    # Sorted by place like the render tables, so the rows of one town are
    # a few contiguous pages to the place rules rather than one page each.
), order_by='geom_center')

OSM_SEARCH_ADDRESS = Table('osm_search_address', (
    # A key of its own, because osm_id is not one: OSM ids are unique per
    # *type*, so a node and a way can share one, and 63 of Liechtenstein's
    # 12 629 addresses do. A result a client can page through needs a
    # stable identity, and an ORDER BY needs a unique tie-break.
    ('id', 'serial primary key'),
    # The OSM id of the object the address sits on, and the only thing that
    # makes id_object resolvable at all: the carrier's search-row id is a
    # serial the database assigns during a concurrent COPY, so nothing else
    # on the row identifies it afterwards.
    # It also lets a client fetch the building outline from osm_building
    # directly, which matters because few buildings are named and so few
    # addresses will ever have an id_object.
    ('osm_id', 'bigint not null'),
    ('street', 'text'),
    ('search_street', 'text'),
    ('phon_street', 'text'),
    ('postcode', 'text'),
    ('city', 'text'),
    ('housenumber', 'text'),
    ('number', 'integer'),                   # the integer part, for ordering 1, 2, 2a, 3
    ('number_part', 'text'),                 # the suffix, 'a' in '12a'
    ('geom', 'geometry(Point, 4326) not null'),
    ('id_object', 'integer'),                # the carrier, when it has a name of its own
    ('id_places', 'integer[]'),              # the address path, see importer/places.py
    # The carrier's own category, whatever its name: a pure address is shown
    # as what it sits on -- "Wohnhaus", "Garage" -- not as "Adresse". NULL
    # where the carrier is nothing but the address (an address node).
    ('category', 'text'),
), indexes=(
    'using gist (geom)',
    'using btree (search_street, postcode, number, number_part)',
    'using btree (osm_id)',
), order_by='geom')

OSM_CATEGORY_TERM = Table('osm_category_term', (
    ('term', 'text not null'),
    ('category', 'text not null'),
    ('phon_term', 'text'),
    ('lang', 'text not null'),
), indexes=(
    'using btree (term)',
    'using btree (phon_term)',
))

OSM_STREET = Table('osm_street', (
    ('search_street', 'text not null'),
    ('phon_street', 'text'),
    ('n', 'integer not null'),
), indexes=(
    'using btree (search_street)',
    'using gin (search_street gin_trgm_ops)',
    'using btree (phon_street)',
))

SEARCH_TABLES = (OSM_SEARCH_OBJECT, OSM_SEARCH_ADDRESS, OSM_CATEGORY_TERM, OSM_STREET)

#: Written by the ways pass, read by the street merge, dropped afterwards.
#: search_name and phon_name are computed in Python during the pass, which
#: is how the merged rows carry them without a SQL phonetic function.
STREET_ENDS = Table('_street_ends', (
    ('osm_id', 'bigint not null'),
    ('name', 'text not null'),
    ('search_name', 'text not null'),
    ('phon_name', 'text'),
    ('class', 'text not null'),
    ('category', 'text'),        # carried so the merged row needs no reclassification
    ('n1', 'bigint not null'),
    ('n2', 'bigint not null'),
))

#: One row, written last: its presence is what says the import completed.
IMPORT_META = Table('import_meta', (
    ('id', 'smallint primary key default 1 check (id = 1)'),
    ('area', 'text not null'),
    ('source', 'text not null'),
    ('extract_timestamp', 'timestamptz'),
    ('replication_base_url', 'text'),
    ('replication_sequence', 'bigint'),
    ('imported_at', 'timestamptz not null default now()'),
    ('duration_s', 'integer'),
    ('row_counts', 'jsonb not null'),
    ('style_zooms', 'jsonb'),                # {class: [minzoom, minzoom_label]} the rows were written with
    ('table_classes', 'jsonb'),              # {render table: {class: rows}}, what the style run reads
    ('icons_applied', 'text'),               # the icon mapping osm_point/osm_label.icon was last set from
    ('bbox_3857', 'geometry(Polygon, 3857)'),
), unlogged=False)
