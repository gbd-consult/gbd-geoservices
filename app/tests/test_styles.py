"""The style generator.

The generator's job is to refuse. A style file that is wrong produces tiles
that render without an error and show the wrong thing, so every check here
exists because that failure mode is expensive to notice.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from importer import elevation
from renderer import queries
from renderer import styles as gen
from renderer.resolve import Styles
from renderer.styles import Theme

PALETTES = {
    'default': {'clr_land': '#f2efe9', 'forest': '#c8e0b8', 'halo': '#ffffff',
                'halo_radius': 1.5, 'casing_scale': 1.0},
    'dark': {'clr_land': '#14181d', 'forest': '#17251a', 'halo': '#10131a',
             'halo_radius': 1.5, 'casing_scale': 1.0},
}
CLASSES = {
    'fill': {
        'cls_landcover_wood 5': {'polygon-fill': 'forest'},
        'cls_road_primary 8': {'line-color': 'forest', 'line-width': 1.2},
    },
    'label': {
        'cls_landcover_wood 13': {'text': 'name', 'font': 'DejaVu Sans Book', 'size': 10,
                                  'fill': 'forest', 'halo': 'halo', 'halo-radius': 'halo_radius'},
    },
}
LAYERS = [
    {'name': 'landcover', 'mode': 'fill', 'classes': ['cls_landcover_*']},
    {'name': 'roads_fill', 'mode': 'fill', 'classes': ['cls_road_*']},
    {'name': 'labels_area', 'mode': 'label', 'classes': ['cls_landcover_*']},
]
DETAILS = {
    'min': {'classes': ['cls_landcover_*']},
    'std': {'classes': ['cls_landcover_*', 'cls_road_*']},
    'max': {'classes': ['*']},
}
PRESENT = {
    'osm_polygon': {'cls_landcover_wood': 7},
    'osm_line': {'cls_road_primary': 9},
    'osm_label': {'cls_landcover_wood': 3},
    'osm_point': {},
    'osm_building': {},
}


class StubClassifier:
    def __init__(self, classes):
        self.rules = [type('R', (), {'cls': c})() for c in classes]


def with_entries(document, mode, entries):
    """`document` with `entries` added under `mode`."""
    return {**document, mode: {**document.get(mode, {}), **entries}}


@pytest.fixture
def small() -> Styles:
    return Styles(CLASSES, PALETTES)


@pytest.fixture
def classifier() -> StubClassifier:
    return StubClassifier(['cls_landcover_wood', 'cls_road_primary'])


# --- themes and details ---------------------------------------------------

def test_a_theme_name_is_its_palette_and_detail():
    assert Theme('default', 'std').name == 'default_std'
    assert Theme('dark', 'min').name == 'dark_min'
    assert Theme('hico', 'max').name == 'hico_max'


def test_twenty_four_themes_from_eight_palettes_and_three_details(styles):
    names = {t.name for t in gen.themes(styles.palettes, DETAILS)}
    assert len(names) == 24
    assert 'default_std' in names and 'dark_min' in names and 'hico_max' in names


def test_the_serve_palettes_and_serve_details_options_narrow_what_is_compiled(styles):
    """A dev server loads every compiled theme at start, ~0.06 s per Map through pgbouncer."""
    names = {t.name for t in gen.themes(styles.palettes, DETAILS, ['default', 'dark'], ['std'])}
    assert names == {'default_std', 'dark_std'}
    assert len(gen.themes(styles.palettes, DETAILS, None, None)) == len(styles.palettes) * 3


def test_an_unknown_palette_or_detail_in_the_options_is_refused(styles):
    with pytest.raises(gen.GenerationError, match='no such palette blue'):
        gen.themes(styles.palettes, DETAILS, ['blue'], None)
    with pytest.raises(gen.GenerationError, match='no such detail standard'):
        gen.themes(styles.palettes, DETAILS, None, ['standard'])


def test_a_detail_draws_what_it_lists(small):
    known = small.classes
    assert set(gen.detail_modes(DETAILS, 'min', known)) == {'cls_landcover_wood'}
    assert set(gen.detail_modes(DETAILS, 'std', known)) == {'cls_landcover_wood', 'cls_road_primary'}
    assert set(gen.detail_modes(DETAILS, 'max', known)) == known


def test_a_detail_can_draw_a_class_in_some_modes_only():
    """A detail can draw the building and its number, not its name.
    Entries add up: a plain glob wins over a restricted one."""
    details = {'min': {'classes': [{'cls_landcover_wood': ['fill']}]},
               'std': {'classes': [{'cls_landcover_wood': ['fill']}, 'cls_landcover_*']},
               'max': {'classes': [{'cls_landcover_wood': ['fill']}, {'cls_landcover_wood': ['label']}]}}
    known = {'cls_landcover_wood'}
    assert gen.detail_modes(details, 'min', known) == {'cls_landcover_wood': frozenset({'fill'})}
    assert gen.detail_modes(details, 'std', known) == {'cls_landcover_wood': None}
    assert gen.detail_modes(details, 'max', known) == {'cls_landcover_wood': frozenset({'fill', 'label'})}


def test_a_detail_without_a_mode_does_not_draw_it(small, params):
    details = {**DETAILS, 'min': {'classes': [{'cls_landcover_wood': ['fill']}]}}
    root = gen.build('sh', Theme('default', 'min'), small, LAYERS, details, params, PRESENT, '0,0,1,1')
    names = {layer.get('name') for layer in root.iter('Layer')}
    assert any(n.startswith('landcover') for n in names)
    assert not any(n.startswith('labels_area') for n in names)


def test_a_mode_that_is_not_one_is_refused(small, classifier):
    details = {**DETAILS, 'min': {'classes': [{'cls_landcover_wood': ['lable']}]}}
    errors, _ = gen.check(small, LAYERS, details, classifier)
    assert any("names 'lable', which is not a mode" in e for e in errors), errors


def test_a_detail_without_symbols_has_none():
    details = {'min': {'symbols': {'icons': {100: 12, 80: 14}, 'labels': {100: 15}}},
               'std': {'symbols': {'icons': {60: 15}}},
               'max': {}}
    assert gen.detail_symbols(details, 'min') == {'icons': {100: 12, 80: 14}, 'labels': {100: 15}}
    assert gen.detail_symbols(details, 'std') == {'icons': {60: 15}, 'labels': {}}
    assert gen.detail_symbols(details, 'max') == {'icons': {}, 'labels': {}}


def test_extends_is_gone(small, classifier):
    # A detail lists all it draws; a leftover `extends` would silently
    # draw less than whoever wrote it expects.
    details = {**DETAILS, 'std': {**DETAILS['std'], 'extends': 'min'}}
    errors, _ = gen.check(small, LAYERS, details, classifier)
    assert any('details.yaml std: extends is not one of' in e for e in errors), errors


def test_a_symbol_starts_at_the_highest_entry_its_importance_reaches():
    zooms = {100: 12, 80: 14, 20: 17}
    assert [gen.symbol_start(zooms, i) for i in (100, 99, 80, 79, 20, 19)] == [12, 14, 14, 17, 17, None]


def test_the_real_details_draw_more_icons_the_more_they_draw():
    import yaml

    from importer.run import STYLES

    details = yaml.safe_load((STYLES / 'details.yaml').read_text())
    assert gen.detail_symbols(details, 'min') == {'icons': {}, 'labels': {}}
    std, most = gen.detail_symbols(details, 'std'), gen.detail_symbols(details, 'max')
    assert std['icons'] and min(most['icons']) < min(std['icons'])
    for kind in gen.SYMBOLS:
        for importance in range(1, 101):
            here, there = gen.symbol_start(std[kind], importance), gen.symbol_start(most[kind], importance)
            assert here is None or there <= here, (kind, importance)


# --- scale ranges --------------------------------------------------------

def test_scale_range_brackets_the_zooms():
    # A rule applies while min <= scale < max, and the scale halves per
    # zoom. The bounds sit between neighbouring zooms, not on them.
    minimum, maximum = gen.scale_range(10, 12, 18)
    assert queries.scale_denominator(13) < minimum < queries.scale_denominator(12)
    assert queries.scale_denominator(10) < maximum < queries.scale_denominator(9)


def test_a_boundary_is_never_an_equality():
    """Six decimals in the XML, and a float comparison in Mapnik.

    Writing the neighbouring zoom's exact denominator means rounding the
    last digit decides whether a rule covers one more zoom: cls_poi_cafe drew
    from z15 against a style that said 16.
    """
    for low in range(1, 18):
        _, maximum = gen.scale_range(low, low, 18)
        assert maximum != queries.scale_denominator(low - 1)
        assert maximum != queries.scale_denominator(low)
        # Survives being written with six decimals and read back.
        written = float(f'{maximum:.6f}')
        assert queries.scale_denominator(low) < written
        assert queries.scale_denominator(low - 1) > written


def test_each_zoom_is_covered_by_exactly_one_rule_range():
    # Adjacent ranges must not overlap or leave a gap after rounding.
    ranges = [gen.scale_range(lo, hi, 18)
              for lo, hi in [(0, 6), (7, 9), (10, 12), (13, 18)]]
    for zoom in range(19):
        scale = float(f'{queries.scale_denominator(zoom):.6f}')
        hits = [1 for lo, hi in ranges
                if (lo is None or scale >= lo) and (hi is None or scale < hi)]
        assert sum(hits) == 1, zoom


def test_scale_range_is_open_at_the_ends():
    assert gen.scale_range(0, 6, 18)[1] is None      # nothing below z0
    assert gen.scale_range(13, 18, 18)[0] is None    # nothing above z18


def test_a_zoom_is_in_exactly_one_range():
    ranges = [gen.scale_range(lo, hi, 18) for lo, hi in [(0, 6), (7, 9), (10, 12), (13, 18)]]
    for zoom in range(19):
        scale = queries.scale_denominator(zoom)
        matching = [1 for lo, hi in ranges
                    if (lo is None or scale >= lo) and (hi is None or scale < hi)]
        assert sum(matching) == 1, zoom


# --- the checks ----------------------------------------------------------

def test_a_styled_class_that_no_rule_produces_is_an_error(small):
    errors, _ = gen.check(small, LAYERS, DETAILS, StubClassifier(['cls_road_primary']))
    assert any('cls_landcover_wood' in e and 'no rule produces' in e for e in errors)


def test_a_classified_class_nobody_styles_is_only_a_warning(small, classifier):
    classifier.rules.append(type('R', (), {'cls': 'poi_bench'})())
    errors, warnings = gen.check(small, LAYERS, DETAILS, classifier)
    assert not errors
    assert any('poi_bench' in w for w in warnings)


def test_a_layer_glob_matching_nothing_is_an_error(small, classifier):
    layers = [*LAYERS, {'name': 'x', 'mode': 'fill', 'classes': ['nothing_*']}]
    errors, _ = gen.check(small, layers, DETAILS, classifier)
    assert any("'nothing_*' matches no class" in e for e in errors)


def test_a_detail_glob_matching_nothing_is_an_error(small, classifier):
    details = {**DETAILS, 'min': {'classes': ['cls_landcover_*', 'gone_*']}}
    errors, _ = gen.check(small, LAYERS, details, classifier)
    assert any("'gone_*' matches no class" in e for e in errors)


def test_a_colour_literal_is_an_error(classifier):
    broken = Styles(with_entries(CLASSES, 'fill', {'cls_road_primary 8': {'line-color': '#ff0000'}}),
                    PALETTES)
    errors, _ = gen.check(broken, LAYERS, DETAILS, classifier)
    assert any('literal' in e for e in errors)


def test_a_token_missing_from_one_palette_is_an_error(classifier):
    palettes = {'default': PALETTES['default'],
                'dark': {k: v for k, v in PALETTES['dark'].items() if k != 'forest'}}
    broken = Styles(CLASSES, palettes)
    errors, _ = gen.check(broken, LAYERS, DETAILS, classifier)
    assert any("token 'forest' is missing from dark" in e for e in errors)


def test_a_class_moved_earlier_than_its_rows_is_an_error(small, classifier):
    """The rule would fire where the import wrote no rows: it draws nothing.

    `minzoom` and `minzoom_label` come from classes.yaml at import, so a
    start moved earlier needs a re-import, and nothing else would say so.
    """
    imported = {'cls_landcover_wood': [9, 13], 'cls_road_primary': [8, None]}
    errors, _ = gen.check(small, LAYERS, DETAILS, classifier, imported=imported)
    assert errors == ['cls_landcover_wood is drawn from z5, but was imported as drawn '
                      'from z9: re-import the area']


def test_text_added_since_the_import_is_an_error(small, classifier):
    imported = {'cls_landcover_wood': [5, None], 'cls_road_primary': [8, None]}
    errors, _ = gen.check(small, LAYERS, DETAILS, classifier, imported=imported)
    assert errors == ['cls_landcover_wood is labelled from z13, but was imported as labelled '
                      'never: re-import the area']


def test_a_class_moved_later_than_its_rows_is_fine(small, classifier):
    # The rule starts later; the rows cost a few reads until the next import.
    imported = {'cls_landcover_wood': [3, 11], 'cls_road_primary': [8, None]}
    errors, _ = gen.check(small, LAYERS, DETAILS, classifier, imported=imported)
    assert errors == []


def test_a_missing_font_is_an_error(small, classifier):
    errors, _ = gen.check(small, LAYERS, DETAILS, classifier,
                             faces=frozenset({'Some Other Face'}))
    assert any("font 'DejaVu Sans Book' is not installed" in e for e in errors)


def test_the_checks_pass_on_the_real_files():
    """The whole point: the checked-in style files must generate cleanly.

    They did not on the first run -- eight classes were styled below the
    zoom their own rules produce rows for. The import is the real files'
    own, so this also says that classes.yaml agrees with itself.
    """
    from importer import params as params_module
    from importer import rules as rules_module
    from importer.run import MODEL, STYLES

    real, layers, details = gen.load_style_files(STYLES)
    imported = params_module.load(MODEL, STYLES).style_zooms()
    errors, _ = gen.check(real, layers, details, rules_module.load(MODEL), imported=imported)
    assert errors == []


# --- the XML -------------------------------------------------------------

def build_one(small, classifier, params, detail='max'):
    return gen.build('sh', Theme('default', detail), small, LAYERS, DETAILS,
                        params, PRESENT, '0,0,1,1')


def test_the_ampersand_in_the_query_is_escaped(small, classifier, params):
    # `geom && !bbox!` in an attribute or element text must not break the
    # document. A serialiser cannot get this wrong; a template can.
    root = build_one(small, classifier, params)
    text = ET.tostring(root, encoding='unicode')
    assert '&amp;&amp;' in text
    ET.fromstring(text)      # parses, which is the actual claim


def test_the_datasource_carries_no_credential(small, classifier, params):
    root = build_one(small, classifier, params)
    names = {p.get('name') for p in root.iter('Parameter')}
    assert names == {'type', 'table', 'geometry_field', 'srid', 'extent', 'max_size'}
    text = ET.tostring(root, encoding='unicode').lower()
    for secret in ('password', 'dbname', 'host=', 'user='):
        assert secret not in text


def test_the_background_is_the_palette_land(small, classifier, params):
    assert build_one(small, classifier, params).get('background-color') == '#f2efe9'
    dark = gen.build('sh', Theme('dark', 'max'), small, LAYERS, DETAILS,
                        params, PRESENT, '0,0,1,1')
    assert dark.get('background-color') == '#14181d'


def test_a_detail_drops_the_classes_it_does_not_draw(small, classifier, params):
    minimal = gen.build('sh', Theme('default', 'min'), small, LAYERS, DETAILS,
                           params, PRESENT, '0,0,1,1')
    text = ET.tostring(minimal, encoding='unicode')
    assert 'cls_landcover_wood' in text
    assert 'cls_road_primary' not in text


def test_the_buffer_is_on_the_layers_not_the_map(small, classifier, params):
    """A Map buffer widens the extent `avoid-edges` is measured against, so
    icons and labels crossing a tile edge were still drawn -- by one tile,
    while its neighbour dropped them in a collision, leaving half an icon."""
    root = gen.build('sh', Theme('default', 'max'), small, LAYERS, DETAILS,
                     params, PRESENT, '0,0,1,1', buffer_px=48)
    assert root.get('buffer-size') == '0'
    layers = root.findall('Layer')
    assert layers
    assert {layer.get('buffer-size') for layer in layers} == {'48'}


def test_a_none_token_leaves_the_class_out_of_that_palette_only(params):
    """A palette leaves out what it paints `none`: not a transparent rule but
    no rule, so a layer left without rules is not compiled either. Otherwise
    every theme would query the contours of every tile to draw nothing."""
    palettes = {**PALETTES, 'dark': {**PALETTES['dark'], 'forest': 'none'}}
    dark = gen.build('sh', Theme('dark', 'max'), Styles(CLASSES, palettes), LAYERS, DETAILS,
                     params, PRESENT, '0,0,1,1')
    plain = gen.build('sh', Theme('default', 'max'), Styles(CLASSES, palettes), LAYERS, DETAILS,
                      params, PRESENT, '0,0,1,1')
    assert dark.findall('Layer') == [] and dark.findall('Style') == []
    assert plain.findall('Layer')
    assert 'none' not in ET.tostring(dark, encoding='unicode')


def test_only_topographic_and_max_read_the_contours(styles, params):
    from importer.run import STYLES

    _, layers, details = gen.load_style_files(STYLES)
    present = {'osm_contour': {cls: 1 for cls in elevation.classes()}}
    tables = {}
    for detail in ('topographic', 'max', 'std'):
        root = gen.build('sh', Theme('default', detail), styles, layers, details, params, present,
                         '0,0,1,1')
        tables[detail] = {p.text for p in root.iter('Parameter') if p.get('name') == 'table'}
    assert any('osm_contour' in table for table in tables['topographic'])
    assert any('osm_contour' in table for table in tables['max'])
    assert not any('osm_contour' in table for table in tables['std'])


def test_each_contour_level_reads_only_its_own_lines(styles, params):
    """A z9 tile draws the 1000 m lines. Had one layer read every level, the
    query -- `minzoom <= 9` on the GiST scan -- would read every 50 m line in
    the tile to keep the few 1000 m ones: the same picture, at the cost of
    the whole table under it."""
    from importer.run import STYLES

    _, layers, details = gen.load_style_files(STYLES)
    present = {'osm_contour': {cls: 1 for cls in elevation.classes()}}
    root = gen.build('sh', Theme('default', 'topographic'), styles, layers, details, params, present,
                     '0,0,1,1')
    tables = [p.text for p in root.iter('Parameter')
              if p.get('name') == 'table' and 'osm_contour' in p.text]
    assert len(tables) == 2 * len(elevation.classes())        # lines and heights per level
    for table in tables:
        assert sum(cls in table.replace("'", ' ').split() for cls in elevation.classes()) == 1, table


def test_symbolizers_follow_the_properties(small, classifier, params):
    root = build_one(small, classifier, params)
    kinds = {e.tag for e in root.iter() if e.tag.endswith('Symbolizer')}
    assert kinds == {'PolygonSymbolizer', 'LineSymbolizer', 'TextSymbolizer'}


def test_the_text_expression_names_a_column(small, classifier, params):
    root = build_one(small, classifier, params)
    for element in root.iter('TextSymbolizer'):
        assert element.text in ('[name]', '[label]')


ICON_DETAILS = {**DETAILS, 'max': {**DETAILS['max'],
                                    'symbols': {'icons': {100: 12, 40: 15}, 'labels': {40: 17}}}}


def icon_theme(icons, extra=None, details=ICON_DETAILS, detail='max'):
    classes = with_entries(CLASSES, 'marker', {
        'cls_poi_food': {'icon': True, 'size': 27},
        'cls_poi_food 18': {'size': 54},
        'cls_poi_bus': {'icon': True, 'size': 27},
        **(extra or {})})
    layers = [*LAYERS, {'name': 'pois', 'mode': 'marker', 'classes': ['cls_poi_*']}]
    present = {**PRESENT, 'osm_point': {'cls_poi_food': 3, 'cls_poi_bus': 2}}
    from importer import params as params_module
    from importer.run import MODEL, STYLES
    return gen.build('sh', Theme('default', detail), Styles(classes, PALETTES), layers, details,
                     params_module.load(MODEL, STYLES), present, '0,0,1,1', icons=icons)


def marker_rules(root):
    style = next(s for s in root.iter('Style') if s.get('name').startswith('pois'))
    return list(style.iter('Rule'))


def test_an_icon_marker_reads_the_rows_own_category():
    """The file is named by the row, not by the rule: one rule per class
    draws every category's icon, and inheritance was resolved into the files
    when they were written."""
    root = icon_theme(Path('/data/styles/icons/abc'))
    markers = list(root.iter('MarkersSymbolizer'))
    files = {m.get('file') for m in markers}
    # One directory per palette: the colour is baked into the file.
    assert files == {'/data/styles/icons/abc/default/[icon].svg'}
    icons = markers
    # Mapnik fits width/height to the drawn shape's bounding box, which
    # stretched each icon to a different non-integer scale: blurred.
    assert all(m.get('width') is None and m.get('height') is None for m in icons)
    assert {m.get('transform') for m in icons} == {None, 'scale(2)'}
    # A marker fill would recolour the white disc and the white icon too.
    assert all(m.get('fill') is None for m in icons)
    tables = [p.text for p in root.iter('Parameter') if p.get('name') == 'table']
    assert any('icon is not null' in text for text in tables)


def test_a_marker_that_is_not_an_icon_is_refused():
    # There are no shapes: `icon: false` would draw nothing and say nothing.
    with pytest.raises(gen.GenerationError, match='a marker is an icon'):
        icon_theme(Path('/i'), {'cls_poi_bus': {'icon': False}})


def test_an_icon_marker_without_an_icon_directory_is_refused():
    with pytest.raises(gen.GenerationError, match='icon directory'):
        icon_theme(None)


def test_a_detail_without_icons_has_no_marker_layer():
    root = icon_theme(Path('/i'), details=DETAILS)
    assert not [layer for layer in root.iter('Layer') if layer.get('name').startswith('pois')]


def test_the_detail_class_list_does_not_select_icons():
    # `min` lists no POI class; its `symbols` alone decide.
    details = {**DETAILS, 'min': {**DETAILS['min'], 'symbols': {'icons': {100: 14}}}}
    root = icon_theme(Path('/i'), details=details, detail='min')
    assert {r.find('Filter').text for r in marker_rules(root)} >= {"[class] = 'cls_poi_food'"}


def test_icons_start_at_the_earliest_importance_not_at_the_style_zoom():
    """classes.yaml gives the icon no zoom; the detail draws importance 100
    from z12. The rule has to cover z12 or the query's rows are never drawn."""
    rules = [r for r in marker_rules(icon_theme(Path('/i')))
             if r.find('Filter').text == "[class] = 'cls_poi_food'"]
    first = max(float(r.find('MaxScaleDenominator').text) for r in rules)
    assert queries.scale_denominator(12) < first < queries.scale_denominator(11)
    table = next(p.text for layer in icon_theme(Path('/i')).iter('Layer')
                 if layer.get('name').startswith('pois')
                 for p in layer.iter('Parameter') if p.get('name') == 'table')
    assert 'then 40 ' in table and 'then 100 ' in table


