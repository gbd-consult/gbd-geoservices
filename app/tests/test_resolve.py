"""Style resolution.

One entry in classes.yaml is not a symbolizer, it is a *change*. Getting the
order of application wrong produces a map that renders without an error and
looks subtly wrong, so a worked example (DESIGN.md "Style files" gives the
order) is pinned here property for property.
"""

from __future__ import annotations

import pytest
import yaml

from renderer import resolve
from renderer.resolve import Key, StyleError, Styles, parse_key

PALETTES = {
    'default': {'primary': '#fcd6a4', 'primary_case': '#d1ab82', 'halo': '#ffffff',
                'halo_radius': 1.5, 'casing_scale': 1.0},
    'hico': {'primary': '#ff0000', 'primary_case': '#000000', 'halo': '#ffffff',
             'halo_radius': 2.5, 'casing_scale': 1.3},
}

#: The worked example.
DESIGN_EXAMPLE = {
    '*': {'cls_road_primary': {'line-cap': 'round', 'line-join': 'round'}},
    'casing': {
        'cls_road_primary 10': {'line-color': 'primary_case', 'line-width': 4.8},
        'cls_road_primary 15': {'line-width': 9.5},
    },
    'fill': {
        'cls_road_primary 8': {'line-color': 'primary', 'line-width': 1.2},
        'cls_road_primary 10': {'line-width': 3.2},
        'cls_road_primary 15': {'line-width': 7.5},
    },
}


def with_entries(document, mode, entries):
    """`document` with `entries` added under `mode`."""
    return {**document, mode: {**document.get(mode, {}), **entries}}


@pytest.fixture
def example() -> Styles:
    return Styles(DESIGN_EXAMPLE, PALETTES)


# --- keys and sections ---------------------------------------------------

def test_parse_key():
    assert parse_key('cls_road_primary 15', 'casing') == Key('cls_road_primary', 'casing', 15)
    assert parse_key('cls_road_primary', '*') == Key('cls_road_primary', '*', None)
    assert parse_key('cls_waterway_river_intermittent', 'line') == Key(
        'cls_waterway_river_intermittent', 'line', None)


def test_a_class_glob_is_refused():
    # That would cascade across classes; sharing goes through templates and
    # tokens, which are explicit and greppable.
    with pytest.raises(StyleError, match='class glob'):
        parse_key('* 5', 'fill')


@pytest.mark.parametrize('key', ['cls_road_primary 15 extra', 'cls_road_primary twelve', ''])
def test_malformed_keys_are_refused(key):
    with pytest.raises(StyleError):
        parse_key(key, 'casing')


def test_properties_must_be_a_mapping():
    with pytest.raises(StyleError, match='must map to properties'):
        Styles({'fill': {'cls_road_primary 8': 'line-width: 3'}}, PALETTES)


def test_an_unknown_section_is_refused():
    # Skipped, a misspelt mode would drop all of its entries from the map
    # without an error.
    with pytest.raises(StyleError, match="'lable' is not a mode"):
        Styles({'lable': {'x 10': {'text': 'name'}}}, PALETTES)


def test_templates_are_not_read():
    styles = Styles({'templates': {'anything': {'text': 'name'}},
                     'label': {'x 10': {'text': 'name'}}}, PALETTES)
    assert styles.classes == {'x'}


def test_templates_merge_through_yaml_anchors():
    document = yaml.safe_load("""
templates:
  a: &a {font: F, size: 10}
  b: &b {size: 11, fill: c}
label:
  x 10: {<<: [*a, *b], halo: h}
  y 10: {<<: *a, size: 12}
""")
    styles = Styles(document, PALETTES)
    # The earlier template wins a key both have; the entry's own over all.
    assert styles.properties('x', 'label', 10) == {'font': 'F', 'size': 10, 'fill': 'c', 'halo': 'h'}
    assert styles.properties('y', 'label', 10) == {'font': 'F', 'size': 12}


def test_a_mode_without_a_zoom_is_refused():
    # Nothing says where it starts, so it would never be drawn.
    with pytest.raises(StyleError, match='line x: no entry has a zoom'):
        Styles({'line': {'x': {'line-color': 'primary', 'line-width': 1}}}, PALETTES)


# --- defaults ------------------------------------------------------------

