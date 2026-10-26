"""The SQL a Mapnik datasource runs, per layer and per band.

No hand-written SQL anywhere in the styles: a layer knows its classes and
its mode, and everything else follows from the schema the importer built.
What is *not* in these queries is the point of them -- no `!pixel_width!`,
no `way_area`, no `CASE`, no `COALESCE`. Those would be evaluated per row
per tile, and the importer precomputed all of them into
`minzoom`, `minzoom_label` and `z_order`.

Two things vary per tile and cannot be baked in:

* the **zoom**, which `minzoom <= z` needs. It comes from Mapnik's
  `!scale_denominator!` through one expression, so the same query serves
  every TileMatrixSet -- a UTM32 level maps to the 3857 zoom with the same
  metres per pixel.
* the **bbox**, which is `!bbox!`.

The only `CASE`s are the icon markers' importance floors -- which rows get
an icon, and which of those get their label -- step functions of the zoom
alone: `!scale_denominator!` is a literal by the time Postgres sees it, so
the planner folds each to a constant once per query, not per row.

The **band** does not vary per tile: it decides the table, so it is fixed
per `<Layer>`, and the generator must bound that layer's scale denominators
to the band's zoom range. If the two disagree, a tile at the edge of a band
reads one table with another band's threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Class names, table names and the schema all reach the SQL as text.
_SAFE_NAME = re.compile(r'\A[a-z][a-z0-9_]*\Z')

#: 3857 units per pixel at zoom 0, and the pixel size WMTS standardises on.
#: Together they turn a scale denominator back into a zoom.
UNITS_PER_PIXEL_Z0 = 156543.03392804097
STANDARDIZED_PIXEL_SIZE_M = 0.00028

#: Geometry tables that have bands, and the one that does not.
BANDED = ('osm_polygon', 'osm_line')

#: Modes whose layers read text, and therefore filter on minzoom_label.
TEXT_MODES = ('label', 'shield', 'number')

#: Modes that draw the `label` column only: a row without one draws nothing
#: and is not fetched.
LABEL_COLUMN_MODES = ('number',)

#: Which tables a mode may read. The *data* decides which of these actually
#: holds a given class, but the mode decides the candidates -- without this
#: a `fill` layer over landcover_wood also picks up the osm_label rows for
#: the same class and asks them for a `minzoom` column they do not have.
#:
#: `fill` spans three tables because in Mapnik terms it is the inner stroke
#: over a casing as much as it is a polygon fill: `roads_fill` is mode fill
#: over line classes. `label` reads osm_line as well because line labels are not in
#: osm_label -- Mapnik cannot place text along a point geometry, so they
#: are read from osm_line on its own minzoom_label. Contours and their
#: heights are in osm_contour (importer/tables.py says why).
TABLES_BY_MODE = {
    'fill': ('osm_polygon', 'osm_building', 'osm_line'),
    'line': ('osm_line', 'osm_contour'),
    'casing': ('osm_line',),
    'marker': ('osm_point',),
    'label': ('osm_label', 'osm_line', 'osm_contour'),
    'shield': ('osm_label', 'osm_line'),
    'number': ('osm_label',),
}


@dataclass(frozen=True)
class Source:
    """One Mapnik datasource: a table, a filter and an order."""
    table: str
    classes: tuple[str, ...]
    text: bool                     # selects name/label and filters on minzoom_label
    descending: bool               # label layers sort descending, drawn layers ascending
    min_zoom: int
    max_zoom: int
    icon: bool = False             # selects `icon`, the marker's file, and skips undrawn rows
    label_only: bool = False       # skips rows without a `label` (house number, ref)
    #: (importance, zoom) pairs, the detail's `symbols.icons`: a row is drawn
    #: from the zoom of the highest importance it reaches. Only read when `icon`.
    icon_zooms: tuple[tuple[int, int], ...] = ()
    #: The same for the icon's label, `symbols.labels`. Only read when `icon`.
    label_zooms: tuple[tuple[int, int], ...] = ()
    #: On osm_label: the classes whose label gives way to their icon from the
    #: zoom the icon starts at (`icon_zooms`), when the icon is drawn at all.
    yields: tuple[str, ...] = ()


def scale_denominator(zoom: float, metres_factor: float = 1.0) -> float:
    """The scale denominator Mapnik reports at this zoom.

    The generator uses it to bound a layer to its band.
    """
    return (UNITS_PER_PIXEL_Z0 * metres_factor / 2.0 ** zoom) / STANDARDIZED_PIXEL_SIZE_M


def zoom_expression(metres_factor: float = 1.0) -> str:
    """`!scale_denominator!` -> the EPSG:3857 zoom with the same pixel size.

    `metres_factor` converts the CRS's map units to 3857 units. For
    EPSG:3857 it is 1: the map units *are* 3857 units. For a true-metre
    CRS like EPSG:25832 it is cos(latitude) for the area's centre, because
    one ground metre is 1/cos(latitude) 3857 units there -- which is what
    "the same metres per pixel, latitude-corrected for the area" means.

    Rounded, not floored: at an exact zoom the arithmetic lands a hair
    either side of the integer, and flooring 11.999999 gives 11.
    """
    numerator = UNITS_PER_PIXEL_Z0 * metres_factor
    return (f'round(log(2, ({numerator} / '
            f'(!scale_denominator! * {STANDARDIZED_PIXEL_SIZE_M}))::numeric))::int')


def importance_floor(zooms, metres_factor: float = 1.0) -> str:
    """The lowest importance an icon, or its label, needs at this tile's zoom,
    as SQL.

    `zooms` maps importance to the zoom icons (or labels) of that importance
    start at. Checked by the style generator to be monotonic -- more
    important never later -- so at a zoom the floor is the smallest
    importance whose zoom has been reached. Above every entry's zoom range
    nothing is drawn: 101 is more than any importance.
    """
    zoom = zoom_expression(metres_factor)
    arms = ' '.join(f'when {zoom} >= {int(z)} then {int(importance)}'
                    for importance, z in sorted(zooms))
    return f'(case {arms} else 101 end)' if arms else '101'


def band_ranges(bands, zoom_max: int) -> list[tuple[str, int, int]]:
    """(suffix, min zoom, max zoom) for every band and the full table.

    One `<Layer>` per entry, because the table is what changes.
    """
    out = []
    low = 0
    for band in bands:
        out.append((band.suffix, low, band.zoom_max))
        low = band.zoom_max + 1
    out.append(('', low, zoom_max))
    return out


def sources(layer_classes, present, bands, zoom_max: int, *, mode: str) -> list[Source]:
    """Every datasource one `layers.yaml` entry needs.

    A layer's classes routinely span several tables -- on a real import the
    marker layer has classes in the point, line and polygon tables at once
    -- so one entry becomes several `<Layer>`s. Which of the tables a mode
    may read actually holds a given class is asked of the data
    (`lib.db.table_classes`), not guessed: the mode alone does not decide
    the table (DESIGN.md "Style files").
    """
    text = mode in TEXT_MODES
    out = []
    for base in TABLES_BY_MODE[mode]:
        classes_present = present.get(base)
        if not classes_present:
            continue
        matching = tuple(sorted(set(layer_classes) & set(classes_present)))
        if not matching:
            continue
        ranges = (band_ranges(bands, zoom_max) if base in BANDED
                  else [('', 0, zoom_max)])
        for suffix, low, high in ranges:
            out.append(Source(table=base + suffix, classes=matching, text=text,
                              label_only=mode in LABEL_COLUMN_MODES,
                              icon=mode == 'marker',
                              descending=text, min_zoom=low, max_zoom=high))
    return out


def check_name(value: str) -> str:
    """Refuse anything that is not a plain identifier.

    These names are interpolated into SQL, because a Mapnik datasource
    takes its query as a string in an XML file and there is nowhere to bind
    a parameter. They come from the model, not from a request, so this is a
    guard against a typo in a YAML file rather than against an attacker.
    """
    if not value or not _SAFE_NAME.match(value):
        raise ValueError(f'not a plain identifier: {value!r}')
    return value


def sql(schema: str, source: Source, metres_factor: float = 1.0) -> str:
    """The datasource query, as Mapnik's `table` parameter.

    `!bbox!` goes *inside* the subquery on purpose. Mapnik appends its own
    bbox clause when the token is absent, which would filter after the
    subquery had already produced every row of the class at that zoom --
    a whole-table scan per tile. Inside, the GiST index does the work.

    `ORDER BY` inside a subquery is preserved by Postgres for a plain
    wrapping like Mapnik's, but it is not guaranteed by the standard; the
    draw order within a layer depends on it. If it ever stops holding, the
    symptom is a minor road drawn over a motorway, not an error.
    """
    check_name(schema)
    check_name(source.table)
    if source.text:
        columns = 'class, name, label, geom'
    elif source.icon:
        # `name` for the shield: an icon's label is drawn with it or not at
        # all. Below the label's floor it is NULL, and the generator's rule
        # for a row without a name draws the bare icon.
        label_floor = importance_floor(source.label_zooms, metres_factor)
        columns = f'class, icon, case when importance >= {label_floor} then name end as name, geom'
    else:
        columns = 'class, geom'
    zoom = zoom_expression(metres_factor)
    if source.icon:
        # A category that is not drawn has no icon (renderer/icons.py) and
        # gets no marker of any kind: it is not fetched at all. When the rest
        # is, is the row's importance's, not the class's minzoom.
        condition = (f'icon is not null'
                     f' and importance >= {importance_floor(source.icon_zooms, metres_factor)}')
    elif source.text:
        # minzoom_label may be NULL, meaning the object carries no text at all.
        condition = f'minzoom_label is not null and minzoom_label <= {zoom}'
        if source.label_only:
            condition += ' and label is not null'
        if source.yields:
            # An airport, a hospital: named by the area's label until its
            # icon appears, then by the icon's -- never both. A category with
            # no icon keeps its label.
            yielding = ', '.join(f"'{check_name(c)}'" for c in source.yields)
            icon_floor = importance_floor(source.icon_zooms, metres_factor)
            condition += (f' and (class not in ({yielding}) or icon is null'
                          f' or importance < {icon_floor})')
    else:
        condition = f'minzoom <= {zoom}'
    order = 'desc' if source.descending else 'asc'
    # Markers do not overlap: the first one placed keeps its spot, so the
    # more important POI has to be drawn first -- and of two equally
    # important ones the named: a school mapped twice, its named grounds
    # around an unnamed part, showed the unnamed icon, which never gets a
    # label. `name is null` is an expression, so it reads the table's name,
    # not the label-floor `name` of the select list.
    ordering = (f'importance desc, name is null, z_order {order}' if source.icon
                else f'z_order {order}')
    classes = ', '.join(f"'{check_name(c)}'" for c in source.classes)
    return (
        f'(select {columns} from {schema}.{source.table}'
        f' where class in ({classes})'
        f' and {condition}'
        f' and geom && !bbox!'
        f' order by {ordering}) as t'
    )
