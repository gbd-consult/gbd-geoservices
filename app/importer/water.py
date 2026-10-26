"""The sea.

OSM has no ocean polygons, only `natural=coastline` ways; without these the
map ends at the shoreline with land-coloured water behind it. It is why
Schleswig-Holstein is the test area.

The polygons come from osmdata.openstreetmap.de, which derives closed
land/water polygons from the planet's coastline daily, in two resolutions:
the full set for osm_polygon and the _z12 band, the simplified set for the
_z6 and _z9 bands (DESIGN.md "Zoom bands"). Both are already EPSG:3857, so
nothing here projects anything.

They ship as split shapefiles and nothing else in the stack reads one, which
is why pyshp is a dependency: pure Python, no GDAL, no shelling out. The
full .shp is 1.27 GB, so the bbox filter matters -- pyshp reads each
record's header box and skips the geometry of everything that misses.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import shapefile
import shapely
from shapely.geometry import shape as shapely_shape

from importer import geometry as geom
from importer import tables as t
from importer.writer import TableWriter

log = logging.getLogger('importer')

FULL = 'water-polygons-split-3857'
SIMPLIFIED = 'simplified-water-polygons-split-3857'

#: The class the water polygons get. It has no classifier rule -- nothing in
#: OSM carries it -- and is styled as the first fill in the landcover layer.
OCEAN = 'cls_ocean'


def fetch(base_url: str, name: str, downloads: Path) -> Path:
    """Download and unpack once. Returns the .shp path.

    Unpacked rather than read through ZipFile: random access into a deflate
    stream is pathological, and the bbox filter is random access.
    """
    target = downloads / name
    shp = next(iter(sorted(target.glob('*.shp'))), None) if target.is_dir() else None
    if shp is not None:
        return shp

    archive = downloads / f'{name}.zip'
    if not archive.is_file():
        log.info('downloading %s', name)
        urlretrieve(f'{base_url.rstrip("/")}/{name}.zip', archive)  # noqa: S310
    log.info('unpacking %s', name)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(downloads)
    return next(iter(sorted((downloads / name).glob('*.shp'))))


def area_bbox(extract_box, margin_deg: float) -> tuple[float, float, float, float]:
    """The extract's bbox in 3857, widened so the clip seam falls off-area.

    `extract_box` is the osmium header box, in degrees.
    """
    import numpy as np
    corners = np.array([
        [extract_box.bottom_left.lon - margin_deg, extract_box.bottom_left.lat - margin_deg],
        [extract_box.top_right.lon + margin_deg, extract_box.top_right.lat + margin_deg],
    ], dtype=float)
    projected = geom.mercator(corners)
    return (projected[0][0], projected[0][1], projected[1][0], projected[1][1])


def _clipped_parts(shp: Path, bbox) -> list:
    """Every water polygon inside `bbox`, clipped to it."""
    box = shapely.box(*bbox)
    out = []
    with shapefile.Reader(str(shp)) as reader:
        for record in reader.iterShapes(bbox=bbox):
            if record is None:
                continue
            clipped = shapely.intersection(shapely_shape(record.__geo_interface__), box)
            if shapely.is_empty(clipped):
                continue
            out.extend(p for p in geom.polygon_parts(shapely.make_valid(clipped))
                       if shapely.get_type_id(p) == 3 and not shapely.is_empty(p))
    return out


def load(conn, schema: str, shp: Path, bbox, batch: int) -> int:
    """The full set into osm_polygon, as class `ocean` drawn from z0."""
    writer = TableWriter(conn, schema, t.OSM_POLYGON, batch)
    for part in _clipped_parts(shp, bbox):
        # No OSM id: the shapefile has none, and nothing joins to these.
        writer.add((0, OCEAN, None, None, 0, 0, None, part))
    return writer.close()


def load_bands(conn, schema: str, shp: Path, bbox, params, batch: int) -> dict[str, int]:
    """The simplified set into the bands that union.

    The union bands take their ocean from here rather than from osm_polygon:
    unioning the full-resolution coastline of a whole state at z6 would be
    both slow and pointless, which is why osmdata publishes two resolutions.
    _z12 is not in
    this list -- it is a plain copy of osm_polygon and gets the full set.
    """
    parts = _clipped_parts(shp, bbox)
    counts = {}
    for band in params.bands:
        if not band.union_cell_deg:
            continue
        table = t.band_table('osm_polygon', band.suffix)
        writer = TableWriter(conn, schema, table, batch)
        for part in parts:
            simplified = shapely.make_valid(
                shapely.simplify(part, band.tolerance_m, preserve_topology=True))
            for piece in geom.polygon_parts(simplified):
                if shapely.get_type_id(piece) == 3 and shapely.area(piece) > 0:
                    writer.add((0, OCEAN, None, None, 0, 0, None, piece))
        counts[table.name] = writer.close()
    return counts
