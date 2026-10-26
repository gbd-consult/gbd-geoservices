"""What a place is, and how far a place without a border reaches.

"Kiel" is both a `place=city` node and an `admin_level=6` relation: the
boundary row carries the polygon, a village node only its centre. The
phrase mode (search/phrase.py `PLACE_LOOKUP`) reads a place name as all the
places called that; the ones with a border are tested by the address path
or their polygon, the ones without by their centre plus a radius by place
rank -- city 10 km, town 5, village 2, hamlet 1 (`place_radius_km` in
`parameters.yaml`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

#: What counts as a place: a `place=*` object of any kind, or an
#: administrative area (the assembled boundary relation). The area rows
#: carry no class -- their classifier rules are search-only, restricted to
#: polygons, while the border lines are drawn -- so they are found by category.
PLACE_CATEGORIES = ('cat_geography_places', 'cat_geography_admin')

_radii: dict[str, float] | None = None


def radii(model_dir: Path | None = None) -> dict[str, float]:
    """`place_radius_km` as metres, keyed by the `cls_place_*` class."""
    global _radii
    if _radii is None or model_dir is not None:
        directory = model_dir or _model_dir()
        values = yaml.safe_load((directory / 'parameters.yaml').read_text())['place_radius_km']
        loaded = {f'cls_place_{key}': float(km) * 1000.0 for key, km in values.items()}
        if model_dir is None:
            _radii = loaded
        return loaded
    return _radii


def _model_dir() -> Path:
    from importer.run import MODEL
    return MODEL


def radius_for(cls: str | None) -> float:
    """The radius for a place with no polygon.

    An unranked place -- `cls_place_other`, or a boundary row with no class --
    falls back to the smallest, because guessing large on a place nobody
    ranked means sweeping in a whole region's restaurants and calling them
    that place's.
    """
    table = radii()
    if cls and cls in table:
        return table[cls]
    return min(table.values())