def test_an_area_label_yields_to_the_areas_icon():
    """An airport named twice -- by its area label and by its icon -- is
    what this prevents: the area label is read only for rows whose icon is
    not drawn yet at the tile's zoom."""
    marker = {'cls_landcover_wood': {'icon': True, 'size': 27}}
    layers_with_wood = [*LAYERS, {'name': 'pois', 'mode': 'marker', 'classes': ['*']}]
    root = gen.build('sh', Theme('default', 'max'),
                     Styles(with_entries(CLASSES, 'marker', marker), PALETTES), layers_with_wood,
                     ICON_DETAILS, _params(), PRESENT, '0,0,1,1', icons=Path('/i'))
    table = next(p.text for layer in root.iter('Layer') if layer.get('name') == 'labels_area_osm_label'
                 for p in layer.iter('Parameter') if p.get('name') == 'table')
    floor = queries.importance_floor(((40, 15), (100, 12)))
    assert f"class not in ('cls_landcover_wood') or icon is null or importance < {floor}" in table


def test_a_marker_entry_no_layer_draws_does_not_hide_the_label():
    # Without a marker layer for it there is no icon to yield to.
    marker = {'cls_landcover_wood': {'icon': True, 'size': 27}}
    root = gen.build('sh', Theme('default', 'max'),
                     Styles(with_entries(CLASSES, 'marker', marker), PALETTES), LAYERS,
                     ICON_DETAILS, _params(), PRESENT, '0,0,1,1', icons=Path('/i'))
    table = next(p.text for layer in root.iter('Layer') if layer.get('name') == 'labels_area_osm_label'
                 for p in layer.iter('Parameter') if p.get('name') == 'table')
    assert 'importance' not in table


