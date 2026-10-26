"""The point mode: everything at one point.

A point (`near`) and a radius instead of a query string, optionally narrowed
by `categories`. DESIGN.md "Modes": optionally the nearest address, then
the points and lines near it, nearest first, then the areas that contain
it, smallest first. The render tables are
not involved; this reads the same search objects everything else does.

The order is the answer. A click on a bar means the bar: what lies under
the cursor comes first, by distance. The areas that contain the point --
a country, a municipality and a park at once -- are where it is, not what
it is, and follow, the most specific first. Listed first, they put four
boundaries above a bar clicked 0.1 m away.

Points and lines are *one* list, interleaved by distance, not two lists one
after the other. They have different radii (50 m and 25 m) because a line
passing nearby is a weaker answer than a POI at the same distance, but once
both are in, a footpath 5 m away is a better answer than a shop 30 m away
and has to come first.

Three indexed lookups, one statement. Each has its own index and its own
ordering, and concatenating them in SQL rather than in Python keeps it to
one round trip. `limit` cuts the concatenation, so it drops areas first.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from search import shape

#: Rows per part. A point lookup is a click, and a client shows a handful.
PART_LIMIT = 20

SQL = f"""
    WITH pt AS MATERIALIZED (
        SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) AS g
    ),
    areas AS (
        SELECT {{columns}}, 1 AS part,
               ST_Area(o.geom_polygon) AS sort_key,
               0.0 AS distance,
               {shape.GEOJSON_EXPR} AS geojson,
               {shape.CENTER_EXPR} AS center
        FROM {{objects}} o, pt
        WHERE o.geom_polygon && pt.g AND ST_Contains(o.geom_polygon, pt.g){{filter}}
        ORDER BY sort_key ASC
        LIMIT %(part_limit)s
    ),
    points AS (
        SELECT {{columns}}, 0 AS part,
               ST_Distance(o.geom_center::geography, pt.g::geography) AS sort_key,
               ST_Distance(o.geom_center::geography, pt.g::geography) AS distance,
               {shape.GEOJSON_EXPR} AS geojson,
               {shape.CENTER_EXPR} AS center
        FROM {{objects}} o, pt
        WHERE o.geom_point IS NOT NULL
          AND ST_DWithin(o.geom_center::geography, pt.g::geography, %(point_radius)s){{filter}}
        ORDER BY sort_key ASC
        LIMIT %(part_limit)s
    ),
    lines AS (
        SELECT {{columns}}, 0 AS part,
               ST_Distance(o.geom_line::geography, pt.g::geography) AS sort_key,
               ST_Distance(o.geom_line::geography, pt.g::geography) AS distance,
               {shape.GEOJSON_EXPR} AS geojson,
               {shape.CENTER_EXPR} AS center
        FROM {{objects}} o, pt
        WHERE o.geom_line && ST_Expand(pt.g, %(line_degrees_lon)s, %(line_degrees_lat)s)
          AND ST_DWithin(o.geom_line::geography, pt.g::geography, %(line_radius)s){{filter}}
        ORDER BY sort_key ASC
        LIMIT %(part_limit)s
    )
    SELECT *, count(*) OVER () AS total_count FROM (
        SELECT * FROM areas
        UNION ALL SELECT * FROM points
        UNION ALL SELECT * FROM lines
    ) parts
    ORDER BY part ASC, sort_key ASC
    LIMIT %(limit)s
