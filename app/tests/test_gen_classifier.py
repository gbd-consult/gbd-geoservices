"""The model generator: model/categories.yaml + iD + OpenMapTiles -> model/generated/.

The generated files are what the importer, search and the style check read,
and nothing reads model/categories.yaml at run time. So the checks here are
the ones that keep a hand edit of the tree from silently becoming a
different generated model.
"""

from __future__ import annotations

import pytest
import yaml

from importer.run import MODEL
from tools import gen_classifier as gen


def node(node_id, **kw):
    return {'id': node_id, 'name_en': node_id, 'name_de': node_id, **kw}


def test_colliding_preset_names_both_take_more_of_their_path():
    """Neither gets the short name by accident of order."""
    segments = gen._segments(['highway/footway/crossing', 'highway/cycleway/crossing',
                              'highway/crossing/unmarked'], 'cat_x', set())
    assert segments == {'highway/footway/crossing': 'footwaycrossing',
                        'highway/cycleway/crossing': 'cyclewaycrossing',
                        'highway/crossing/unmarked': 'unmarked'}


def test_a_generated_id_never_takes_a_hand_written_one():
    segments = gen._segments(['amenity/parking'], 'cat_x', {'cat_x_parking'})
    assert segments == {'amenity/parking': 'amenityparking'}


def test_the_poi_class_is_the_second_level():
    assert gen.poi_class('cat_poi_food_cafe_bubbletea') == 'poi_food'
    assert gen.poi_class('cat_built_roads_parking') == 'poi_roads'


def test_the_tag_iD_only_adds_is_matched_too():
    """iD 7's kindergarten preset matches `education=kindergarten` and only
    adds `amenity=kindergarten` -- the tag nearly every kindergarten has."""
    assert gen.legacy_tags({'tags': {'education': 'kindergarten'},
                            'addTags': {'amenity': 'kindergarten', 'education': 'kindergarten'}}) \
        == {'amenity': 'kindergarten'}
    # A preset that matches on a POI key already needs nothing more.
    assert gen.legacy_tags({'tags': {'amenity': 'clinic'},
                            'addTags': {'amenity': 'clinic', 'healthcare': 'clinic'}}) == {}
    assert gen.legacy_tags({'tags': {'education': 'school'}}) == {}


def test_the_generated_rules_match_the_legacy_tags():
    rules = {r['match']: r for r in yaml.safe_load((MODEL / 'generated' / 'classifier.yaml').read_text())}
    assert rules['amenity=kindergarten + point']['class'] == 'cls_poi_education'
    assert rules['amenity=school + polygon']['category'] == 'cat_poi_education_school'
    assert rules['amenity=bus_station + point']['category'] == 'cat_built_transport_busstation_stationbus'
    # Matched as it is by its own preset, not taken over by one that adds it.
    assert rules['leisure=marina']['category'] == 'cat_poi_leisure_marina'


def test_the_base_rule_category_is_the_common_ancestor():
    assert gen.common_ancestor(['cat_poi_food_cafe', 'cat_poi_food_bar']) == 'cat_poi_food'
    assert gen.common_ancestor(['cat_poi_food_cafe', 'cat_built_roads']) is None


@pytest.mark.parametrize('roots,message', [
    ([node('poi')], 'is not cat_'),
    ([node('cat_poi', subs=[node('cat_food')])], 'plus one segment'),
    ([node('cat_poi', subs=[node('cat_poi_food_cafe')])], 'plus one segment'),
    ([node('cat_poi', presets=['amenity/cafe'], subs=[node('cat_poi_x', presets=['amenity/cafe'])])],
     'listed at'),
])
def test_a_malformed_tree_is_refused(roots, message):
    with pytest.raises(SystemExit, match=message):
        gen.Tree(roots)


def test_the_marker_flag_is_inherited():
    tree = gen.Tree([node('cat_poi', marker=True, subs=[node('cat_poi_food')]),
                     node('cat_built', subs=[node('cat_built_roads', marker=True)])])
    assert tree.marker == {'cat_poi': True, 'cat_poi_food': True,
                           'cat_built': False, 'cat_built_roads': True}


def test_the_generated_files_are_current():
    """model/generated/ is what everything reads; a tree edited without
    running gen_model.sh would import under the old one."""
    cache = gen.Path(gen.__file__).with_name('.cache')
    if not any(cache.glob('*presets.json')):
        pytest.skip('no cached iD sources; run app/scripts/gen_model.sh once')
    presets, names, omt = gen.load_sources(cache)
    tree = gen.Tree(yaml.safe_load((MODEL / 'categories.yaml').read_text()))
    assigned, _ = gen.assign(tree, presets)
    categories, category = gen.deepen(tree, assigned, names)
    rules = [gen.written(r) for r in
             gen.build_rules(presets, assigned, category, tree, gen.build_class_lookup(omt))]
    manual = {r['match'] for r in yaml.safe_load((MODEL / 'classifier.yaml').read_text())}
    rules = [r for r in rules if r['match'] not in manual]

    assert categories == yaml.safe_load((MODEL / 'generated' / 'categories.yaml').read_text())
    assert rules == yaml.safe_load((MODEL / 'generated' / 'classifier.yaml').read_text())
