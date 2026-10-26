"""The legend: what `legend.yaml` may say, what a theme shows, how it is drawn.

A legend that shows a class its theme does not draw, or draws it in other
colours than the map, is wrong without anything failing -- so the checks
are against the real style files, and the drawing is the style's own.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from importer.run import MODEL, STYLES
from renderer import icons, legend
from renderer import styles as gen
from renderer.styles import Theme


@pytest.fixture(scope='module')
def document():
    return legend.load(STYLES)


@pytest.fixture(scope='module')
def details():
    return gen.load_style_files(STYLES)[2]


@pytest.fixture(scope='module')
def icon_keys():
    tree = yaml.safe_load((MODEL / 'generated' / 'categories.yaml').read_text())
    entries = yaml.safe_load((STYLES / 'icons.yaml').read_text())
    palettes = yaml.safe_load((STYLES / 'palettes.yaml').read_text())
    return icons.build(tree, entries, STYLES / 'icons', palettes)[2]


def shown(document, theme, styles, details, classifier, icon_keys, lang='de'):
    return legend.groups(document, theme, styles, details, lang,
                         classifier=classifier, icon_keys=icon_keys)


def entries(groups):
    return [entry for group in groups for entry in group.entries]


# --- legend.yaml ---------------------------------------------------------

def checked(document, styles, details, classifier, icon_keys):
    return legend.check(document, styles, details, classifier, icon_keys)


def test_the_real_legend_passes_its_checks(document, styles, details, classifier, icon_keys):
    assert checked(document, styles, details, classifier, icon_keys) == []


def edited(document, entry):
    out = copy.deepcopy(document)
    out['groups'][0]['entries'].append(entry)
    return out


@pytest.mark.parametrize(('entry', 'message'), [
    ({'class': 'cls_road_nonexistent', 'text': 'legend.motorway'}, 'no class'),
    ({'class': ['cls_road_motorway', 'cls_road_*_nonexistent'], 'text': 'legend.motorway'},
     "no class 'cls_road_*_nonexistent'"),
    ({'class': 'cls_road_motorway'}, 'needs a text'),
    ({'class': 'cls_road_motorway', 'text': 'legend.nonexistent'}, 'not in lib/messages.yaml'),
    ({'category': 'cat_nonexistent'}, 'no category'),
    ({'category': 'cat_poi_shopping_vending'}, 'draws no icon'),
    ({'class': 'cls_road_motorway', 'category': 'cat_poi_health_hospital'}, 'a class or a category'),
    ({'class': 'cls_road_motorway', 'text': 'legend.motorway', 'colour': 'red'}, 'is not class'),
])
def test_a_wrong_entry_is_refused(document, styles, details, classifier, icon_keys,
                                  entry, message):
    errors = checked(edited(document, entry), styles, details, classifier, icon_keys)
    assert any(message in error for error in errors), errors


def test_a_class_not_drawn_at_the_legends_zoom_is_refused(document, styles, details,
                                                          classifier, icon_keys):
    """It would be an entry with a text and nothing beside it. The building
    starts at z13."""
    entry = {'class': 'cls_building', 'text': 'legend.building', 'zoom': 10}
    errors = checked(edited(document, entry), styles, details, classifier, icon_keys)
    assert any('draws nothing at z10' in error for error in errors), errors


def test_an_icons_group_shows_no_classes(document, styles, details, classifier, icon_keys):
    out = copy.deepcopy(document)
    group = next(g for g in out['groups'] if g.get('icons') == 'cat_poi_food')
    group['entries'] = [{'class': 'cls_road_motorway', 'text': 'legend.motorway'}]
    errors = checked(out, styles, details, classifier, icon_keys)
    assert any('an icons group shows icons' in error for error in errors), errors


# --- the legend shows everything the map draws ---------------------------

def without(document, test):
    """`document` with every group and entry `test` is true of removed."""
    out = copy.deepcopy(document)
    out['groups'] = [group for group in out['groups'] if not test(group)]
    for group in out['groups']:
        group['entries'] = [entry for entry in group.get('entries') or [] if not test(entry)]
    return out


def test_a_class_the_map_draws_and_no_entry_names_is_refused(document, styles, details,
                                                             classifier, icon_keys):
    """The failure is silent otherwise: a legend that leaves out what the
    map draws looks complete. Here the bridges: one entry stands for every
    road's bridge, and without it none is named."""
    out = without(document, lambda e: e.get('text') == 'legend.bridge')
    errors = checked(out, styles, details, classifier, icon_keys)
    assert 'legend.yaml: no entry shows cls_road_motorway_bridge' in errors
    assert 'legend.yaml: no entry shows cls_road_path_bridge' in errors


def test_a_place_needs_an_entry_too(document, styles, details, classifier, icon_keys):
    """A place has no geometry; its name is what the map draws."""
    out = without(document, lambda e: e.get('class') == 'cls_place_city')
    errors = checked(out, styles, details, classifier, icon_keys)
    assert errors == ['legend.yaml: no entry shows cls_place_city']


