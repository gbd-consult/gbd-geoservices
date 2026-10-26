"""The size thresholds of DESIGN.md "Sizes and zooms".

Sizes are measured on the projected geometry, in 3857 units. At 54 N -- the
middle of the test area -- a 3857 unit is 0.59 m of ground, so the examples
below convert ground metres up by 1/cos(54) before applying the formula.
Measuring in ground metres instead would make the same object appear a zoom
later in Flensburg than in Hamburg, which is what "no latitude correction"
rules out.
"""

from __future__ import annotations

import math

import pytest

#: 3857 units per ground metre at 54 N.
SH = 1.0 / math.cos(math.radians(54.0))


def area_3857(ground_m2: float) -> float:
    return ground_m2 * SH * SH


def length_3857(ground_m: float) -> float:
    return ground_m * SH


def test_forest(params):
    # 1 km2 of ground is 2.8 x 2.8 px at z8 and 1.4 x 1.4 at z7, so z8.
    assert params.size_minzoom_area(area_3857(1e6), params.polygon_px2) == 8


def test_house(params):
    assert params.size_minzoom_area(area_3857(100), params.building_px2) == 14


def test_residential_street_label(params):
    # A 500 m street is labelled from the zoom its length reaches 100 px.
    # The street itself is drawn from its class zoom, see features.minzooms.
    assert params.size_minzoom_length(length_3857(500), params.line_label_px) == 15


def test_label_thresholds_are_stricter_than_draw_thresholds(params):
    for ground in (100, 10_000, 1e6, 1e8):
        assert (params.size_minzoom_area(area_3857(ground), params.polygon_label_px2)
                >= params.size_minzoom_area(area_3857(ground), params.polygon_px2))


def test_bigger_is_earlier(params):
    zooms = [params.size_minzoom_area(area_3857(a), params.polygon_px2)
             for a in (1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8)]
    assert zooms == sorted(zooms, reverse=True)


def test_clamped_to_the_configured_range(params):
    # A continent is still 0, a doorstep is still 18.
    assert params.size_minzoom_area(area_3857(1e13), params.polygon_px2) == params.zoom_min
    assert params.size_minzoom_area(area_3857(0.0001), params.polygon_px2) == params.zoom_max
    assert params.size_minzoom_length(length_3857(1e9), params.line_label_px) == params.zoom_min


@pytest.mark.parametrize('size', [0.0, -1.0])
def test_degenerate_geometry_does_not_divide_by_zero(params, size):
    # A zero-area polygon and a zero-length way are both real in OSM data.
    assert params.size_minzoom_area(size, params.polygon_px2) == params.zoom_max
    assert params.size_minzoom_length(size, params.line_label_px) == params.zoom_max


def test_building_threshold_comes_from_the_class(params):
    # No generated rule sets min_px, so the 1 px2 building threshold has to
    # be reachable from the class alone.
    assert params.draw_px2('cls_building', None) == params.building_px2
    assert params.draw_px2('cls_landcover_wood', None) == params.polygon_px2
    assert params.draw_px2('cls_building', 9.0) == 9.0


def test_label_minzoom_comes_from_the_style(params):
    # 244 of the 291 classes are styled with text; the rest are never
    # labelled and must return None rather than a zoom.
    assert params.label_minzoom('cls_waterway_river') == 12
    assert params.label_minzoom('cls_road_primary') is not None
    assert params.label_minzoom('cls_coastline') is None
    assert params.label_minzoom('not_a_class') is None


def test_shield_counts_as_text(params):
    # cls_road_motorway has a shield at z10 and a label later; a motorway with a
    # ref and no name still has to get a label row.
    assert params.label_minzoom('cls_road_motorway') == 10