def test_defaults_lie_under_every_entry_of_their_mode():
    styles = Styles({'defaults': {'label': {'text': 'name', 'halo': 'halo'}},
                     'label': {'x 10': {'font': 'F'}, 'y 12': {'text': 'label'}},
                     'fill': {'x 5': {'polygon-fill': 'primary'}}}, PALETTES)
    assert styles.properties('x', 'label', 10) == {'text': 'name', 'halo': 'halo', 'font': 'F'}
    assert styles.properties('y', 'label', 12) == {'text': 'label', 'halo': 'halo'}
    assert styles.properties('x', 'fill', 5) == {'polygon-fill': 'primary'}


def test_defaults_do_not_make_a_mode():
    # A class is drawn in a mode only if it has an entry there.
    styles = Styles({'defaults': {'label': {'text': 'name'}},
                     'fill': {'x 5': {'polygon-fill': 'primary'}}}, PALETTES)
    assert styles.modes('x') == {'fill'}


@pytest.mark.parametrize('mode', ['*', 'lable'])
def test_defaults_for_something_that_is_not_a_mode_are_refused(mode):
    with pytest.raises(StyleError, match='is not a mode'):
        Styles({'defaults': {mode: {'text': 'name'}}}, PALETTES)


# --- where a class starts ------------------------------------------------

def test_a_class_starts_at_its_lowest_zoom_in_a_geometry_mode(example):
    # fill 8, casing 10.
    assert example.start('cls_road_primary') == 8
    assert example.text_start('cls_road_primary') is None


def test_text_starts_at_the_lowest_label_or_shield_zoom():
    styles = Styles({'shield': {'x 10': {'text': 'label'}},
                     'label': {'x 13': {'text': 'name'}},
                     'fill': {'x 5': {'line-width': 1}}}, PALETTES)
    assert styles.text_start('x') == 10
    assert styles.start('x') == 5


def test_a_number_is_text_too():
    # A class with only a house number still needs its label rows.
    styles = Styles({'number': {'x 19': {'text': 'label'}},
                     'fill': {'x 13': {'polygon-fill': 'primary'}}}, PALETTES)
    assert styles.text_start('x') == 19


def test_a_marker_is_not_a_start():
    # Where an icon starts is the row's importance and the detail.
    styles = Styles({'marker': {'x': {'icon': True}}}, PALETTES)
    assert styles.start('x') is None
    assert styles.text_start('x') is None


def test_a_marker_always_has_the_key_zero():
    """Its first rule is the icon alone; the text comes in at its own zoom.

    With no zoomless entry, `x 17` would be the first key, and the first
    rule -- which the generator moves down to where the detail's icons
    start -- would carry the text from there.
    """
    styles = Styles({'defaults': {'marker': {'icon': True, 'size': 27}},
                     'marker': {'x 17': {'text': 'name'}}}, PALETTES)
    assert styles.zoom_keys('x', 'marker') == (0, 17)
    assert styles.properties('x', 'marker', 0) == {'icon': True, 'size': 27}
    assert styles.properties('x', 'marker', 17)['text'] == 'name'


# --- the worked example --------------------------------------------------

def test_design_example_casing_15(example):
    assert example.properties('cls_road_primary', 'casing', 15) == {
        'line-cap': 'round', 'line-join': 'round',
        'line-color': 'primary_case', 'line-width': 9.5,
    }


def test_design_example_fill_10(example):
    assert example.properties('cls_road_primary', 'fill', 10) == {
        'line-cap': 'round', 'line-join': 'round',
        'line-color': 'primary', 'line-width': 3.2,
    }


def test_a_zoom_key_holds_until_the_next(example):
    # 8 sets 1.2, 10 sets 3.2, 15 sets 7.5: everything between holds.
    widths = [example.properties('cls_road_primary', 'fill', z)['line-width']
              for z in (8, 9, 10, 14, 15, 18)]
    assert widths == [1.2, 1.2, 3.2, 3.2, 7.5, 7.5]


def test_below_the_first_zoom_nothing_is_drawn(example):
    # Only the *-mode entry applies: a cap and a join, which modify a
    # stroke nothing has provided. No symbolizer, so no rule.
    assert example.properties('cls_road_primary', 'fill', 7) == {
        'line-cap': 'round', 'line-join': 'round'}
    assert resolve.symbolizers(example.properties('cls_road_primary', 'fill', 7)) == ()