def test_a_label_is_drawn_from_its_own_importance_floor():
    """The label's zoom is the detail's, per importance, not a key in
    classes.yaml: below its floor the query hands the row no name, and the
    rule for a row without one draws the bare icon."""
    table = next(p.text for layer in icon_theme(Path('/i')).iter('Layer')
                 if layer.get('name').startswith('pois')
                 for p in layer.iter('Parameter') if p.get('name') == 'table')
    label_floor = queries.importance_floor(((40, 17),))
    assert f'case when importance >= {label_floor} then name end as name' in table


def test_an_icon_with_text_is_one_shield_or_a_bare_icon():
    """Two symbolizers would each run their own collision test, and a label
    whose icon lost its spot would stand there alone."""
    text = {'cls_poi_food 17': {'text': 'name', 'font': 'DejaVu Sans Book',
                                'text-size': 9, 'fill': 'forest', 'dy': 17}}
    rules = marker_rules(icon_theme(Path('/i'), text))
    shields = [r for r in rules if r.find('ShieldSymbolizer') is not None]
    assert shields
    for rule in shields:
        assert rule.find('Filter').text == "[class] = 'cls_poi_food' and [name] != null"
        assert rule.find('TextSymbolizer') is None and rule.find('MarkersSymbolizer') is None
        shield = rule.find('ShieldSymbolizer')
        assert shield.get('file') == '/i/default/[icon].svg'
        assert shield.text == '[name]'
        # `size` is the icon's; the text's is `text-size`.
        assert shield.get('size') == '9'
        assert shield.get('unlock-image') == 'true'
    # Without a name, the icon alone, at the same zooms.
    bare = [r for r in rules if r.find('Filter').text.endswith('[name] = null')]
    assert len(bare) == len(shields)
    assert all(r.find('MarkersSymbolizer') is not None for r in bare)
    scaled = [r.find('ShieldSymbolizer').get('transform') for r in shields]
    assert scaled == [None, 'scale(2)']