def test_an_icon_the_map_draws_and_no_group_holds_is_refused(document, styles, details,
                                                             classifier, icon_keys):
    out = without(document, lambda g: g.get('icons') == 'cat_poi_food')
    errors = checked(out, styles, details, classifier, icon_keys)
    assert 'legend.yaml: no group shows the icon of cat_poi_food_restaurant' in errors


def test_an_icon_the_map_never_draws_needs_no_entry(styles, classifier, icon_keys):
    """A city has an icon, for the search; on the map its class has no
    marker and it is a name. A legend of icons the map never shows would be
    as wrong as one that misses some."""
    can_draw = legend.iconic(classifier, styles)
    assert 'cat_geography_places_city' in icon_keys
    assert 'cat_geography_places_city' not in can_draw
    assert 'cat_poi_food_restaurant' in can_draw


@pytest.mark.parametrize('detail', ['std', 'max'])
def test_every_icon_a_theme_draws_is_shown_once(document, styles, details, classifier,
                                                icon_keys, detail):
    drawn = legend.drawn_icons(details, detail, classifier, icon_keys,
                               legend.iconic(classifier, styles))
    keys = [entry.icon for entry in entries(shown(document, Theme('default', detail), styles,
                                                  details, classifier, icon_keys))
            if entry.icon]
    assert sorted(keys) == sorted(set(drawn.values()))


def test_the_compiler_refuses_a_wrong_legend(tmp_path, classifier, params):
    import shutil

    styles_dir = tmp_path / 'styles'
    shutil.copytree(STYLES, styles_dir)
    document = edited(legend.load(styles_dir), {'class': 'cls_road_nonexistent', 'text': 'x'})
    (styles_dir / legend.LEGEND).write_text(yaml.safe_dump(document))
    with pytest.raises(gen.GenerationError, match='no class'):
        gen.generate('small', styles_dir, tmp_path / 'out', {}, '0,0,1,1', params,
                     classifier, {})


# --- what a theme shows --------------------------------------------------

def test_a_theme_shows_only_what_its_detail_draws(document, styles, details, classifier,
                                                   icon_keys):
    shown_min = entries(shown(document, Theme('default', 'min'), styles, details,
                              classifier, icon_keys))
    classes = {entry.cls for entry in shown_min}
    assert 'cls_road_motorway' in classes
    assert 'cls_landcover_wood' not in classes
    assert not any(entry.icon for entry in shown_min)


def test_an_icon_is_shown_where_the_details_symbols_reach_its_importance(
        document, styles, details, classifier, icon_keys):
    """Parking is importance 40: `max` draws its icon, `std` starts at 60
    and never does."""
    def names(detail):
        return {entry.text for entry in entries(shown(document, Theme('default', detail),
                                                      styles, details, classifier, icon_keys))
                if entry.icon}
    assert 'Parkplatz' in names('max')
    assert 'Parkplatz' not in names('std')
    assert 'Krankenhaus' in names('std')


def test_a_mode_the_detail_leaves_out_is_not_drawn(document, styles, classifier, icon_keys,
                                                   tmp_path):
    """A detail may draw a class in some modes only (`{glob: [modes]}`); the
    legend must not draw what the detail took away."""
    details = {'roads': {'classes': [{'cls_road_motorway': ['fill']}]}}
    groups = shown(document, Theme('default', 'roads'), styles, details, classifier, icon_keys)
    (motorway,) = entries(groups)
    assert motorway.modes == ('fill',)
    root, _ = legend.build(groups, styles, 'default', tmp_path)
    assert rule_filters(root, 'casing') == []
    assert len(rule_filters(root, 'fill')) == 1


def test_a_class_entry_is_drawn_as_the_first_of_its_classes_the_detail_draws(
        document, styles, classifier, icon_keys):
    """Shops and offices look alike and share an entry; a detail that draws
    only the offices still shows it, in their style."""
    details = {'offices': {'classes': ['cls_landuse_commercial']}}
    (entry,) = entries(shown(document, Theme('default', 'offices'), styles, details,
                             classifier, icon_keys))
    assert (entry.cls, entry.text) == ('cls_landuse_commercial', 'Handel, Büros')


def test_a_place_is_shown_as_its_name_in_its_own_style(document, styles, details, classifier,
                                                       icon_keys, tmp_path):
    groups = shown(document, Theme('default', 'std'), styles, details, classifier, icon_keys)
    rows = [entry for group in groups for entry in (None, *group.entries)]
    city = next(entry for entry in rows if entry and entry.cls == 'cls_place_city')
    assert city.modes == (legend.LABEL,)
    root, _ = legend.build(groups, styles, 'default', tmp_path)
    (rule,) = [rule for rule in root.find("Style[@name='text']").iter('Rule')
               if rule.find('Filter').text == f"[n] = {rows.index(city)} and [shape] = 'label'"]
    text = rule.find('TextSymbolizer')
    expected = styles.paint(styles.properties('cls_place_city', 'label', 15), 'default', 'label')
    assert text.get('size') == str(expected['size'])
    assert text.get('halo-fill') == expected['halo']
    assert text.get('placement') == 'point'


