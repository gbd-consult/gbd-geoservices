"""The numbers the importer, the renderer and the search agree on.

`model/parameters.yaml` is the value of record; this reads it, plus the two
style files the importer needs -- `styles/classes.yaml` for the zooms at
which a class starts being drawn and carrying text, and `styles/layers.yaml`
for the class sets the partial indexes are built from.

Sizes are measured on the *projected* geometry, in EPSG:3857 units. That is
not an approximation waiting to be corrected: a Web Mercator pixel at zoom
z is 156543 / 2^z 3857 units, so 3857 area is exactly the quantity the
pixel threshold is about, and it is what decides whether a shape is visible
in a tile. Ground metres would make the same object appear a zoom later in
Flensburg than in Hamburg.
"""

from __future__ import annotations

import fnmatch
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from renderer import resolve
from renderer.resolve import Styles


@dataclass(frozen=True)
class Band:
    suffix: str
    zoom_max: int
    tolerance_m: float
    union_cell_deg: float


@dataclass(frozen=True)
class Contours:
    """`contours` in parameters.yaml: how manage.py init-elevation draws the
    lines, and how much the import copies (importer/elevation.py)."""
    levels_m: tuple[int, ...]
    cell_m: float
    min_ring_m: float
    simplify_m: float
    subdivide_vertices: int
    bbox_margin_deg: float