@pytest.mark.parametrize('symbols,message', [
    ({'icons': {100: 12, 80: 11}}, 'icons draw importance 100 from z12, later than 80'),
    ({'icons': {0: 12}}, 'not 1-100'),
    ({'icons': {101: 12}}, 'not 1-100'),
    ({'icons': {100: -1}}, 'not a zoom'),
    ({'icons': {100: 12}, 'labels': {100: 15, 80: 14}}, 'labels draw importance 100 from z15'),
    # Drawn with its icon or not at all, so it cannot start first.
    ({'icons': {100: 14}, 'labels': {100: 12}}, 'labels draw importance 100 from z12, but its icon from z14'),
    ({'icons': {100: 14}, 'labels': {60: 16}}, 'labels draw importance 60 from z16, but its icon never'),
    # Between keys: 80-99 get their icon at z15 and their label at z14.
    ({'icons': {100: 12, 80: 15}, 'labels': {60: 14}}, 'importance 80 from z14, but its icon from z15'),
    ({'icon': {100: 12}}, "symbols.icon is not one of icons, labels"),
])
def test_bad_symbols_are_refused(small, classifier, symbols, message):
    details = {**DETAILS, 'max': {**DETAILS['max'], 'symbols': symbols}}
    errors, _ = gen.check(small, LAYERS, details, classifier)
    assert any(message in error for error in errors), errors


