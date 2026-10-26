"""The ways pass's judgement: what one way writes to osm_line.

A boundary member way is the one object the importer writes twice, and the
rules around it are all failure modes that render without an error: a border
drawn once too often, a border drawn across the sea, or -- the one this file
was written for -- a river that vanishes because it also carries a border.
"""

from __future__ import annotations

import pytest

from importer import passes, rules
from importer.run import MODEL


@pytest.fixture(scope='module')
def classifier():
    return rules.load(MODEL)


@pytest.fixture(scope='module')
def admin(classifier):
    return passes.admin_classes(classifier)


def dispatch(classifier, admin, tags, *, level=None, relevant=True, closed_area=False):
    return passes.line_dispatch(classifier, admin, tags, level=level,
                                relevant=relevant, closed_area=closed_area)


def classes(writes):
    return [(result.cls, search) for result, search in writes]


# --- the classes are asked of the classifier, not spelled out ------------

def test_the_admin_classes_come_from_the_rules(admin):
    assert admin == {'cls_boundary_admin_2', 'cls_boundary_admin_4',
                     'cls_boundary_admin_6', 'cls_boundary_admin_8'}


# --- an ordinary way -----------------------------------------------------

def test_a_plain_road_writes_one_row(classifier, admin):
    assert classes(dispatch(classifier, admin, {'highway': 'primary'})) \
        == [('cls_road_primary', True)]


def test_an_irrelevant_way_writes_nothing(classifier, admin):
    assert dispatch(classifier, admin, {'foo': 'bar'}, relevant=False) == []


def test_a_closed_area_belongs_to_the_areas_pass(classifier, admin):
    assert dispatch(classifier, admin, {'landuse': 'forest'}, closed_area=True) == []


# --- a way that is only a border -----------------------------------------

def test_an_untagged_member_way_is_the_border(classifier, admin):
    assert classes(dispatch(classifier, admin, {}, level=6, relevant=False)) \
        == [('cls_boundary_admin_6', True)]


def test_a_way_tagged_as_a_border_is_still_written_once(classifier, admin):
    """Every border way belongs to at least two municipalities and often to
    a district and a state as well, so it must not be written per relation
    -- and its own tags say the same thing the relation does."""
    writes = dispatch(classifier, admin,
                      {'boundary': 'administrative', 'admin_level': '8'}, level=6)
    assert classes(writes) == [('cls_boundary_admin_6', True)]


def test_the_level_is_the_relations_not_the_ways(classifier, admin):
    """The lowest level any relation claims it at is the one it is drawn as,
    which is what `boundary_levels` computed."""
    writes = dispatch(classifier, admin,
                      {'boundary': 'administrative', 'admin_level': '8'}, level=2)
    assert classes(writes) == [('cls_boundary_admin_2', True)]


# --- a way that is a border *and* a feature ------------------------------

@pytest.mark.parametrize('tags,expected', [
    ({'waterway': 'river'}, 'cls_waterway_river'),
    ({'waterway': 'stream'}, 'cls_waterway_stream'),
    ({'waterway': 'canal'}, 'cls_waterway_canal'),
    ({'natural': 'coastline'}, 'cls_coastline'),
])
def test_a_border_that_is_also_a_feature_writes_both(classifier, admin, tags, expected):
    """The regression this file exists for.

    The ways pass classified a member way from synthetic boundary tags and
    threw its own tags away, so on Schleswig-Holstein 113 ways lost their
    real class: 47 rivers, 42 streams, 18 canals and 5 coastline ways --
    on the extract chosen specifically for having a coastline. Nothing
    failed; the river was simply not on the map where it carried a border.
    """
    writes = dispatch(classifier, admin, tags, level=6)
    assert classes(writes) == [('cls_boundary_admin_6', False), (expected, True)]


def test_the_feature_keeps_the_search_row_not_the_border(classifier, admin):
    """A river named Stör is a river, not a district boundary: the search
    row has to carry the waterway's categories, not the border's."""
    writes = dispatch(classifier, admin, {'waterway': 'river', 'name': 'Stör'}, level=6)
    border, feature = writes
    assert border[1] is False and feature[1] is True
    assert 'water' in feature[0].categories or feature[0].category
    assert feature[0].category != border[0].category


def test_a_named_member_way_with_no_class_stays_one_row(classifier, admin):
    """No class of its own means there is nothing to write a second row
    for, so the border carries it -- including its name."""
    writes = dispatch(classifier, admin, {'name': 'Landesgrenze'}, level=4)
    assert classes(writes) == [('cls_boundary_admin_4', True)]


# --- maritime ------------------------------------------------------------

def test_a_maritime_border_is_not_drawn(classifier, admin):
    """A sea border must not cross the water (DESIGN.md "Import"). 65 ways
    on Schleswig-Holstein, which is the Kiel Fjord and the North Sea."""
    assert dispatch(classifier, admin,
                    {'boundary': 'administrative', 'admin_level': '2',
                     'maritime': 'yes'}, level=2) == []


def test_maritime_drops_the_border_not_the_way(classifier, admin):
    """Only the border is dropped. Every maritime member way on
    Schleswig-Holstein happens to be a border and nothing else, so this
    changes no row today -- and a maritime way that is also a coastline
    would otherwise take the coastline off the map with it."""
    writes = dispatch(classifier, admin,
                      {'natural': 'coastline', 'maritime': 'yes'}, level=2)
    assert classes(writes) == [('cls_coastline', True)]


def test_maritime_suppresses_the_ways_own_border_class_too(classifier, admin):
    """63 of the 65 maritime member ways on Schleswig-Holstein carry
    `boundary=administrative` themselves, so suppressing only the
    relation's border lets the way put it straight back -- across the
    water, which is the whole thing the rule forbids."""
    writes = dispatch(classifier, admin,
                      {'boundary': 'administrative', 'admin_level': '2',
                       'maritime': 'yes'}, level=None)
    assert writes == []


# --- the class-drift check -----------------------------------------------

def test_the_real_files_do_not_drift(classifier):
    """`classifier.yaml` and `styles/classes.yaml` name the same classes.

    Both directions are silent: a ruled class nobody styles imports and is
    never labelled, a styled class no rule produces is a layer that draws
    nothing. The import runs the check before it writes anything
    (DESIGN.md "Import").
    """
    from importer import params as params_module
    from importer import run
    from importer.run import MODEL, STYLES

    run.check_class_drift(classifier, params_module.load(MODEL, STYLES))


def test_a_styled_class_no_rule_produces_is_refused(classifier):
    from importer import params as params_module
    from importer import run
    from importer.run import MODEL, STYLES

    params = params_module.load(MODEL, STYLES)
    params.styled_classes = params.styled_classes | {'invented_class'}
    with pytest.raises(run.ClassDriftError, match='invented_class'):
        run.check_class_drift(classifier, params)


def test_a_ruled_class_nobody_styles_is_refused(classifier):
    from importer import params as params_module
    from importer import run
    from importer.run import MODEL, STYLES

    params = params_module.load(MODEL, STYLES)
    dropped = sorted(params.styled_classes)[0]
    params.styled_classes = params.styled_classes - {dropped}
    with pytest.raises(run.ClassDriftError, match=dropped):
        run.check_class_drift(classifier, params)


def test_ocean_is_not_drift():
    """The water import assigns it and no rule produces it."""
    from importer import run

    assert run.WATER_CLASS == 'cls_ocean'
