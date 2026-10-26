"""The compiled classifier must agree with a plain reading of the rules.

The bitmask compiler exists only to make 863 rules affordable over 5 M
objects. It is an optimisation, so the test that matters is that it decides
exactly what a naive top-down walk of classifier.yaml decides -- checked
over 2 000 tag sets taken from the real Schleswig-Holstein extract, which
is where the combinations that a hand-written fixture never thinks of come
from.
"""

from __future__ import annotations

import re

import pytest

from importer import rules as rules_module
from importer.rules import Categories, compile_rules, parse_match, split_geometry

# --- an independent implementation, deliberately slow and literal --------

def naive_geometry(expr: str) -> str | None:
    words = {term.strip() for term in expr.replace('|', '+').split('+')}
    kinds = words & set(rules_module.KINDS)
    return kinds.pop() if kinds else None


def naive_matches(expr: str, tags: dict[str, str]) -> bool:
    for alternative in expr.split('|'):
        for term in alternative.split('+'):
            if term.strip() in rules_module.KINDS:
                continue
            key, _, value = term.strip().partition('=')
            key, value = key.strip(), value.strip()
            if value == '*':
                if key not in tags:
                    break
            elif tags.get(key) != value:
                break
        else:
            return True
    return False


def naive_keys(expr: str) -> set[str]:
    return {term.strip().partition('=')[0].strip() for term in expr.replace('|', '+').split('+')
            if '=' in term}


def naive_classify(raw_rules, categories, tags, kind):
    cls = min_px = category = None
    collected: list[str] = []
    fallbacks = []
    keys: set[str] = set()
    for raw in raw_rules:
        if not naive_matches(raw['match'], tags):
            continue
        geometry = naive_geometry(raw['match'])
        if geometry is not None and geometry != kind:
            continue
        if re.fullmatch(r'[^=+|]+=\*( \+ (point|line|polygon))?', raw['match'].strip()):
            fallbacks.append(raw)
            continue
        keys |= naive_keys(raw['match'])
        if cls is None and raw.get('class') is not None:
            cls, min_px = raw['class'], raw.get('min_px')
        if category is None:
            category = raw['category']
        if raw['category'] not in collected:
            collected.append(raw['category'])
    for raw in fallbacks:
        if naive_keys(raw['match']) & keys:
            continue
        if cls is None and raw.get('class') is not None:
            cls, min_px = raw['class'], raw.get('min_px')
        if raw['category'] not in collected:
            collected.append(raw['category'])
            category = category or raw['category']
    if cls == rules_module.NO_CLASS:
        cls = min_px = None
    if cls is None and not collected:
        return rules_module.EMPTY
    return rules_module.Result(
        cls, min_px, categories.expand(collected), category,
        categories.importance[category] if category else None)


def test_compiled_matches_naive_over_real_tagsets(classifier, raw_rules, tagsets):
    for entry in tagsets:
        tags, kind = entry['tags'], entry['kind']
        expected = naive_classify(raw_rules, classifier.categories, tags, kind)
        actual = classifier.classify(classifier.tag_bits(tags), kind)
        assert actual == expected, f'{kind} {tags}'


def test_compiled_matches_naive_across_kinds(classifier, raw_rules, tagsets):
    # The same tag set under every geometry, since the restriction is what
    # makes amenity=hospital two different classes.
    for entry in tagsets[::7]:
        for kind in rules_module.KINDS:
            tags = entry['tags']
            expected = naive_classify(raw_rules, classifier.categories, tags, kind)
            actual = classifier.classify(classifier.tag_bits(tags), kind)
            assert actual == expected, f'{kind} {tags}'


# --- the compiled shape --------------------------------------------------

def test_corpus_shape(classifier):
    assert len(classifier.rules) == 1764
    assert len(classifier._bit) == 1554
    assert len(classifier.relevant_keys) == 173


def test_attribute_keys_are_not_classifier_keys(classifier):
    # The filter that feeds the passes is the union of these 173 keys and the
    # attributes the importer reads directly. If any of these ever became a
    # classifier key the union would still be right, but the reason the
    # union exists -- an address-only object matches no rule at all -- is
    # what this pins.
    for key in ('name', 'addr:street', 'addr:housenumber', 'height',
                'building:levels', 'layer', 'population', 'ref'):
        assert key not in classifier.relevant_keys