def test_a_key_a_detail_does_not_have_is_refused(small, classifier):
    # `icons` where `symbols.icons` is meant would leave the detail without
    # icons, and nothing else would say so.
    details = {**DETAILS, 'max': {**DETAILS['max'], 'icons': {100: 12}}}
    errors, _ = gen.check(small, LAYERS, details, classifier)
    assert any("details.yaml max: icons is not one of" in error for error in errors), errors


def test_a_fill_layer_never_reads_osm_label(small, classifier, params):
    """osm_label has no `minzoom` column.

    Only found by loading the XML in Mapnik: a fill layer over
    cls_landcover_wood also matched the osm_label rows for the same class and
    asked them for a column they do not have.
    """
    root = build_one(small, classifier, params)
    for layer in root.iter('Layer'):
        table = next(p.text for p in layer.iter('Parameter') if p.get('name') == 'table')
        if layer.get('name', '').startswith(('landcover', 'roads_fill')):
            assert 'osm_label' not in table


# --- one file per TileMatrixSet ------------------------------------------

def _generate(tmp_path, classifier, sets):
    import shutil

    from importer.run import STYLES

    styles_dir = tmp_path / 'styles'
    shutil.copytree(Path(STYLES), styles_dir)
    return gen.generate('small', styles_dir, tmp_path / 'out', PRESENT,
                        '0,0,1,1', _params(), classifier, sets)


