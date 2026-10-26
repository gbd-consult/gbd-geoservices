"""Batched COPY into one table.

Text COPY with hex EWKB, not binary: PostGIS's geometry input reads hex
EWKB directly, so no psycopg dumper has to be registered per geometry type,
and what a failed import sent can be read as plain text. The escaping
surface is four characters.

Rows arrive with shapely geometries still in their geometry columns. The
whole batch is converted on flush, because shapely's vectorised call hands
one array of coordinates to one callback -- 2.6 us per geometry against
20 us one at a time -- and that is most of what the geometry work costs.
"""

from __future__ import annotations

from typing import Any

from importer import geometry as geom
from importer import tables as t

#: Everything text COPY treats specially. NULL is \\N, which is why a
#: backslash in the data has to be doubled first.
_ESCAPES = str.maketrans({'\\': '\\\\', '\t': '\\t', '\n': '\\n', '\r': '\\r'})

NULL = r'\N'


def array_literal(values) -> str:
    """A Postgres array literal, before COPY escaping.

    Quoted elements, because a category id is safe but a name is not; the
    result is then escaped again by `field`, which is correct -- COPY
    unescapes first and hands the array parser what is left.
    """
    if values is None:
        return NULL
    if not len(values):
        return '{}'
    parts = []
    for value in values:
        if value is None:
            parts.append('NULL')
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            parts.append(str(value))
        else:
            escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
            parts.append(f'"{escaped}"')
    return '{' + ','.join(parts) + '}'


def field(value: Any) -> str:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return 't' if value else 'f'
    if isinstance(value, (list, tuple)):
        return array_literal(value).translate(_ESCAPES)
    return str(value).translate(_ESCAPES)


class TableWriter:
    """One table, one connection, buffered.

    Not a context manager on purpose: the passes open several of these at
    once and close them together through an ExitStack.
    """

    def __init__(self, conn, schema: str, table: t.Table, batch: int = 10_000):
        self._conn = conn
        self._table = table
        self._sql = t.copy_sql(schema, table)
        self._geometry = t.geometry_columns(table)
        self._width = len(t.copy_columns(table))
        self._batch = batch
        self._rows: list[list[Any]] = []
        self.written = 0

    def add(self, row) -> None:
        if len(row) != self._width:
            raise ValueError(
                f'{self._table.name} takes {self._width} columns, got {len(row)}: {row!r}')
        self._rows.append(list(row))
        if len(self._rows) >= self._batch:
            self.flush()

    def flush(self) -> None:
        if not self._rows:
            return
        rows = self._rows
        self._rows = []

        for index, srid in self._geometry:
            present = [i for i, row in enumerate(rows) if row[index] is not None]
            if not present:
                continue
            encoded = geom.hex_ewkb([rows[i][index] for i in present], srid)
            # strict: one encoded value per geometry handed in. A silent
            # truncation here would leave shapely objects in the row and
            # write their repr into a geometry column.
            for i, value in zip(present, encoded, strict=True):
                rows[i][index] = value

        with self._conn.cursor().copy(self._sql) as copy:
            for row in rows:
                copy.write('\t'.join(field(value) for value in row))
                copy.write('\n')
        self.written += len(rows)

    def close(self) -> int:
        self.flush()
        return self.written
