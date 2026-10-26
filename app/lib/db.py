"""Database connections.

Every consumer reaches Postgres through libpq's environment -- psycopg
here, Mapnik's PostGIS datasources with no connection parameters at all.
lib.config puts `db.host`/`db.port` and postgres.env's credentials there
when it loads; the credentials are in config/postgres.env and nowhere else,
which is what keeps them out of the image, the repository and the compiled
Mapnik XML (DESIGN.md "Configuration").

So there is deliberately nothing here that takes a host or a password.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql

from lib import config


def conninfo() -> str:
    """Empty: libpq takes everything from PGHOST and friends.

    Loading the options is what sets them, so it happens here first rather
    than relying on something else having asked for an option already.
    """
    config.load()
    return ''


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conninfo(), autocommit=autocommit)


@contextmanager
def connection(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = connect(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


# --- import schemas ------------------------------------------------------
#
# Every import writes a schema of its own, `<area>_<yyyymmdd>_<hhmmss>`,
# under the name `_<area>_...` until it is complete, so a re-import never
# touches the schema being served and an incomplete one is recognisable by
# name in any database tool. The server serves the newest complete schema of
# `serve_area`, or `force_schema` when that is set.

class NoImportError(LookupError):
    """The area has no complete import."""


def schema_name(area: str, started: datetime.datetime) -> str:
    return f'{area}_{started:%Y%m%d_%H%M%S}'


def temp_name(schema: str) -> str:
    return f'_{schema}'


def area_of(schema: str) -> str:
    """The area a schema belongs to; a schema of no import is its own area."""
    match = re.fullmatch(r'_?(.+)_\d{8}_\d{6}', schema)
    return match.group(1) if match else schema


def complete_schemas(conn, area: str) -> list[str]:
    """The area's complete imports, newest first."""
    rows = conn.execute(
        'select nspname from pg_namespace where nspname ~ %s order by nspname desc',
        (rf'^{re.escape(area)}_\d{{8}}_\d{{6}}$',)).fetchall()
    return [row[0] for row in rows]


def temp_schemas(conn, area: str) -> list[str]:
    """The area's incomplete imports: running, or left by one that failed."""
    rows = conn.execute(
        'select nspname from pg_namespace where nspname ~ %s order by nspname',
        (rf'^_{re.escape(area)}_\d{{8}}_\d{{6}}$',)).fetchall()
    return [row[0] for row in rows]


_active: dict[str, str] = {}


def active_schema(area: str | None = None) -> str:
    """The schema served for an area: `force_schema` if it is one of the area's,
    else the newest complete import.

    Resolved once per process and kept until `reset_active_schema()`, which
    `/internal/reload` calls: a tile must not cost a catalog query, and a
    schema that changed under a running server would be served from XML
    compiled for another.
    """
    area = area or config.opt('serve_area')
    forced = config.opt('force_schema')
    if forced and area_of(forced) == area:
        return forced
    if area not in _active:
        with connection() as conn:
            schemas = complete_schemas(conn, area)
        if not schemas:
            raise NoImportError(f'no complete import of {area!r}: run `manage.py import {area}`')
        _active[area] = schemas[0]
    return _active[area]


def reset_active_schema() -> None:
    _active.clear()


def schema_for(name: str | None) -> str:
    """A schema name as it is, an area's active schema, or the served one's."""
    if name and re.fullmatch(r'.+_\d{8}_\d{6}', name):
        return name
    return active_schema(name)


def table_classes(conn, schema: str, tables) -> dict[str, dict[str, int]]:
    """{table: {class: row count}} for the tables named.

    Which table a class lives in is a property of the data, not of the
    model: a rule with no `geometry:` restriction says a class *may* appear
    as a point, a line and an area, not that it does. The importer asks
    this to decide where a partial index belongs, and the style generator
    asks it to decide which table a layer reads. Both have to get the same
    answer, which is why it is here and not in either of them.
    """
    out = {}
    for name in tables:
        rows = conn.execute(sql.SQL('select class, count(*) from {} group by 1').format(
            sql.Identifier(schema, name))).fetchall()
        out[name] = dict(rows)
    return out


def table(schema: str, name: str) -> sql.Identifier:
    """A schema-qualified table name.

    The schema is an option and a filesystem path segment, so it reaches
    SQL as an identifier object rather than through an f-string -- the one
    place in the importer where a value from configuration becomes part of
    a statement.
    """
    return sql.Identifier(schema, name)
