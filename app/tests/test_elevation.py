"""The contour build of importer/elevation.py, on hand-made lines.

`init()` itself needs GDAL and the rasters, and `load()` reads the real
`elevation` schema, which a test must not overwrite; what is tested here is
the SQL between the two -- classes, the bump filter, the cutting -- in a
scratch schema.
"""

from __future__ import annotations

from importer import elevation
from importer.params import Contours

C = Contours(levels_m=(1000, 500, 250, 100, 50), cell_m=60, min_ring_m=300, simplify_m=0,
             subdivide_vertices=8, bbox_margin_deg=0.05)


def build(db, schema, lines):
    from psycopg import sql

    raw, built = sql.Identifier(schema, '_raw'), sql.Identifier(schema, '_built')
    db.execute(sql.SQL('create table {} (ele double precision, geom geometry(LineString, 3857))')
               .format(raw))
    for ele, wkt in lines:
        db.execute(sql.SQL('insert into {} values (%s, st_geomfromtext(%s, 3857))').format(raw),
                   (ele, wkt))
    count = elevation._build(db, raw, built, C)
    return count, db.execute(sql.SQL('select class, ele, st_npoints(geom) from {} order by ele')
                             .format(built)).fetchall()


def test_classes_bumps_and_pieces(db, temp_schema):
    line = 'LINESTRING(0 0, 1000 0)'
    zigzag = 'LINESTRING(' + ', '.join(f'{x * 10} {x % 2 * 10}' for x in range(30)) + ')'
    count, rows = build(db, temp_schema, [
        (999.9999999, line),                                        # a float on a multiple of 1000
        (0.0000001, line),                                          # sea level: dropped
        (1500, line),                                               # 500, not 1000
        (1250, line),                                               # 250: not a multiple of 100, still a level
        (1300, line),                                               # 100
        (1350, zigzag),                                             # 50; 30 vertices, cut into pieces
        (1400, 'LINESTRING(0 0, 50 0, 50 50, 0 50, 0 0)'),         # a 200 m ring: a tree, dropped
        (1550, 'LINESTRING(0 0, 500 0, 500 500, 0 500, 0 0)'),     # a 2 km ring: a hill, kept
    ])
    classes = {ele: cls for cls, ele, _ in rows}
    assert 0 not in classes
    assert classes == {1000: 'cls_contour_1000', 1500: 'cls_contour_500', 1250: 'cls_contour_250',
                       1300: 'cls_contour_100', 1350: 'cls_contour_50', 1550: 'cls_contour_50'}
    pieces = [r for r in rows if r[1] == 1350]
    assert len(pieces) > 1 and all(r[2] <= C.subdivide_vertices for r in pieces)
    assert count == len(rows)


def test_the_classes_follow_the_levels():
    assert elevation.classes() == ('cls_contour_1000', 'cls_contour_500', 'cls_contour_250',
                                   'cls_contour_100', 'cls_contour_50')
