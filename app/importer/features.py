"""Tags plus geometry plus a classification, turned into table rows.

Everything here is a pure function of its arguments -- no database, no
osmium, no configuration beyond the Params object -- which is what makes
the arithmetic of DESIGN.md "Sizes and zooms" testable without an extract.

Row builders return tuples in `tables.copy_names(...)` order. That coupling
is deliberate and is what the width check in the writer and the column test
in the suite between them pin down.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import shapely

from importer import geometry as geom
from importer.params import Params
from importer.rules import Result
from lib import text


def label_value(tags: Mapping[str, str]) -> str | None:
    """The secondary label: a road's ref, a house number, an elevation.

    Which classes actually draw it is the style's business -- a motorway
    shield reads this column, a building label may not -- so this only has
    to find the one piece of text that is not the name.
    """
    return tags.get('ref') or tags.get('addr:housenumber') or tags.get('ele')


def minzooms(result: Result, params: Params, geometry, kind: str,
             has_text: bool) -> tuple[int, int | None]:
    """(minzoom, minzoom_label) for an object, both clamped to 0-21 (size.zoom_min, zoom_max).

    The class's zooms are the style's (`Params.minzoom`, `label_minzoom`).
    For an area, minzoom is the larger of the class's own zoom and the zoom
    at which the geometry first covers the pixel threshold. **A line has no
    size test for drawing**: its minzoom is its class's. OSM cuts a road at
    every junction and bridge, so a way's own length says nothing about the
    road it is part of, and testing each way hid 4 581 of `de_sh`'s 6 611
    primary-road segments at z10-12 -- main roads drawn as dashes. That is
    osm-carto's rule too: roads by class, sizes for areas.

    minzoom_label keeps the size test for lines as well as areas, against
    the stricter label threshold, because a label is placed on one way's
    geometry and has to fit on it. It is NULL when the style never gives the
    class text or the object has none to give.
    """
    class_minzoom = params.minzoom(result.cls)

    if kind == 'point':
        size_minzoom = size_label_minzoom = params.zoom_min
    elif kind == 'line':
        size_minzoom = params.zoom_min
        size_label_minzoom = params.size_minzoom_length(
            shapely.length(geometry), params.line_label_px)
    else:
        area = shapely.area(geometry)
        size_minzoom = params.size_minzoom_area(area, params.draw_px2(result.cls, result.min_px))
        size_label_minzoom = params.size_minzoom_area(area, params.polygon_label_px2)

    minzoom = max(class_minzoom, size_minzoom)

    class_label_minzoom = params.label_minzoom(result.cls) if result.cls else None
    if class_label_minzoom is None or not has_text:
        return minzoom, None
    return minzoom, max(class_label_minzoom, size_label_minzoom)


def render_row(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
               geometry, kind: str) -> tuple:
    """A row for osm_point / osm_line / osm_polygon."""
    name = tags.get('name')
    label = label_value(tags)
    minzoom, minzoom_label = minzooms(result, params, geometry, kind, bool(name or label))
    return (osm_id, result.cls, name, label, params.z_order(result.cls, tags),
            minzoom, minzoom_label, geometry)


def point_row(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
              geometry) -> tuple:
    """A row for osm_point: the render columns plus `category`, `icon` (set later,
    by the style run) and `importance`."""
    row = render_row(osm_id, result, params, tags, geometry, 'point')
    return (*row[:-1], result.category, None, result.importance, row[-1])


def building_rows(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
                  geometry) -> list[tuple]:
    """Rows for osm_building: the render columns plus the height estimate.

    Exploded like any other area -- the column is typed `Polygon`, and a
    building mapped as a multipolygon (a block with a courtyard split into
    parts) would otherwise be rejected by the column type.
    """
    row = render_row(osm_id, result, params, tags, geometry, 'polygon')
    height, source = params.building_height(tags)
    return [(*row[:-1], height, source, part) for part in geom.polygon_parts(geometry)]


def marker_row(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
               anchor) -> tuple:
    """An osm_point row for an object that was not mapped as a point.

    A POI is often drawn as its outline -- a restaurant as its building, a
    school as its grounds -- and `marker` mode reads osm_point. Without
    this the dot is simply missing for every such object.

    `minzoom` is the *class* minzoom, not the object's size-limited one --
    what the same object mapped as a node would get. The marker query does
    not read it: an icon starts where its importance and the detail say.
    `minzoom_label` is NULL because the object's label already comes from
    its own osm_label row; a second one would label it twice.
    """
    minzoom = params.minzoom(result.cls)
    return (osm_id, result.cls, tags.get('name'), label_value(tags),
            params.z_order(result.cls, tags), minzoom, None, result.category, None,
            result.importance, anchor)


def label_row(render: tuple, result: Result, anchor) -> tuple | None:
    """A row for osm_label, or None when the object carries no text.

    Point-placed labels only. A line's text is drawn from osm_line with
    `placement: line`, which Mapnik cannot do on a point geometry, so line
    labels and shields never come through here. `icon` is left to the style
    run.
    """
    osm_id, cls, name, label, z_order, _minzoom, minzoom_label, *_rest = render
    if minzoom_label is None or not (name or label):
        return None
    return (osm_id, cls, name, label, z_order, minzoom_label, result.category, None,
            result.importance, anchor)


#: Degrees per metre, near enough for a 5 m simplification tolerance applied
#: to a 4326 geometry. The search geometry is a highlight, not a measurement.
DEGREES_PER_METRE = 1.0 / 111_320.0


def join_unique(*parts: str | None) -> str:
    """Normalized parts joined once each, in order.

    search_text is compared with trigram similarity, so a word repeated
    because the name and the street share it would weight that word twice.
    """
    out: list[str] = []
    for part in parts:
        for word in text.normalize(part).split(' '):
            if word and word not in out:
                out.append(word)
    return ' '.join(out)


def as_multi(geometry):
    """Wrap a single geometry so one object is always one row."""
    kind = shapely.get_type_id(geometry)
    if kind == 1:
        return shapely.multilinestrings([geometry])
    if kind == 3:
        return shapely.multipolygons([geometry])
    return geometry


def search_row(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
               geometry, kind: str, centre) -> tuple:
    """An osm_search_object row, in 4326.

    Only named objects get one (plus merged streets, which post-processing
    builds), so `name` is never NULL here.
    """
    name = tags.get('name')
    street = tags.get('addr:street')
    housenumber = tags.get('addr:housenumber')
    postcode = tags.get('addr:postcode')
    city = tags.get('addr:city')

    point = line = polygon = None
    if kind == 'point':
        point = geometry
    elif kind == 'line':
        line = as_multi(geometry)
    else:
        polygon = as_multi(shapely.simplify(
            geometry, params.polygon_simplify_m * DEGREES_PER_METRE))

    return (
        [osm_id], name, text.expand_street(name),
        join_unique(name, street, housenumber, postcode, city),
        text.phonetic(name), text.normalize(city),
        list(result.categories), result.category, result.importance, result.cls,
        street, housenumber, postcode, city,
        point, line, polygon, centre,
        json.dumps(dict(tags), ensure_ascii=False), None,
    )


def address_row(osm_id: int, tags: Mapping[str, str], centre, category: str | None) -> tuple:
    """An osm_search_address row, in 4326.

    id_object and id_places are resolved in post-processing; osm_id is what
    makes the first of them resolvable at all. `category` is the carrier's.
    """
    street = tags.get('addr:street')
    housenumber = tags.get('addr:housenumber')
    parsed = text.extract_housenumber(housenumber)
    number, number_part = parsed if parsed else (None, None)
    search_street = text.expand_street(street)
    return (
        osm_id, street, search_street, text.phonetic(search_street),
        tags.get('addr:postcode'), tags.get('addr:city'), housenumber,
        number, number_part, centre, None, None, category,
    )


def street_ends_row(osm_id: int, result: Result, tags: Mapping[str, str],
                    first_node: int, last_node: int) -> tuple:
    """A row for the street merge input.

    The normalized and phonetic forms are computed here, while the object is
    in hand, so the merged rows post-processing creates carry them without a
    phonetic function in SQL.
    """
    name = tags['name']
    search_name = text.expand_street(name)
    return (osm_id, name, search_name, text.phonetic(search_name),
            result.cls, result.category, first_node, last_node)


def explode(osm_id: int, result: Result, params: Params, tags: Mapping[str, str],
            geometry) -> list[tuple]:
    """Polygon rows for an area, one per outer ring.

    The column is typed `Polygon`, so a multipolygon becomes several rows --
    but the zooms are computed once from the whole area, so a scattered
    nature reserve appears all at once rather than ring by ring.
    """
    row = render_row(osm_id, result, params, tags, geometry, 'polygon')
    return [(*row[:-1], part) for part in geom.polygon_parts(geometry)]
