"""Tile format spellings, normalised once.

XYZ URLs carry a short
extension (`.png`); WMTS's `FORMAT` parameter is conventionally a full MIME
type (`image/png`). Both have to hand the *same* canonical short string to
the renderer and set the same kind of `Content-Type`, so the normalisation
lives here rather than twice.
"""

from __future__ import annotations

#: Every accepted spelling -> its one canonical short form.
CANONICAL: dict[str, str] = {
    'png': 'png',
    'image/png': 'png',
    'jpg': 'jpg',
    'jpeg': 'jpg',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'pbf': 'pbf',
    'mvt': 'pbf',
    'application/x-protobuf': 'pbf',
    'application/vnd.mapbox-vector-tile': 'pbf',
}

#: `pbf` sends the registered vector-tile type; `application/x-protobuf`
#: stays an accepted *input* spelling for clients that still send it.
MIME: dict[str, str] = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'pbf': 'application/vnd.mapbox-vector-tile',
}

#: What `mapnik.Image` encodes, in the order a UI should offer them.
RASTER: tuple[str, ...] = ('png', 'jpg')

#: Built offline into a PMTiles archive and sliced out per request; never
#: reaches Mapnik.
VECTOR: tuple[str, ...] = ('pbf',)

#: What a client may legitimately ask for, whichever pipeline answers.
#: Separate from RASTER because "may I request it" and "can Mapnik encode
#: it" stopped having the same answer once vector tiles existed.
SERVABLE: tuple[str, ...] = RASTER + VECTOR


def normalize(value: str) -> str:
    """A short extension or MIME type in any accepted spelling -> canonical.

    An unrecognised value passes through lower-cased (a MIME type stripped
    to its subtype) rather than raising: deciding whether a format is
    *servable* is the route's job, and it wants to name the offender.
    """
    value = value.strip().lower()
    if value in CANONICAL:
        return CANONICAL[value]
    if '/' in value:
        return value.split('/', 1)[-1]
    return value


def mime_for(fmt: str) -> str:
    return MIME.get(fmt.lower(), 'application/octet-stream')
