"""Geometry: osmium's WKB in, hex EWKB out, projected on the way.

osmium's WKBFactory emits plain WKB in EPSG:4326 -- its `epsg` attribute is
not settable, so it cannot be asked for 3857, and the output carries no SRID
flag, so it cannot go straight into a typed geometry column either. Both are
answered by parsing once with shapely and serialising twice: the render
tables get the projected geometry, the search tables the unprojected one.

EPSG:3857 is *defined* as the spherical Mercator formula on a sphere of
radius 6378137 -- no datum shift, no grid file, nothing to iterate -- so
pyproj would add a dependency and a per-point Python/C boundary and nothing
else. numpy arrives with shapely anyway, and one vectorised callback over a
whole batch is what makes this affordable: shapely.transform hands the
callback every coordinate of every geometry in one array (measured: 2.6 us
per geometry against 20 us calling it per geometry).
"""

from __future__ import annotations

import numpy as np
import shapely

#: The sphere EPSG:3857 is defined on, and the latitude where it is cut off
#: to keep the map square. Beyond it log(tan(...)) runs away to infinity,
#: and a node at the pole is not hypothetical in OSM data.
EARTH_RADIUS = 6378137.0
LAT_MAX = 85.05112877980659

#: 3857 units per pixel at zoom 0. The same constant parameters.yaml uses.
UNITS_PER_PIXEL_Z0 = 156543.0


def mercator(coords: np.ndarray) -> np.ndarray:
    """(n, 2) lon/lat degrees -> (n, 2) EPSG:3857 units."""
    lon = coords[:, 0]
    lat = np.clip(coords[:, 1], -LAT_MAX, LAT_MAX)
    return np.column_stack((
        np.radians(lon) * EARTH_RADIUS,
        np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * EARTH_RADIUS,
    ))


def to_3857(geometries):
    """Project a batch of 4326 geometries. One callback for the whole batch."""
    return shapely.transform(np.asarray(geometries, dtype=object), mercator)


def from_wkb(values):
    """Parse a batch of osmium's hex WKB."""
    return shapely.from_wkb(np.asarray(values, dtype=object))


def hex_ewkb(geometries, srid: int):
    """Serialise a batch for COPY: hex EWKB, which PostGIS reads directly."""
    tagged = shapely.set_srid(np.asarray(geometries, dtype=object), srid)
    return shapely.to_wkb(tagged, hex=True, include_srid=True)


def label_anchor(geometry):
    """Where the object's text goes.

    The point itself; point-on-surface for an area, which unlike the
    centroid is guaranteed to lie inside a horseshoe-shaped one; the
    midpoint *along* a line, which is not the centre of its bounding box.
    """
    kind = shapely.get_type_id(geometry)
    if kind == 0:                                  # Point
        return geometry
    if kind in (1, 5):                             # LineString, MultiLineString
        return shapely.line_interpolate_point(geometry, 0.5, normalized=True)
    return shapely.point_on_surface(geometry)


def polygon_parts(geometry):
    """A (Multi)Polygon as the Polygon rows the table is typed for.

    osm_polygon's column is typed `Polygon`, so an area with several
    outer rings becomes several rows. They share one osm_id, and their
    minzoom is computed from the whole area rather than per part, so a
    scattered nature reserve does not appear ring by ring as you zoom.
    """
    if shapely.get_type_id(geometry) == 3:         # Polygon
        return [geometry]
    return list(shapely.get_parts(geometry))