class Params:
    def __init__(self, values: dict, layers: list[dict], styles: Styles):
        self._layers = layers
        #: {class: zoom} for every class drawn in a geometry mode, from
        #: `styles/classes.yaml`. The band builds select lines by it.
        self.class_minzoom = {cls: zoom for cls in styles.classes
                              if (zoom := styles.start(cls)) is not None}
        self._label_minzoom = {cls: zoom for cls in styles.classes
                               if (zoom := styles.text_start(cls)) is not None}
        self._marker_classes = frozenset(cls for cls in styles.classes
                                         if resolve.MARKER_MODE in styles.modes(cls))
        #: Every class `styles/classes.yaml` mentions, in any mode. What
        #: `run.check_class_drift` compares the rules against.
        self.styled_classes = styles.classes

        size = values['size']
        self.polygon_px2 = float(size['polygon_px2'])
        self.building_px2 = float(size['building_px2'])
        self.polygon_label_px2 = float(size['polygon_label_px2'])
        self.line_label_px = float(size['line_label_px'])
        self.zoom_min = int(size['zoom_min'])
        self.zoom_max = int(size['zoom_max'])

        self.bands = tuple(Band(b['suffix'], int(b['zoom_max']), float(b['tolerance_m']),
                                float(b['union_cell_deg'])) for b in values['bands'])

        z = values['z_order']
        self._layer_min = int(z['layer_tag_min'])
        self._layer_max = int(z['layer_tag_max'])
        self._rank = dict(z['rank'])
        self._rank_default = self._rank.pop('default', 0)
        # Longest first, so road_primary_bridge finds road_primary and not road.
        self._rank_prefixes = sorted(self._rank, key=len, reverse=True)
        self._rank_cache: dict[str, int] = {}

        self.level_height_m = float(values['buildings']['level_height_m'])
        self.default_height_m = float(values['buildings']['default_height_m'])
        places = values['places']
        self.place_levels = tuple(int(level) for level in places['levels'])
        self.place_categories = tuple(places['categories'])
        self.place_subdivide_vertices = int(places['subdivide_vertices'])
        self.place_area_share = float(places['area_share'])
        self.merge_classes = tuple(values['search']['merge_classes'])
        self.polygon_simplify_m = float(values['search']['polygon_simplify_m'])
        self.water_bbox_margin_deg = float(values['water']['bbox_margin_deg'])
        contours = dict(values['contours'])
        self.contours = Contours(
            levels_m=tuple(int(m) for m in contours.pop('levels_m')),
            subdivide_vertices=int(contours.pop('subdivide_vertices')),
            **{k: float(v) for k, v in contours.items()})
        self.copy_batch = int(values['import']['copy_batch'])
        self.index_workers = int(values['import']['index_workers'])
        self.progress_s = float(values['import']['progress_s'])
        self.location_store = str(values['import']['location_store'])
        self.report_change_pct = float(values['import']['report_change_pct'])
        self.report_min_rows = int(values['import']['report_min_rows'])

    # --- zooms ----------------------------------------------------------

    def _clamp(self, zoom: float) -> int:
        return max(self.zoom_min, min(self.zoom_max, int(zoom)))

    def size_minzoom_area(self, area: float, px2: float) -> int:
        """First zoom at which `area` (3857 units²) covers `px2` pixels."""
        if area <= 0:
            return self.zoom_max
        return self._clamp(math.ceil(math.log2(156543.0 * math.sqrt(px2 / area))))

    def size_minzoom_length(self, length: float, px: float) -> int:
        """First zoom at which `length` (3857 units) is `px` pixels long."""
        if length <= 0:
            return self.zoom_max
        return self._clamp(math.ceil(math.log2(156543.0 * px / length)))

    def draw_px2(self, cls: str | None, min_px: float | None) -> float:
        """The area threshold for a polygon.

        `min_px` on a rule wins where it is set; no generated rule sets one
        today, so in practice this keys on the class -- buildings are drawn
        from 1 px² and everything else from 4.
        """
        if min_px is not None:
            return float(min_px)
        return self.building_px2 if cls == 'cls_building' else self.polygon_px2

    def minzoom(self, cls: str | None) -> int:
        """Lowest zoom at which the style draws this class's geometry.

        A class it never draws that way -- a POI, a place -- gets zoom_max,
        which keeps its rows out of every band table and every `minzoom <= z`
        query. Its marker and its text do not read this column.
        """
        return self.class_minzoom.get(cls, self.zoom_max)

    def label_minzoom(self, cls: str) -> int | None:
        """Lowest zoom at which the style gives this class text, or None."""
        return self._label_minzoom.get(cls)

    def style_zooms(self) -> dict[str, tuple[int | None, int | None]]:
        """{class: (minzoom, label minzoom)} as this import writes them, for
        `import_meta`: the style run refuses a style that starts a class
        earlier than its rows."""
        return {cls: (self.class_minzoom.get(cls), self._label_minzoom.get(cls))
                for cls in sorted(self.styled_classes)}

    def draws_marker(self, cls: str | None) -> bool:
        """Whether the style puts a dot on this class.

        A POI is often mapped as its outline rather than as a node -- a
        restaurant as its building, a school as its grounds -- and on a
        real import 53 of the marker layer's classes exist *only* in
        osm_polygon. `marker` mode reads osm_point, so without a point row
        those objects get no dot at all. The importer writes one, because
        it already has the anchor: computing it per tile instead is exactly
        the work the precomputed design exists to remove.
        """
        return cls in self._marker_classes

    # --- draw order -----------------------------------------------------

    def rank(self, cls: str) -> int:
        cached = self._rank_cache.get(cls)
        if cached is None:
            cached = self._rank_cache[cls] = self._rank_for(cls)
        return cached

    def _rank_for(self, cls: str) -> int:
        if cls in self._rank:
            return self._rank[cls]
        for prefix in self._rank_prefixes:
            if cls.startswith(prefix):
                return self._rank[prefix]
        return self._rank_default

    def z_order(self, cls: str, tags: Mapping[str, str]) -> int:
        """Draw order within a layer.

        For places the column carries the population instead, so that the
        larger place wins the label collision test (DESIGN.md "Draw order").
        The column therefore means two different things depending on the
        class; places and POIs are separate Mapnik layers with separate
        queries, so they never sort against each other.
        """
        if cls.startswith('cls_place_'):
            return _int_or(tags.get('population'), 0)
        layer = max(self._layer_min, min(self._layer_max, _int_or(tags.get('layer'), 0)))
        return layer * 1000 + self.rank(cls)

    # --- buildings ------------------------------------------------------

    def building_height(self, tags: Mapping[str, str]) -> tuple[float, str]:
        metres = _float_or(_strip_unit(tags.get('height')), None)
        if metres is not None and metres > 0:
            return metres, 'tag'
        levels = _float_or(tags.get('building:levels'), None)
        if levels is not None and levels > 0:
            return levels * self.level_height_m, 'levels'
        return self.default_height_m, 'est'

    # --- class sets -----------------------------------------------------

    def is_merge_class(self, cls: str) -> bool:
        return any(fnmatch.fnmatchcase(cls, pattern) for pattern in self.merge_classes)

    def layer_class_sets(self, known: set[str]) -> list[tuple[str, frozenset[str]]]:
        """Each layer of styles/layers.yaml with its globs expanded.

        Used to build one partial GiST index per layer. Which table the
        index lands on is decided from the classes actually present in each
        table, not from the layer's mode -- `roads_fill` has mode `fill`
        over line classes, and `buildings` has mode `fill` but belongs to
        osm_building.
        """
        out = []
        for layer in self._layers:
            classes = {cls for pattern in layer['classes']
                       for cls in fnmatch.filter(known, pattern)}
            if layer['mode'] == resolve.MARKER_MODE:
                # The marker layer lists `*` and draws what has a marker
                # entry; its index covers those, not every class there is.
                classes &= self._marker_classes
            out.append((layer.get('name') or layer['mode'], frozenset(classes)))
        return out


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strip_unit(value: str | None) -> str | None:
    """'12', '12 m', '12.5m' -> the number. Anything else is left to fail."""
    if value is None:
        return None
    return value.strip().removesuffix('m').strip()


def load(model_dir: Path, styles_dir: Path) -> Params:
    return Params(
        yaml.safe_load((model_dir / 'parameters.yaml').read_text()),
        yaml.safe_load((styles_dir / 'layers.yaml').read_text()),
        resolve.load(styles_dir),
    )