def _params():
    from importer import params as params_module
    from importer.run import MODEL, STYLES

    return params_module.load(MODEL, STYLES)


@pytest.fixture
def two_sets():
    from renderer import matrix

    return matrix.load(['GoogleMapsCompatible', 'DE_EPSG_25832_ADV'], {
        'GoogleMapsCompatible': {'crs': 'EPSG:3857',
                                     'origin': [-20037508.342789244, 20037508.342789244],
                                     'span': 40075016.685578488, 'levels': 19, 'centre_lat': 0},
        'DE_EPSG_25832_ADV': {'crs': 'EPSG:25832', 'origin': [-46133.17, 6301219.54],
                              'span': 1252344.2714243277, 'levels': 15, 'centre_lat': 51.0},
    })


def test_a_theme_no_longer_selected_leaves_no_xml_behind(tmp_path, two_sets):
    """A dev server loads every XML in the set's directory; one left over
    from a wider compile would be loaded and served from stale styles."""
    import shutil

    from importer import rules as rules_module
    from importer.run import MODEL, STYLES

    classifier = rules_module.load(MODEL)
    styles_dir = tmp_path / 'styles'
    shutil.copytree(Path(STYLES), styles_dir)
    gen.generate('small', styles_dir, tmp_path / 'out', PRESENT, '0,0,1,1', _params(),
                 classifier, two_sets)
    gen.generate('small', styles_dir, tmp_path / 'out', PRESENT, '0,0,1,1', _params(),
                 classifier, two_sets, only_palettes=['default'], only_details=['std'])
    for directory in (tmp_path / 'out').iterdir():
        assert [p.name for p in directory.glob('*.xml')] == ['default_std.xml']