def test_modes_of_a_class(example):
    # `*` is not a mode: it carries shared properties and never draws.
    assert example.modes('cls_road_primary') == {'casing', 'fill'}


def test_zoom_keys(example):
    assert example.zoom_keys('cls_road_primary', 'casing') == (10, 15)
    assert example.zoom_keys('cls_road_primary', 'fill') == (8, 10, 15)
    assert example.zoom_keys('cls_road_primary', 'label') == ()


def test_a_shared_entry_at_a_zoom_adds_a_key():
    styles = Styles(with_entries(DESIGN_EXAMPLE, '*', {'cls_road_primary 12': {'line-cap': 'butt'}}),
                    PALETTES)
    # It changes what casing draws from 12 on, so 12 is a rule boundary.
    assert styles.zoom_keys('cls_road_primary', 'casing') == (10, 12, 15)
    assert styles.properties('cls_road_primary', 'casing', 12)['line-cap'] == 'butt'
    assert styles.properties('cls_road_primary', 'casing', 11)['line-cap'] == 'round'


def test_a_shared_entry_below_the_mode_is_not_a_key():
    # Nothing is drawn at z5 in casing mode, so there is nothing to change.
    styles = Styles(with_entries(DESIGN_EXAMPLE, '*', {'cls_road_primary 5': {'line-cap': 'butt'}}),
                    PALETTES)
    assert styles.zoom_keys('cls_road_primary', 'casing') == (10, 15)


def test_an_entry_without_a_zoom_applies_from_the_first_real_zoom():
    styles = Styles({'line': {
        'cls_waterway_river_intermittent': {'line-color': 'primary', 'line-dasharray': [4, 3]},
        'cls_waterway_river_intermittent 12': {'line-width': 1.5},
    }}, PALETTES)
    assert styles.zoom_keys('cls_waterway_river_intermittent', 'line') == (12,)
    assert styles.properties('cls_waterway_river_intermittent', 'line', 12) == {
        'line-color': 'primary', 'line-dasharray': [4, 3], 'line-width': 1.5}


def test_specific_mode_wins_over_shared_at_the_same_zoom():
    styles = Styles({
        '*': {'x 10': {'line-width': 1}},
        'fill': {'x 10': {'line-width': 2}},
    }, PALETTES)
    assert styles.properties('x', 'fill', 10)['line-width'] == 2


# --- palettes ------------------------------------------------------------

def test_tokens_are_substituted(example):
    painted = example.paint(example.properties('cls_road_primary', 'fill', 10), 'default', 'fill')
    assert painted['line-color'] == '#fcd6a4'
    assert painted['line-width'] == 3.2


def test_numeric_tokens_are_substituted_too():
    styles = Styles({'label': {'x 10': {'text': 'name', 'halo': 'halo',
                                        'halo-radius': 'halo_radius'}}}, PALETTES)
    painted = styles.paint(styles.properties('x', 'label', 10), 'hico', 'label')
    assert painted['halo-radius'] == 2.5
    assert painted['halo'] == '#ffffff'


def test_a_token_name_is_not_substituted_outside_a_token_property():
    """`label` is a palette token *and* the column a shield reads.

    Substituting on the value -- "is this string a token?" -- rewrote
    `text: label` to `text: '#333333'`, and Mapnik then looked for a column
    called #333333. Only found by rendering, so it is pinned here.
    """
    palettes = {'default': {'label': '#333333', 'halo': '#ffffff', 'casing_scale': 1.0}}
    styles = Styles({'shield': {'cls_road_motorway 10': {'text': 'label', 'fill': 'label',
                                                         'halo': 'halo'}}}, palettes)
    painted = styles.paint(styles.properties('cls_road_motorway', 'shield', 10),
                           'default', 'shield')
    assert painted['text'] == 'label'          # the column, untouched
    assert painted['fill'] == '#333333'        # the colour, substituted
    assert painted['halo'] == '#ffffff'


def test_a_value_that_is_not_a_token_is_left_alone():
    # `font`, `text` and `placement` are literals that happen to be strings.
    styles = Styles({'label': {'x 10': {'text': 'name', 'font': 'DejaVu Sans Book',
                                        'placement': 'line'}}}, PALETTES)
    painted = styles.paint(styles.properties('x', 'label', 10), 'default', 'label')
    assert painted == {'text': 'name', 'font': 'DejaVu Sans Book', 'placement': 'line'}


