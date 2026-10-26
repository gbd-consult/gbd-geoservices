"""TileMatrixSets: the configured tile grids.

There is one quadtree builder and a
declaration per grid in `styles/grids.yaml`, keyed by the identifier WMTS
advertises, so adding a grid is five values in a file rather than a
function in code. The `serve_grids` option is the list that decides what
is advertised, rendered and pre-cached.

Declared rather than derived. Deriving the grid from the CRS's area of use
is not possible from this image: there is
no pyproj, no projinfo and no proj.db, and `spatial_ref_sys.srtext` is
WKT1, which carries no bounds. The alternative -- deriving the grid from
the imported extent -- is computable but would move every tile address the
moment a larger area is imported, silently invalidating every cached tile
and every URL a client has stored. A grid is a public addressing scheme,
so it is declared and it does not move.

Level numbering here is the *grid's* own, and is not the zoom the
`minzoom` columns are written in. A DE_EPSG_25832_ADV level 8 and a Web Mercator z8
are different scales. `metres_factor` is what connects them: the datasource
query converts a level's scale denominator into the equivalent EPSG:3857
zoom, which is what `minzoom <= z` is compared against.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from renderer.queries import STANDARDIZED_PIXEL_SIZE_M

TILE_SIZE = 256

GRIDS_PATH = Path(__file__).resolve().parent.parent / 'styles' / 'grids.yaml'

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class TileMatrix:
    """One level of a set.

    `identifier` is what GetCapabilities advertises, zero-padded where the
    grid declares `level_digits`. A request sends the level as a number, so
    `08` and `8` address the same matrix.
    """
    identifier: str
    scale_denominator: float
    top_left: tuple[float, float]
    matrix_width: int
    matrix_height: int
    tile_width: int = TILE_SIZE
    tile_height: int = TILE_SIZE


@dataclass(frozen=True)
class TileMatrixSet:
    identifier: str
    crs: str
    origin: tuple[float, float]
    span: float
    centre_lat: float
    matrices: dict[str, TileMatrix] = field(default_factory=dict)

    @property
    def metres_factor(self) -> float:
        """This CRS's units expressed as Web Mercator units.

        One ground metre is 1/cos(lat) Web Mercator units, so a true-metre
        CRS compares at cos(lat). EPSG:3857 declares a latitude of 0 and
        so gets 1, which is right at every latitude: its units already are
        Web Mercator units.
        """
        return math.cos(math.radians(self.centre_lat))

    @property
    def levels(self) -> int:
        return len(self.matrices)

    def matrix(self, identifier: str) -> TileMatrix:
        try:
            return self.matrices[str(identifier)]
        except KeyError:
            raise ValueError(
                f'unknown TileMatrix {identifier!r} in {self.identifier!r}; '
                f'levels 0-{self.levels - 1}') from None

    def tile_span(self, level: int) -> float:
        return self.span / 2 ** level

    def bbox(self, level: int, col: int, row: int) -> BBox:
        """Level/col/row -> bbox in this CRS. Rows count down from the top."""
        matrix = self.matrix(level)
        if not (0 <= col < matrix.matrix_width and 0 <= row < matrix.matrix_height):
            raise ValueError(
                f'tile {level}/{col}/{row} is outside {self.identifier!r}: '
                f'{matrix.matrix_width}x{matrix.matrix_height} at this level')
        size = self.tile_span(int(level))
        left = self.origin[0] + col * size
        top = self.origin[1] - row * size
        return (left, top - size, left + size, top)

    def tile_for(self, level: int, x: float, y: float) -> tuple[int, int]:
        """The (col, row) containing a point. The inverse of `bbox`.

        What the pre-cache walks an extent with, and what turns a click
        into a tile address.
        """
        matrix = self.matrix(level)
        size = self.tile_span(int(level))
        col = int(math.floor((x - self.origin[0]) / size))
        row = int(math.floor((self.origin[1] - y) / size))
        # A point exactly on the far edge belongs to the last tile, not to
        # one past it.
        col = min(col, matrix.matrix_width - 1)
        row = min(row, matrix.matrix_height - 1)
        if not (0 <= col < matrix.matrix_width and 0 <= row < matrix.matrix_height):
            raise ValueError(f'({x}, {y}) is outside {self.identifier!r}')
        return col, row

    def tiles_in(self, level: int, bbox: BBox):
        """Every (col, row) at this level covering a bbox, clipped to the grid."""
        matrix = self.matrix(level)
        left, bottom, right, top = bbox
        size = self.tile_span(int(level))
        first_col = max(0, int(math.floor((left - self.origin[0]) / size)))
        last_col = min(matrix.matrix_width - 1,
                       int(math.floor((right - self.origin[0]) / size)))
        first_row = max(0, int(math.floor((self.origin[1] - top) / size)))
        last_row = min(matrix.matrix_height - 1,
                       int(math.floor((self.origin[1] - bottom) / size)))
        for row in range(first_row, last_row + 1):
            for col in range(first_col, last_col + 1):
                yield col, row

    def resolution(self, level: int) -> float:
        """CRS units per pixel at this level."""
        return self.tile_span(level) / TILE_SIZE


def quadtree(identifier: str, crs: str, origin, span: float, levels: int,
             centre_lat: float, level_digits: int = 1) -> TileMatrixSet:
    """A quadtree set: one tile at level 0, doubling each level.

    The scale denominator follows from the resolution and the OGC
    standardized pixel size -- the same scheme the OGC well-known
    GoogleMapsCompatible set uses, which is why EPSG:3857 comes out of this
    builder identical to it rather than being special-cased.
    """
    matrices = {}
    for level in range(levels):
        side = 2 ** level
        matrices[str(level)] = TileMatrix(
            identifier=str(level).zfill(level_digits),
            scale_denominator=(span / side / TILE_SIZE) / STANDARDIZED_PIXEL_SIZE_M,
            top_left=(float(origin[0]), float(origin[1])),
            matrix_width=side,
            matrix_height=side,
        )
    return TileMatrixSet(identifier=identifier, crs=crs,
                         origin=(float(origin[0]), float(origin[1])),
                         span=float(span), centre_lat=float(centre_lat),
                         matrices=matrices)


def from_config(identifier: str, grid: dict) -> TileMatrixSet:
    missing = {'crs', 'origin', 'span', 'levels', 'centre_lat'} - set(grid)
    if missing:
        raise ValueError(f'grid {identifier!r} is missing {", ".join(sorted(missing))}')
    return quadtree(identifier, grid['crs'], grid['origin'], grid['span'],
                    int(grid['levels']), grid['centre_lat'],
                    int(grid.get('level_digits', 1)))


def load(grid_ids=None, grids=None) -> dict[str, TileMatrixSet]:
    """Every served grid, keyed by its identifier.

    A grid in `serve_grids` with no entry in `grids.yaml` is refused rather
    than skipped: it would otherwise be advertised in GetCapabilities and
    then 404 on every tile.
    """
    from lib import config

    grid_ids = grid_ids if grid_ids is not None else (config.opt('serve_grids') or [])
    grids = grids if grids is not None else (yaml.safe_load(GRIDS_PATH.read_text()) or {})

    out = {}
    for identifier in grid_ids:
        if identifier not in grids:
            raise ValueError(
                f'{identifier} is in `serve_grids` but has no entry in grids.yaml; '
                f'it would be advertised and then 404 on every tile')
        out[identifier] = from_config(identifier, grids[identifier])
    return out


def by_crs(sets: dict[str, TileMatrixSet], crs: str) -> TileMatrixSet | None:
    """The served grid in one CRS, or None. What `/xyz` and the tools that
    want "the Web Mercator grid" ask for, whatever a deployment calls it."""
    return next((tms for tms in sets.values() if tms.crs == crs), None)