def test_a_theme_is_compiled_once_per_set(tmp_path, two_sets):
    """Forty-eight themes, but a file per theme *per grid*.

    `metres_factor` is a constant of the set and is baked into both the
    rule scale denominators and the datasource's zoom expression, so one
    file cannot serve two grids.
    """
    from importer import rules as rules_module
    from importer.run import MODEL

    written = _generate(tmp_path, rules_module.load(MODEL), two_sets)
    assert len(written) == 96
    for identifier in ('GoogleMapsCompatible', 'DE_EPSG_25832_ADV'):
        directory = tmp_path / 'out' / identifier
        assert len(list(directory.glob('*.xml'))) == 48


def test_each_sets_xml_carries_its_own_metres_factor(tmp_path, two_sets):
    """The regression that made this a per-set file at all.

    Every EPSG:25832 level resolved exactly one zoom too fine while a
    single 3857 XML served both -- level 8, the configured pre-cache
    depth, asked for `minzoom <= 13` and so read the full table where
    `_z12` was meant. Nothing failed; the tile was simply a zoom more
    detailed and a band table more expensive than the design says.
    """
    import re

    from importer import rules as rules_module
    from importer.run import MODEL

    _generate(tmp_path, rules_module.load(MODEL), two_sets)
    numerator = re.compile(r'round\(log\(2, \(([0-9.]+) /')
    for tms in two_sets.values():
        xml = (tmp_path / 'out' / tms.identifier / 'default_std.xml').read_text()
        found = sorted({float(v) for v in numerator.findall(xml)})
        expected = queries.UNITS_PER_PIXEL_Z0 * tms.metres_factor
        assert found == pytest.approx([expected]), tms.identifier


