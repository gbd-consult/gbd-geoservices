"""Draw order: z_order = clamp(layer, -5, 5) * 1000 + rank.

The rank lookup is the class itself, else the longest key of
z_order.rank that is a prefix of it, else default -- which is how one entry
per road kind covers its bridge and tunnel variants.
"""

from __future__ import annotations

import pytest

from importer import elevation


@pytest.mark.parametrize('cls,rank', [
    ('cls_road_primary', 80),
    ('cls_road_primary_bridge', 80),          # longest prefix, not cls_road_path or cls_road
    ('cls_road_primary_tunnel', 80),
    ('cls_road_motorway_bridge', 90),
    ('cls_road_minor_tunnel', 60),
    ('cls_transit_tram', 93),
    ('cls_rail_rail', 95),
    ('cls_rail_rail_bridge', 95),
    ('cls_waterway_stream_intermittent', 15),
    ('cls_waterway_ditch', 10),
    ('cls_ocean', 0),                          # no entry and no prefix -> default
    ('cls_landcover_wood', 0),
    ('cls_building', 0),
])
def test_rank_lookup(params, cls, rank):
    assert params.rank(cls) == rank


def test_rank_is_cached(params):
    assert params.rank('cls_road_primary_bridge') == params.rank('cls_road_primary_bridge')


@pytest.mark.parametrize('layer,expected', [
    (None, 80),
    ('0', 80),
    ('1', 1080),
    ('-2', -1920),
    ('5', 5080),
    ('-5', -4920),
    ('99', 5080),        # clamped to layer_tag_max
    ('-99', -4920),      # clamped to layer_tag_min
    ('abc', 80),         # unparseable is no layer at all
    ('', 80),
])
def test_layer_tag(params, layer, expected):
    tags = {} if layer is None else {'layer': layer}
    assert params.z_order('cls_road_primary', tags) == expected


def test_a_bridge_sorts_above_the_road_it_crosses(params):
    # The whole point of the layer term: a bridged minor road must come out
    # above an unbridged motorway.
    bridge = params.z_order('cls_road_minor_bridge', {'layer': '1'})
    motorway = params.z_order('cls_road_motorway', {})
    assert bridge > motorway


def test_places_carry_population_instead(params):
    # DESIGN.md "Draw order": for places the column is the population, so
    # the larger place wins the label collision test.
    assert params.z_order('cls_place_city', {'population': '247000'}) == 247000
    assert params.z_order('cls_place_village', {'population': '820'}) == 820
    assert params.z_order('cls_place_city', {}) == 0
    assert params.z_order('cls_place_city', {'population': 'about 2000'}) == 0
    # The layer tag is ignored there, which is the part that surprises.
    assert params.z_order('cls_place_city', {'population': '100', 'layer': '3'}) == 100


def test_building_height(params):
    assert params.building_height({'height': '12'}) == (12.0, 'tag')
    assert params.building_height({'height': '12.5 m'}) == (12.5, 'tag')
    assert params.building_height({'height': '7m'}) == (7.0, 'tag')
    assert params.building_height({'building:levels': '4'}) == (4 * params.level_height_m, 'levels')
    assert params.building_height({}) == (params.default_height_m, 'est')
    # Garbage in either tag falls through to the next source rather than
    # failing the object: both are free-text fields in practice.
    assert params.building_height({'height': 'tall'}) == (params.default_height_m, 'est')
    assert params.building_height({'height': 'tall', 'building:levels': '2'}) \
        == (2 * params.level_height_m, 'levels')
    assert params.building_height({'height': '0'}) == (params.default_height_m, 'est')


def test_merge_classes(params):
    assert params.is_merge_class('cls_road_primary')
    assert params.is_merge_class('cls_road_minor_bridge')
    assert not params.is_merge_class('cls_waterway_river')
    assert not params.is_merge_class('cls_building')


def test_layer_class_sets_expand_globs(params, classifier):
    known = ({rule.cls for rule in classifier.rules if rule.cls}
             | {'cls_ocean', *elevation.classes()})
    sets = dict(params.layer_class_sets(known))
    assert sets['ocean'] == {'cls_ocean'}
    assert sets['buildings'] == {'cls_building'}
    assert 'cls_road_primary' in sets['roads_fill']
    assert 'cls_road_primary_bridge' in sets['bridges_fill']
    # Every layer must match something, or a style glob has gone stale.
    for name, classes in sets.items():
        assert classes, f'layer {name} matches no class'
