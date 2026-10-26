"""Row building: the arithmetic of DESIGN.md "Sizes and zooms" applied to objects."""

from __future__ import annotations

import math

import pytest
import shapely

from importer import features
from importer import tables as t
from importer.rules import Result

SH = 1.0 / math.cos(math.radians(54.0))     # 3857 units per ground metre at 54 N


def square(ground_m2: float):
    side = math.sqrt(ground_m2) * SH
    return shapely.Polygon([(0, 0), (side, 0), (side, side), (0, side)])


def line(ground_m: float):
    return shapely.LineString([(0, 0), (ground_m * SH, 0)])


def result(cls=None, min_px=None, category=None, importance=None):
    return Result(cls, min_px, (category,) if category else (), category, importance)


# --- minzoom -------------------------------------------------------------

def test_point_minzoom_is_the_class_minzoom(params):
    minzoom, _ = features.minzooms(result('cls_road_service'), params,
                                   shapely.Point(0, 0), 'point', True)
    assert minzoom == params.class_minzoom['cls_road_service'] == 14


def test_the_class_minzoom_is_where_the_style_starts_it(params):
    # The lowest zoom in fill, line or casing: fill 5 and casing 10.
    assert params.minzoom('cls_road_motorway') == 5
    assert params.minzoom('cls_coastline') == 12


def test_a_class_never_drawn_as_geometry_is_kept_out_of_every_band(params):
    """A POI is drawn as a marker, a place as text; neither reads minzoom.

    zoom_max keeps their polygons and lines out of the band tables, which
    select on it -- a school's grounds would otherwise be unioned into _z9
    for a fill nothing draws.
    """
    assert params.minzoom('cls_poi_food') == params.zoom_max
    assert params.minzoom('cls_place_city') == params.zoom_max
    assert params.label_minzoom('cls_place_city') == 8
    minzoom, _ = features.minzooms(result('cls_poi_food'), params, square(1e8), 'polygon', False)
    assert minzoom == params.zoom_max


def test_size_raises_the_class_minzoom(params):
    # A tiny forest is not drawn at the class's z5 just because forests are.
    minzoom, _ = features.minzooms(result('cls_landcover_wood'), params,
                                   square(100), 'polygon', False)
    assert minzoom > 5


def test_class_minzoom_raises_the_size_minzoom(params):
    # A continent-sized service road is still a service road.
    minzoom, _ = features.minzooms(result('cls_road_service'), params,
                                   line(500_000), 'line', False)
    assert minzoom == 14


@pytest.mark.parametrize('ground_m', [5, 50, 500, 5_000])
def test_a_line_is_drawn_from_its_class_zoom_whatever_its_length(params, ground_m):
    """No size test for drawing a line.

    OSM cuts a road at every junction and bridge; a per-way size test hid
    4 581 of `de_sh`'s 6 611 primary-road segments at z10-12 and drew main
    roads as dashes. A 50 m bridge of a motorway is still the motorway.
    """
    minzoom, _ = features.minzooms(result('cls_road_motorway'), params,
                                   line(ground_m), 'line', False)
    assert minzoom == 5


def test_a_line_label_still_has_to_fit(params):
    # A label is placed on one way's geometry, so its size test stays.
    _, short = features.minzooms(result('cls_road_primary'), params, line(50), 'line', True)
    _, long = features.minzooms(result('cls_road_primary'), params, line(20_000), 'line', True)
    assert short > long


def test_buildings_use_the_smaller_threshold(params):
    # 1 px2 against 4 px2 is a factor of 4 in area, so a factor of 2 in
    # linear size: exactly one zoom earlier, not two. Both are above their
    # class floors (13 and 5), so this is the size alone.
    small = square(100)
    assert params.size_minzoom_area(shapely.area(small), params.building_px2) == 14
    assert features.minzooms(result('cls_building'), params, small, 'polygon', False)[0] == 14
    assert features.minzooms(result('cls_landcover_wood'), params, small, 'polygon', False)[0] == 15


def test_minzoom_label_is_null_without_text(params):
    _, label = features.minzooms(result('cls_landcover_wood'), params,
                                 square(1e6), 'polygon', False)
    assert label is None


def test_minzoom_label_is_null_when_the_class_is_never_labelled(params):
    assert params.label_minzoom('cls_coastline') is None
    _, label = features.minzooms(result('cls_coastline'), params, line(5000), 'line', True)
    assert label is None


def test_minzoom_label_is_later_than_minzoom(params):
    minzoom, label = features.minzooms(result('cls_landcover_wood'), params,
                                       square(1e6), 'polygon', True)
    assert label is not None and label > minzoom


# --- rows ----------------------------------------------------------------

def test_render_row_matches_the_table(params):
    row = features.render_row(42, result('cls_poi_food'), params,
                              {'name': 'Café'}, line(100), 'line')
    assert len(row) == len(t.copy_names(t.OSM_LINE))
    assert row[0] == 42 and row[1] == 'cls_poi_food' and row[2] == 'Café'


def test_point_row_carries_its_own_category(params):
    # The marker layer reads the icon file named after it.
    row = features.point_row(42, result('cls_poi_food', category='cat_poi_food_cafe',
                                        importance=60), params,
                             {'name': 'Café'}, shapely.Point(1, 2))
    assert len(row) == len(t.copy_names(t.OSM_POINT))
    assert row[0] == 42 and row[1] == 'cls_poi_food' and row[2] == 'Café'
    names = t.copy_names(t.OSM_POINT)
    assert row[names.index('category')] == 'cat_poi_food_cafe'
    # The style run sets it, from the category and styles/icons.yaml.
    assert row[names.index('icon')] is None
    # The marker query draws and orders by it.
    assert row[names.index('importance')] == 60