def test_a_shared_icon_is_named_as_its_most_general_category_not_its_group(
        document, styles, details, classifier, icon_keys):
    """The health group's own category draws the hospital's icon; named
    after it, the hospital would be "Gesundheit" under "Gesundheit"."""
    groups = shown(document, Theme('default', 'std'), styles, details, classifier, icon_keys)
    health = next(group for group in groups if group.title == 'Gesundheit')
    names = [entry.text for entry in health.entries]
    assert 'Krankenhaus' in names and 'Gesundheit' not in names
    assert 'Arzt' in names   # legend.yaml names the icon a clinic shares with the doctor


def test_a_category_entry_names_its_icon_where_only_another_category_draws_it(
        document, styles, details, classifier, icon_keys):
    """No point is a plain "vehicles" shop, but car and boat dealers share
    its icon: the icon is named "Fahrzeuge", not "Bootsgeschäft"."""
    names = [entry.text for entry in entries(shown(document, Theme('default', 'max'), styles,
                                                   details, classifier, icon_keys))]
    assert 'Fahrzeuge' in names and 'Bootsgeschäft' not in names


def test_an_icons_group_is_in_alphabetical_order(document, styles, details, classifier,
                                                 icon_keys):
    groups = shown(document, Theme('default', 'max'), styles, details, classifier, icon_keys)
    food = next(group for group in groups if group.title == 'Gastronomie')
    names = [entry.text for entry in food.entries]
    assert names == sorted(names, key=legend._collation)
    assert names.index('Bäckerei') < names.index('Bar')   # an umlaut sorts as its vowel


def test_an_icon_entry_is_named_as_its_category_in_each_language(
        document, styles, details, classifier, icon_keys):
    theme = Theme('default', 'max')
    de = {e.text for e in entries(shown(document, theme, styles, details, classifier, icon_keys))}
    en = {e.text for e in entries(shown(document, theme, styles, details, classifier, icon_keys,
                                        'en'))}
    assert 'Krankenhaus' in de and 'Hospital' in en


# --- the drawing ---------------------------------------------------------

def built(document, theme, styles, details, classifier, icon_keys, tmp_path):
    groups = shown(document, theme, styles, details, classifier, icon_keys)
    return legend.build(groups, styles, theme.palette, tmp_path)


def rule_filters(root, style):
    return [rule.find('Filter').text
            for rule in root.find(f"Style[@name='{style}']").iter('Rule')]


def test_a_filled_class_is_drawn_on_a_box_and_a_road_on_a_line(
        document, styles, details, classifier, icon_keys, tmp_path):
    root, _ = built(document, Theme('default', 'max'), styles, details, classifier,
                    icon_keys, tmp_path)
    fills = rule_filters(root, 'fill')
    assert sum("[shape] = 'area'" in f for f in fills) >= 9   # every area entry
    casings = rule_filters(root, 'casing')
    assert casings and all("[shape] = 'line'" in f for f in casings)


def test_the_symbols_are_the_themes_own_colours(document, styles, details, classifier,
                                                icon_keys, tmp_path):
    """The point of drawing from classes.yaml: the dark legend is dark."""
    for palette in ('default', 'dark'):
        root, _ = built(document, Theme(palette, 'std'), styles, details, classifier,
                        icon_keys, tmp_path)
        colours = {e.get('fill') for e in root.iter('PolygonSymbolizer')}
        assert styles.palettes[palette]['clr_forest'] in colours


def test_the_layers_draw_casings_under_fills_and_text_last(
        document, styles, details, classifier, icon_keys, tmp_path):
    root, _ = built(document, Theme('default', 'std'), styles, details, classifier,
                    icon_keys, tmp_path)
    assert [layer.get('name') for layer in root.iter('Layer')] == [
        'casing', 'fill', 'line', 'icons', 'text']


def test_a_legend_renders_as_wide_as_it_draws(document, styles, details, classifier,
                                              icon_keys, tmp_path):
    mapnik = pytest.importorskip('mapnik')
    theme = Theme('dark', 'std')
    root, height = built(document, theme, styles, details, classifier, icon_keys, tmp_path)
    background = styles.palettes['dark'][gen.BACKGROUND]
    image = mapnik.Image.from_string(legend.render(root, height, background))
    assert image.height() == height
    assert 100 < image.width() < legend.MAX_WIDTH
    # The palette's background, so a dark legend's light text stays
    # readable in a client's white legend panel.
    corner = image.get_pixel_color(image.width() - 1, 0)
    expected = mapnik.Color(background)
    assert (corner.r, corner.g, corner.b) == (expected.r, expected.g, expected.b)


def test_the_contours_are_in_the_legend_of_the_details_that_draw_them(document, styles, details,
                                                                         classifier, icon_keys):
    """A detail that does not list the contours does not draw them, so its
    legend must not list them either -- and must not leave a gap for them."""
    def titles(detail):
        return [group.title for group in shown(document, Theme('default', detail), styles, details,
                                                classifier, icon_keys)]

    assert 'Relief' in titles('topographic')
    assert 'Relief' in titles('max')
    assert 'Relief' not in titles('std')