def test_memoises_on_bits_and_kind(classifier):
    bits = classifier.tag_bits({'amenity': 'restaurant'})
    assert classifier.classify(bits, 'point') is classifier.classify(bits, 'point')
    assert classifier.classify(bits, 'point') is not classifier.classify(bits, 'polygon')


# --- the mini-language ---------------------------------------------------

def test_parse_match():
    assert parse_match('a=b') == [[('a', 'b')]]
    assert parse_match('a=b + c=*') == [[('a', 'b'), ('c', '*')]]
    assert parse_match('a=b | c=d') == [[('a', 'b')], [('c', 'd')]]
    assert parse_match(' a = b ') == [[('a', 'b')]]


def test_parentheses_are_rejected():
    with pytest.raises(ValueError, match='parentheses are not supported'):
        parse_match('(a=b | c=d) + e=f')


def test_term_without_a_value_is_rejected():
    with pytest.raises(ValueError, match='without a value'):
        parse_match('a=b + c')


def test_a_geometry_term_restricts_the_rule():
    assert split_geometry('a=b + c=* + line') == ('a=b + c=*', 'line')
    assert split_geometry('a=b') == ('a=b', None)
    assert split_geometry('a=b + point | c=d + point') == ('a=b | c=d', 'point')


def test_two_geometries_are_rejected():
    with pytest.raises(ValueError, match='two geometries'):
        split_geometry('a=b + line + point')
    with pytest.raises(ValueError, match='different geometries'):
        split_geometry('a=b + line | c=d + point')


def test_no_rule_uses_the_unimplemented_syntax(raw_rules):
    for raw in raw_rules:
        assert '(' not in raw['match'], raw['match']


# --- worked cases --------------------------------------------------------

@pytest.mark.parametrize('tags,kind,cls,category', [
    ({'highway': 'primary', 'bridge': 'yes'}, 'line', 'cls_road_primary_bridge',
     'cat_built_roads_primary'),
    ({'highway': 'primary'}, 'line', 'cls_road_primary', 'cat_built_roads_primary'),
    # The road rules are for lines; as a node it is only a highway iD does
    # not know as a point.
    ({'highway': 'primary', 'bridge': 'yes'}, 'point', None, 'cat_built_roads_other'),
    ({'amenity': 'hospital'}, 'polygon', 'cls_landuse_hospital', 'cat_poi_health_hospital'),
    ({'amenity': 'hospital'}, 'point', 'cls_poi_health', 'cat_poi_health_hospital'),
    ({'amenity': 'restaurant'}, 'point', 'cls_poi_food', 'cat_poi_food_restaurant'),
    ({'natural': 'coastline'}, 'line', 'cls_coastline', 'cat_geography_water_coastline'),
    ({'waterway': 'river'}, 'line', 'cls_waterway_river', 'cat_geography_water_river'),
    ({'waterway': 'stream', 'intermittent': 'yes'}, 'line',
     'cls_waterway_stream_intermittent', 'cat_geography_water_stream'),
    # building=yes is 53 % of the buildings in a German extract and has no
    # iD preset, so it reaches only the key=* fallback. That rule carrying a
    # class is what puts those rows in osm_building at all.
    ({'building': 'yes'}, 'polygon', 'cls_building', 'cat_built_buildings'),
    ({'building': 'apartments'}, 'polygon', 'cls_building',
     'cat_built_buildings_residential_apartments'),
    ({'building': 'yes'}, 'point', None, None),
    # The tag iD only adds, not the one its preset matches on.
    ({'amenity': 'kindergarten'}, 'point', 'cls_poi_education', 'cat_poi_education_kindergarten'),
    ({'amenity': 'school'}, 'polygon', 'cls_landuse_school', 'cat_poi_education_school'),
    ({'amenity': 'bus_station'}, 'point', 'cls_poi_transport',
     'cat_built_transport_busstation_stationbus'),
    # A stop pole is a Bus Stop however it is tagged, and a platform point a stop.
    ({'highway': 'bus_stop', 'public_transport': 'platform', 'bus': 'yes'}, 'point',
     'cls_poi_transport', 'cat_built_transport_stop_busstop'),
    ({'public_transport': 'platform', 'bus': 'yes'}, 'point', 'cls_poi_transport',
     'cat_built_transport_stop_busstop'),
    ({'public_transport': 'platform', 'train': 'yes'}, 'point', 'cls_poi_transport',
     'cat_built_transport_stop_platform_train'),
    ({'public_transport': 'platform', 'bus': 'yes'}, 'line', 'cls_public_transport_path',
     'cat_built_transport_stop_platform_bus'),
    # Tags iD replaced, and area presets mapped as points.
    ({'amenity': 'nursing_home'}, 'polygon', 'cls_poi_health', 'cat_poi_health_care_nursinghome'),
    ({'landuse': 'basin'}, 'polygon', 'cls_water_lake', 'cat_geography_water_lake_water_basin'),
    ({'leisure': 'swimming_area'}, 'point', 'cls_poi_leisure', 'cat_poi_leisure_swimming_swimmingarea'),
    # A municipality relation tagged place=city is not a second city label
    # (`class: none`); its border ways still are borders.
    ({'boundary': 'administrative', 'admin_level': '6', 'place': 'city'}, 'polygon', None,
     'cat_geography_admin_6'),
    ({'boundary': 'administrative', 'admin_level': '6'}, 'line', 'cls_boundary_admin_6',
     'cat_geography_boundaries_admin'),
    ({'place': 'city'}, 'point', 'cls_place_city', 'cat_geography_places_city'),
    # boundary=* with no iD preset: a region is a place, an electoral
    # district a boundary of its own -- not "Sonstige Grenze".
    ({'boundary': 'region', 'place': 'region'}, 'polygon', None, 'cat_geography_places_region'),
    ({'place': 'region'}, 'point', None, 'cat_geography_places_region'),
    ({'boundary': 'political'}, 'polygon', None, 'cat_geography_boundaries_political'),
    # place=* kinds iD has no preset for, which were "Sonstiger Ort".
    ({'place': 'country'}, 'point', None, 'cat_geography_places_country'),
    ({'place': 'state'}, 'point', None, 'cat_geography_places_state'),
    ({'place': 'continent'}, 'point', None, 'cat_geography_places_continent'),
    ({'place': 'sea'}, 'point', None, 'cat_geography_water_sea'),
    ({'place': 'ocean'}, 'point', None, 'cat_geography_water_sea'),
    ({'place': 'archipelago'}, 'polygon', None, 'cat_geography_places_island'),
    ({'boundary': 'postal_code'}, 'polygon', None, 'cat_geography_boundaries_other'),
])
def test_worked_cases(classifier, tags, kind, cls, category):
    result = classifier.classify(classifier.tag_bits(tags), kind)
    assert (result.cls, result.category) == (cls, category)