def test_building_row_matches_the_table(params):
    rows = features.building_rows(7, result('cls_building'), params,
                                  {'building:levels': '3'}, square(200))
    assert len(rows) == 1
    row = rows[0]
    assert len(row) == len(t.copy_names(t.OSM_BUILDING))
    assert row[-3] == pytest.approx(3 * params.level_height_m)
    assert row[-2] == 'levels'
    assert shapely.get_type_id(row[-1]) == 3


def test_a_multipolygon_building_is_exploded(params):
    # osm_building.geom is typed Polygon, so a building mapped as a
    # multipolygon has to become several rows or the column rejects it.
    side = 20 * SH
    multi = shapely.MultiPolygon([
        [[(0, 0), (side, 0), (side, side), (0, 0)], []],
        [[(100, 100), (100 + side, 100), (100 + side, 100 + side), (100, 100)], []],
    ])
    rows = features.building_rows(7, result('cls_building'), params, {'height': '9'}, multi)
    assert len(rows) == 2
    assert all(shapely.get_type_id(r[-1]) == 3 for r in rows)
    assert all(r[-3] == pytest.approx(9.0) and r[-2] == 'tag' for r in rows)


def test_label_value():
    assert features.label_value({'ref': 'A7'}) == 'A7'
    assert features.label_value({'addr:housenumber': '12a'}) == '12a'
    assert features.label_value({'ele': '168'}) == '168'
    assert features.label_value({'name': 'x'}) is None
    # A road with both keeps the ref: that is what the shield draws.
    assert features.label_value({'ref': 'A7', 'addr:housenumber': '1'}) == 'A7'


def test_label_row_is_skipped_without_text(params):
    row = features.render_row(1, result('cls_landcover_wood'), params, {},
                              square(1e6), 'polygon')
    assert features.label_row(row, result('cls_landcover_wood'), shapely.Point(0, 0)) is None


def test_label_row_from_a_ref_alone(params):
    # A motorway with a ref and no name still has to get a shield.
    row = features.render_row(1, result('cls_road_motorway'), params,
                              {'ref': 'A7'}, line(50_000), 'line')
    label = features.label_row(row, result('cls_road_motorway'), shapely.Point(0, 0))
    assert label is not None
    assert len(label) == len(t.copy_names(t.OSM_LABEL))
    assert label[2] is None and label[3] == 'A7'


def test_label_row_carries_what_decides_whether_it_yields_to_an_icon(params):
    # The label query hides an area's label from where its icon starts.
    names = t.copy_names(t.OSM_LABEL)
    row = features.render_row(1, result('cls_landuse_hospital'), params, {'name': 'name_1'},
                              square(1e6), 'polygon')
    label = features.label_row(row, result('cls_landuse_hospital', category='category_1',
                                           importance=80), shapely.Point(0, 0))
    assert label[names.index('category')] == 'category_1'
    assert label[names.index('importance')] == 80
    # Set by the style run, like osm_point's.
    assert label[names.index('icon')] is None


def test_marker_row_uses_the_class_zoom_not_the_size(params):
    """A marker row gets what the same object mapped as a node would get.

    The polygon is tiny, so by size it earns its fill only deep in; the
    marker row carries the class zoom.
    """
    tiny = square(10)
    polygon = features.render_row(5, result('cls_public_transport_path'), params,
                                  {'name': 'Maxim'}, tiny, 'polygon')
    marker = features.marker_row(5, result('cls_public_transport_path',
                                           category='category_1'),
                                 params, {'name': 'Maxim'}, shapely.Point(1, 2))
    assert polygon[5] > 15, 'a tiny polygon should be size-limited'
    assert marker[5] == 15
    assert len(marker) == len(t.copy_names(t.OSM_POINT))
    assert marker[t.copy_names(t.OSM_POINT).index('category')] == 'category_1'


def test_marker_row_carries_no_label(params):
    # The object's label comes from its own osm_label row; a second one
    # would label it twice.
    marker = features.marker_row(5, result('cls_poi_food'), params,
                                 {'name': 'Cafe'}, shapely.Point(1, 2))
    assert marker[6] is None


def test_only_classes_the_style_marks_get_one(params):
    assert params.draws_marker('cls_poi_food')
    # An area with a marker entry gets its icon from a marker row.
    assert params.draws_marker('cls_landuse_hospital')
    # Areas and roads are drawn, not dotted -- and a platform mapped as a
    # way is a platform; mapped as a point it is a stop, cls_poi_transport.
    assert not params.draws_marker('cls_landuse_cemetery')
    assert not params.draws_marker('cls_public_transport_path')
    assert not params.draws_marker('cls_building')
    assert not params.draws_marker('cls_road_primary')
    assert not params.draws_marker(None)


def test_explode_shares_one_zoom_across_the_parts(params):
    # Two small islands of one reserve must appear together, at the zoom the
    # whole reserve earns, not each at its own.
    side = 300 * SH
    multi = shapely.MultiPolygon([
        [[(0, 0), (side, 0), (side, side), (0, 0)], []],
        [[(10_000, 10_000), (10_000 + side, 10_000), (10_000 + side, 10_000 + side),
          (10_000, 10_000)], []],
    ])
    rows = features.explode(5, result('cls_protected_area'), params, {'name': 'Reserve'}, multi)
    assert len(rows) == 2
    assert {r[0] for r in rows} == {5}
    assert len({r[5] for r in rows}) == 1
    assert all(shapely.get_type_id(r[-1]) == 3 for r in rows)
    assert all(len(r) == len(t.copy_names(t.OSM_POLYGON)) for r in rows)


def test_explode_of_a_single_polygon_is_one_row(params):
    rows = features.explode(5, result('cls_landcover_wood'), params, {}, square(1e6))
    assert len(rows) == 1