def test_casing_scale_applies_only_to_casing(example):
    casing = example.paint(example.properties('cls_road_primary', 'casing', 15), 'hico', 'casing')
    fill = example.paint(example.properties('cls_road_primary', 'fill', 15), 'hico', 'fill')
    assert casing['line-width'] == pytest.approx(9.5 * 1.3)
    assert fill['line-width'] == 7.5


def test_casing_scale_of_one_changes_nothing(example):
    painted = example.paint(example.properties('cls_road_primary', 'casing', 15), 'default', 'casing')
    assert painted['line-width'] == 9.5


def test_the_same_resolution_feeds_every_palette(example):
    properties = example.properties('cls_road_primary', 'casing', 10)
    assert {p: example.paint(properties, p, 'casing')['line-color'] for p in PALETTES} == {
        'default': '#d1ab82', 'hico': '#000000'}


# --- symbolizer type -----------------------------------------------------

@pytest.mark.parametrize('properties,kinds', [
    ({'polygon-fill': 'x'}, ('polygon',)),
    ({'line-color': 'x', 'line-width': 1}, ('line',)),
    ({'line-width': 1}, ('line',)),
    ({'text': 'name', 'font': 'f'}, ('text',)),
    ({'icon': True, 'size': 27}, ('marker',)),
    # Modifiers with nothing to modify draw nothing.
    ({'line-cap': 'round', 'line-join': 'round'}, ()),
    ({'line-dasharray': [4, 3]}, ()),
    ({'line-opacity': 0.5}, ()),
    ({}, ()),
])
def test_symbolizers_follow_the_properties(properties, kinds):
    assert resolve.symbolizers(properties) == kinds


def test_an_outlined_area_is_two_symbolizers():
    # A protected area is a translucent fill *and* a dashed outline; a
    # building is a fill and a stroke from z15. Returning one kind would
    # silently drop the other.
    assert resolve.symbolizers({'polygon-fill': 'x', 'polygon-opacity': 0.4,
                                'line-color': 'y', 'line-width': 1.5}) == ('polygon', 'line')


def test_a_labelled_marker_draws_the_icon_under_the_text():
    # Mapnik draws a rule's symbolizers in document order, so this is the
    # z-order within one rule: the label belongs on top of its own icon.
    assert resolve.symbolizers({'icon': True, 'text': 'name'}) == ('marker', 'text')


# --- against the real files ----------------------------------------------

def test_the_real_files_load(styles):
    assert len(styles.classes) == 131
    assert set(styles.palettes) == {'default', 'light', 'dark', 'hico',
                                   'grayscale', 'sepia', 'atkis', 'flora'}


def test_every_real_class_draws_in_at_least_one_mode(styles):
    for cls in styles.classes:
        assert styles.modes(cls), cls


def test_every_real_entry_resolves_to_a_symbolizer(styles):
    # A class/mode pair that resolves to no symbolizer at its own first zoom
    # is a style that can never draw.
    for cls in sorted(styles.classes):
        for mode in sorted(styles.modes(cls)):
            keys = styles.zoom_keys(cls, mode)
            assert keys, f'{cls} {mode} has no zoom key'
            first = styles.properties(cls, mode, keys[0])
            assert resolve.symbolizers(first), f'{cls} {mode} {keys[0]} draws nothing'


def test_the_real_road_primary_matches_design(styles):
    resolved = styles.properties('cls_road_primary', 'casing', 15)
    assert resolved['line-cap'] == 'round' and resolved['line-join'] == 'round'
    assert resolved['line-color'] == 'clr_primary_case'


def test_the_real_file_names_fonts_only_in_templates():
    """One place to change the typeface, and no entry that silently keeps
    the old one.

    Read as YAML nodes, before merge keys are resolved: an entry that merges
    a template has the key `<<`, one that names its own font has `font`.
    """
    from importer.run import STYLES

    root = yaml.compose((STYLES / 'classes.yaml').read_text())
    naming = []
    for section, body in root.value:
        if section.value == resolve.TEMPLATES:
            continue
        for key, properties in body.value:
            if any(name.value == 'font' for name, _ in properties.value):
                naming.append(f'{section.value} {key.value}')
    assert naming == []