def test_no_class_is_not_a_class(classifier):
    assert rules_module.NO_CLASS not in classifier.classes
    assert any(rule.cls == rules_module.NO_CLASS for rule in classifier.rules)


def test_a_key_fallback_counts_only_where_no_rule_on_its_key_did(classifier):
    """`amenity=*` matches every amenity. Counted everywhere, it would file
    every restaurant under "Sonstiges" as well."""
    restaurant = classifier.classify(classifier.tag_bits({'amenity': 'restaurant'}), 'point')
    assert 'cat_poi_other_amenity' not in restaurant.categories
    unknown = classifier.classify(classifier.tag_bits({'shop': 'value_1'}), 'point')
    assert unknown.category == 'cat_poi_shopping'
    assert unknown.cls == 'cls_poi_shopping'
    # A fallback on another key still counts: the restaurant is a building too.
    both = classifier.classify(
        classifier.tag_bits({'amenity': 'restaurant', 'building': 'yes'}), 'polygon')
    assert {'cat_poi_food_restaurant', 'cat_built_buildings'} <= set(both.categories)
    assert 'cat_poi_other_amenity' not in both.categories


def test_an_unknown_amenity_is_a_generic_poi(classifier):
    result = classifier.classify(classifier.tag_bits({'amenity': 'value_1'}), 'point')
    assert (result.cls, result.category) == ('cls_poi_other', 'cat_poi_other_amenity')


def test_a_known_value_without_a_class_does_not_fall_back_to_one(classifier):
    """A bench's rule is search-only. The `amenity=*` fallback carries a POI
    class, and letting it apply drew every bench as a generic POI."""
    bench = classifier.classify(classifier.tag_bits({'amenity': 'bench'}), 'point')
    assert bench.cls is None
    assert 'cat_poi_other_amenity' not in bench.categories