@pytest.mark.parametrize('level,zoom', [(0, 4), (6, 10), (8, 12), (12, 16)])
def test_a_utm_level_resolves_to_the_3857_zoom_of_the_same_pixel_size(
        db, two_sets, level, zoom):
    """The arithmetic the per-set file exists to get right, end to end.

    Level 8 must land on z12: a non-3857 set is pre-cached to the ground
    resolution of 3857's z12 (DESIGN.md "Cache and pre-cache"), and
    `precache: {DE_EPSG_25832_ADV: 8}` is that rule's answer. It is only the
    answer once the latitude correction is applied.
    """
    tms = two_sets['DE_EPSG_25832_ADV']
    # What Mapnik reports for this level: the map is in true metres.
    scale = tms.resolution(level) / queries.STANDARDIZED_PIXEL_SIZE_M
    expression = queries.zoom_expression(tms.metres_factor).replace(
        '!scale_denominator!', repr(scale))
    assert db.execute(f'select {expression}').fetchone()[0] == zoom


def test_a_name_that_is_both_a_palette_and_a_detail_is_refused(classifier):
    """A URL names a theme by its palette or its detail alone, so `max`
    would mean two themes."""
    palettes = {**PALETTES, 'max': PALETTES['default']}
    errors, _ = gen.check(Styles(CLASSES, palettes), LAYERS, DETAILS, classifier)
    assert "'max' is both a palette and a detail" in errors


def test_a_palette_missing_a_token_only_the_generator_reads_is_refused(classifier):
    """`land` and `casing_scale` are named by no entry in classes.yaml, so
    the entry walk never sees them.

    Unchecked, a palette without one fails with a bare KeyError out of
    `build` or `paint` -- halfway through writing files, with no mention of
    which palette is wrong.
    """
    for token in ('clr_land', 'casing_scale'):
        palettes = {name: {k: v for k, v in tokens.items() if k != token}
                    for name, tokens in PALETTES.items()}
        errors, _ = gen.check(Styles(CLASSES, palettes), LAYERS, DETAILS, classifier)
        assert any(token in e and 'every palette must' in e for e in errors), token


def test_the_real_palettes_define_both(styles):
    for palette, tokens in styles.palettes.items():
        assert 'clr_land' in tokens and 'casing_scale' in tokens, palette


# --- the style run at app start -------------------------------------------

@pytest.fixture
def style_run(monkeypatch, tmp_path):
    """`gen.run` with the database and the file work faked, recording what it
    would have scanned or written."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from importer import meta
    from importer import params as params_module
    from importer import rules as rules_module
    from lib import db
    from renderer import icons as icons_module
    from renderer import legend as legend_module
    from renderer import matrix

    drawn = {'cat_1': 'icon_1.clr_1'}
    stored = {}
    calls = []

    @contextmanager
    def connection():
        yield object()

    monkeypatch.setattr(db, 'connection', connection)
    monkeypatch.setattr(meta, 'read', lambda conn, schema: dict(stored))
    monkeypatch.setattr(meta, 'update', lambda conn, schema, **values: stored.update(values))
    monkeypatch.setattr(params_module, 'load', lambda *a: None)
    monkeypatch.setattr(rules_module, 'load', lambda *a: SimpleNamespace(categories=None))
    monkeypatch.setattr(matrix, 'load', lambda: {})
    monkeypatch.setattr(icons_module, 'write', lambda *a: (tmp_path, drawn))
    monkeypatch.setattr(icons_module, 'update_points',
                        lambda conn, schema, mapping: calls.append('icons') or 1)
    monkeypatch.setattr(db, 'table_classes',
                        lambda conn, schema, tables: calls.append('count') or {'osm_point': {}})
    monkeypatch.setattr(gen, 'schema_extent', lambda conn, schema: '0,0,1,1')
    monkeypatch.setattr(gen, 'installed_faces', lambda: None)
    monkeypatch.setattr(gen, 'generate', lambda *a, **k: [])
    monkeypatch.setattr(legend_module, 'write', lambda *a, **k: [])
    return stored, calls, icons_module.mapping_key(drawn)


def test_a_style_run_with_nothing_changed_scans_nothing(style_run, tmp_path):
    """The app runs this at every start; on de the icon update and
    the class count were 38 s of it."""
    stored, calls, key = style_run
    stored.update(icons_applied=key, table_classes={'osm_point': {'class_1': 1}},
                  style_zooms={})
    gen.run('schema_1', out_dir=tmp_path)
    assert calls == []


def test_a_style_run_on_an_older_import_counts_once_and_stores_it(style_run, tmp_path):
    stored, calls, key = style_run
    stored.update(style_zooms={})
    gen.run('schema_1', out_dir=tmp_path)
    assert calls == ['icons', 'count']
    assert stored['icons_applied'] == key
    assert stored['table_classes'] == {'osm_point': {}}
    calls.clear()
    gen.run('schema_1', out_dir=tmp_path)
    assert calls == []


def test_a_changed_icon_mapping_is_written(style_run, tmp_path):
    stored, calls, key = style_run
    stored.update(icons_applied='key_1', table_classes={}, style_zooms={})
    gen.run('schema_1', out_dir=tmp_path)
    assert calls == ['icons']
    assert stored['icons_applied'] == key