"""

#: `categories` holds every row's ancestors, so an overlap with the
#: requested ids is "one of these or below", as in the name mode.
CATEGORY_FILTER = '\n          AND o.categories && %(categories)s'

#: The nearest address, for a client that wants to label the click.
#:
#: Ordered by metres, not by `geom <-> pt`. That operator measures *degrees*
#: on a 4326 geometry, and at 54 N a degree of longitude is 0.59 of one of
#: latitude -- so an address 40 m north sorted ahead of one 30 m east and
#: "nearest" was the wrong house. The `&&` box is what reaches the GiST
#: index (`ST_DWithin` on a cast to geography cannot: there is no functional
#: index on `(geom::geography)`), and it leaves a handful of rows for the
#: exact recheck and the metric sort.
ADDRESS_SQL = f"""
    WITH pt AS MATERIALIZED (
        SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) AS g
    )
    SELECT a.id, a.osm_id, a.street, a.housenumber, a.postcode, a.city,
           a.id_object, a.id_places, a.category,
           ST_AsGeoJSON(a.geom, {shape.GEOJSON_DECIMALS}) AS geojson,
           ST_Distance(a.geom::geography, pt.g::geography) AS distance
    FROM {{addresses}} a, pt
    WHERE a.geom && ST_Expand(pt.g, %(address_degrees_lon)s, %(address_degrees_lat)s)
      AND ST_DWithin(a.geom::geography, pt.g::geography, %(address_radius)s)
    ORDER BY distance ASC, a.id ASC
    LIMIT 1
"""

#: Degrees of *latitude* per metre. A degree of longitude is this one times
#: cos(latitude), which is where the `&&` pre-filters below get their second
#: number from.
DEGREES_PER_METRE = 1.0 / 111_320.0

#: How far the `&&` box is widened beyond the radius it stands in front of.
#: The box only has to be a superset of what ST_DWithin then rechecks
#: exactly, so erring wide costs a few recheck rows and erring narrow drops
#: results silently.
BOX_MARGIN = 1.10

#: cos(latitude) is not allowed to reach zero: at the poles a metre is
#: unboundedly many degrees of longitude, and the box would be the world.
#: 60 degrees of slack is far more than any OSM extract needs.
_MIN_COS_LAT = 0.5


def degrees_for(metres: float, lat: float) -> tuple[float, float]:
    """`metres` as (degrees of longitude, degrees of latitude) at `lat`.

    Two numbers, not one. `ST_Expand(g, d)` widens both axes by the same
    `d`, which at 54 N is 25 m north-south and 14.7 m east-west -- so a line
    20 m due east passed `ST_DWithin(..., 25)` and was thrown away by the
    box in front of it. Nothing failed; the row was simply never seen.
    """
    lat_degrees = metres * DEGREES_PER_METRE * BOX_MARGIN
    return lat_degrees / max(math.cos(math.radians(lat)), _MIN_COS_LAT), lat_degrees

_radii: dict[str, float] | None = None


def radii(model_dir: Path | None = None) -> dict[str, float]:
    """`whats_here` from parameters.yaml: the two radii, in metres."""
    global _radii
    if _radii is None or model_dir is not None:
        directory = model_dir or _model_dir()
        values = yaml.safe_load((directory / 'parameters.yaml').read_text())['whats_here']
        loaded = {'point_radius_m': float(values['point_radius_m']),
                  'line_radius_m': float(values['line_radius_m'])}
        if model_dir is None:
            _radii = loaded
        return loaded
    return _radii


def _model_dir() -> Path:
    from importer.run import MODEL
    return MODEL


def sql(categories: bool = False) -> str:
    return SQL.format(columns=', '.join(shape.RESULT_COLUMNS), objects='{objects}',
                      filter=CATEGORY_FILTER if categories else '')


def params(lon: float, lat: float, radius: float | None = None,
           categories: tuple[str, ...] = (), limit: int = 3 * PART_LIMIT) -> dict:
    """The bind parameters. `radius` overrides both configured radii.

    One override rather than two, because a caller who widens the search
    means "look further", not "look further for points but not for lines".
    """
    configured = radii()
    point_radius = radius if radius is not None else configured['point_radius_m']
    line_radius = radius if radius is not None else configured['line_radius_m']
    address_radius = max(point_radius, line_radius) * 2
    line_lon, line_lat = degrees_for(line_radius, lat)
    address_lon, address_lat = degrees_for(address_radius, lat)
    return {
        'lon': lon, 'lat': lat,
        'point_radius': point_radius,
        'line_radius': line_radius,
        'line_degrees_lon': line_lon,
        'line_degrees_lat': line_lat,
        'address_radius': address_radius,
        'address_degrees_lon': address_lon,
        'address_degrees_lat': address_lat,
        'part_limit': PART_LIMIT,
        'categories': list(categories),
        'limit': limit,
    }