def test_admin_boundary_polygon_carries_its_level(classifier):
    """The relation polygon is what place resolution filters on.

    Every boundary=administrative rule with a class is restricted to lines,
    so without the search-only rules the assembled area would carry no level.
    """
    tags = {'boundary': 'administrative', 'admin_level': '6', 'name': 'Kiel'}
    area = classifier.classify(classifier.tag_bits(tags), 'polygon')
    assert area.cls is None
    assert area.category == 'cat_geography_admin_6'
    assert 'cat_geography_admin' in area.categories

    line = classifier.classify(classifier.tag_bits(tags), 'line')
    assert line.cls == 'cls_boundary_admin_6'


def test_an_admin_border_is_never_an_admin_area(classifier):
    """The border way is drawn and never searched; the area is searched.

    The level rules had no geometry restriction, so a border way collected
    the municipality's category too, and a named one would have been found
    as a municipality. Its own category has importance 0: no search row.
    """
    tags = {'boundary': 'administrative', 'admin_level': '8', 'name': 'Grenze'}
    line = classifier.classify(classifier.tag_bits(tags), 'line')
    assert line.categories == ('cat_geography', 'cat_geography_boundaries',
                               'cat_geography_boundaries_admin')
    assert line.importance == 0
    area = classifier.classify(classifier.tag_bits(tags), 'polygon')
    assert area.importance == 20
    assert not any(c.startswith('cat_geography_boundaries') for c in area.categories)


@pytest.mark.parametrize('level', range(2, 12))
def test_every_admin_level_has_an_area_category(classifier, level):
    tags = {'boundary': 'administrative', 'admin_level': str(level)}
    area = classifier.classify(classifier.tag_bits(tags), 'polygon')
    assert area.category == f'cat_geography_admin_{level}'


def test_categories_carry_every_ancestor(classifier):
    result = classifier.classify(classifier.tag_bits({'amenity': 'restaurant'}), 'point')
    assert result.category == 'cat_poi_food_restaurant'
    assert set(classifier.categories.ancestors['cat_poi_food_restaurant']) <= set(result.categories)


def test_no_relevant_tag_classifies_as_nothing(classifier):
    # The short circuit every untagged and irrelevantly-tagged object takes,
    # before any geometry work.
    assert classifier.tag_bits({'addr:housenumber': '12', 'addr:street': 'Holtenauer Straße'}) == 0
    assert classifier.classify(0, 'point') is rules_module.EMPTY


def test_duplicate_category_id_is_rejected():
    with pytest.raises(ValueError, match='duplicate category'):
        Categories([{'id': 'a'}, {'id': 'a'}], {'a': 0})


def test_unknown_category_is_rejected():
    categories = Categories([{'id': 'a'}], {'a': 0})
    with pytest.raises(ValueError, match='unknown category'):
        compile_rules([{'match': 'x=y', 'category': 'nope'}], categories)


TREE = [{'id': 'a', 'subs': [{'id': 'a_b', 'subs': [{'id': 'a_b_c'}]}, {'id': 'a_d'}]}]


def test_importance_is_inherited_from_the_nearest_listed_node():
    categories = Categories(TREE, {'a': 40, 'a_b': 80})
    assert categories.importance == {'a': 40, 'a_b': 80, 'a_b_c': 80, 'a_d': 40}


def test_importance_zero_is_inherited_like_any_value():
    categories = Categories(TREE, {'a': 40, 'a_b': 0})
    assert categories.importance['a_b_c'] == 0


def test_the_real_tree_inherits_importance(classifier):
    # boundaries set their own and their descendants do not.
    assert classifier.categories.importance['cat_geography_boundaries'] == 20
    assert classifier.categories.importance['cat_geography_boundaries_political'] == 20


def test_an_importance_key_that_is_no_category_is_refused():
    # A generated id follows iD's preset name; after an iD upgrade a stale
    # key would otherwise set nothing, silently.
    with pytest.raises(ValueError, match='unknown categories: a_x'):
        Categories(TREE, {'a': 40, 'a_x': 0})


def test_a_top_level_node_without_importance_is_refused():
    with pytest.raises(ValueError, match='no value'):
        Categories(TREE, {'a_b': 80})


@pytest.mark.parametrize('value', [-1, 101, 0.5, '60'])
def test_an_importance_outside_0_100_is_refused(value):
    with pytest.raises(ValueError, match='not an integer 0-100'):
        Categories(TREE, {'a': value})
