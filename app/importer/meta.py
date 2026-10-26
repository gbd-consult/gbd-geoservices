"""`import_meta`: what this schema was built from.

Written last and inside its own transaction, so its presence is what says
the import finished -- a schema without a row in it is a partial import
(DESIGN.md "Schemas and imports").

There are no file fingerprints: hashes of the model and style files would
flag an import after edits the import never reads (colours, search
weights). The one change that silently breaks a map, a class starting at an earlier
zoom than its rows were written for, is caught exactly by `style_zooms`.
Production re-imports in full every week.
"""

from __future__ import annotations

import json
from pathlib import Path

from psycopg import sql


def replication(extract: Path) -> dict[str, object]:
    """The extract's replication position, from the pbf header.

    Authoritative even for a cached file.
    No diff path is built -- an update is a full re-import -- but recording
    the position means one can be added later without re-importing first.
    """
    import osmium

    reader = osmium.io.Reader(str(extract), osmium.osm.NOTHING)
    try:
        header = reader.header()
        sequence = header.get('osmosis_replication_sequence_number')
        return {
            'replication_base_url': header.get('osmosis_replication_base_url') or None,
            'replication_sequence': int(sequence) if sequence else None,
            'extract_timestamp': header.get('osmosis_replication_timestamp') or None,
        }
    finally:
        reader.close()


def bbox_3857(extract: Path) -> tuple[float, float, float, float]:
    """The extract's own bounding box, projected.

    The area's extent, which `manage.py pre-cache` needs to know how much to
    seed. Taken from the pbf header rather than from `ST_Extent` over a
    table: the extent of the road table is inflated by maritime boundaries
    -- for `de_sh` to 7.4-12.3 E against 8.3-11.3 E of actual highways -- and
    pre-caching that would spend most of its time on open sea.
    """
    import numpy as np
    import osmium

    from importer import geometry as geom

    reader = osmium.io.Reader(str(extract), osmium.osm.NOTHING)
    try:
        box = reader.header().box()
    finally:
        reader.close()
    corners = geom.mercator(np.array([
        [box.bottom_left.lon, box.bottom_left.lat],
        [box.top_right.lon, box.top_right.lat],
    ], dtype=float))
    return (corners[0][0], corners[0][1], corners[1][0], corners[1][1])


def write(conn, schema: str, *, area: str, extract: Path,
          row_counts: dict, duration_s: float, style_zooms: dict,
          table_classes: dict) -> None:
    minx, miny, maxx, maxy = bbox_3857(extract)
    values = {
        'area': area,
        'source': extract.name,
        'row_counts': json.dumps(row_counts, default=str),
        'style_zooms': json.dumps(style_zooms),
        'table_classes': json.dumps(table_classes),
        'duration_s': int(duration_s),
        'minx': minx, 'miny': miny, 'maxx': maxx, 'maxy': maxy,
        **replication(extract),
    }
    conn.execute(sql.SQL("""
        insert into {} (id, area, source, extract_timestamp, replication_base_url,
                        replication_sequence, duration_s, row_counts, style_zooms,
                        table_classes, bbox_3857)
        values (1, %(area)s, %(source)s, %(extract_timestamp)s, %(replication_base_url)s,
                %(replication_sequence)s, %(duration_s)s, %(row_counts)s, %(style_zooms)s,
                %(table_classes)s, st_makeenvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 3857))
    """).format(sql.Identifier(schema, 'import_meta')), values)
    conn.commit()


def update(conn, schema: str, **values) -> None:
    """Set columns of the one row; mappings are stored as JSON."""
    conn.execute(sql.SQL('update {} set {}').format(
        sql.Identifier(schema, 'import_meta'),
        sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(name)) for name in values)),
        [json.dumps(value) if isinstance(value, dict) else value for value in values.values()])
    conn.commit()


def read(conn, schema: str) -> dict | None:
    row = conn.execute(sql.SQL('select to_jsonb(m) from {} m').format(
        sql.Identifier(schema, 'import_meta'))).fetchone()
    return row[0] if row else None
