"""The legend: `styles/legend.yaml` -> one PNG per theme and language.

`legend.yaml` says what the legend shows; what an entry looks like is not
written anywhere but `classes.yaml`. Each class entry is drawn by Mapnik with
the symbolizers the theme's own XML carries for that class at the legend's
zoom (`styles.symbolizer` over `Styles.paint`), on a short line or a box, and
each icon entry is the file of the theme's palette from the icon set. A
changed colour or width therefore reaches the legend with the next style run,
and the legend cannot show a map that is not there.

The image is drawn by Mapnik too, as a Map whose units are pixels: the extent
is (0, 0, width, height) in a projected CRS, so one unit is one pixel and the
coordinates below are the layout. A class's geometry, an icon and a text are
features of an inline GeoJSON datasource, one layer per pass, in the order
the map draws them: casings under fills, then icons, then text.

The width is not known before rendering: the texts are measured by Mapnik,
with the fonts the map uses, and Python has neither. So a legend is rendered
twice -- once without a background on a wide canvas, to find the rightmost
painted column, and once at that width on the palette's background, which is
there so a dark palette's light text stays readable in a client's white
legend panel.
"""

from __future__ import annotations

import fnmatch
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from lib import i18n
from renderer import resolve
from renderer import styles as styles_module

LEGEND = 'legend.yaml'

#: The faces `classes.yaml`'s templates name: the legend reads like the map.
FONT = 'Noto Sans Regular'
FONT_BOLD = 'Noto Sans Bold'
TEXT_SIZE = 11
TITLE_SIZE = 12
TEXT_COLOR = 'clr_label'

#: The layout, in pixels.
PAD = 8
SYMBOL_WIDTH = 36
AREA_HEIGHT = 14
#: A road's round cap reaches half its width past the line's end.
TEXT_X = PAD + SYMBOL_WIDTH + 2 * PAD
ROW = 20
#: An icon is drawn at its size on the map, the template's canvas.
ICON_ROW = styles_module.ICON_SIZE + 3
TITLE_ROW = 26
#: The measuring canvas: wider than any legend should be.
MAX_WIDTH = 800

#: The modes whose symbolizers draw a class's geometry, in draw order.
GEOMETRY_PASSES = ('casing', 'fill', 'line')
#: The mode a class without geometry -- a place -- is shown in: its name
#: in its own style.
LABEL = 'label'


@dataclass(frozen=True)
class Entry:
    text: str
    cls: str | None = None
    zoom: int | None = None   # the zoom whose style a class entry shows
    #: The modes it is drawn in, in draw order: its geometry, or `label`
    #: for a class that has none -- a place, whose name is its symbol.
    modes: tuple[str, ...] = ()
    icon: str | None = None   # an icon entry's key, `<icon>.<colour token>`


@dataclass(frozen=True)
class Group:
    title: str
    entries: tuple[Entry, ...]


def load(styles_dir: Path) -> dict:
    return yaml.safe_load((styles_dir / LEGEND).read_text()) or {}


def classes(entry: dict, known) -> list[str]:
    """The classes a class entry names, in its order: a glob's matches
    sorted, a class matched twice counted once."""
    out: list[str] = []
    for pattern in _patterns(entry):
        out.extend(cls for cls in sorted(fnmatch.filter(known, pattern)) if cls not in out)
    return out


def _patterns(entry: dict) -> list[str]:
    value = entry['class']
    return value if isinstance(value, list) else [value]


def drawn_modes(styles, cls: str, zoom: int, allowed: frozenset[str] | None = None,
                palette: str | None = None) -> list[str]:
    """The modes `cls` is drawn in at `zoom`, of those the detail draws it
    in (`allowed`, None: all) and `palette` does not leave out (None: any
    palette): its geometry modes in draw order, or its label where it has no
    geometry there."""
    def drawn(mode: str) -> bool:
        return (mode in styles.modes(cls) and (allowed is None or mode in allowed)
                and styles.zoom_keys(cls, mode)[0] <= zoom
                and not (palette and styles.omits(styles.properties(cls, mode, zoom), palette)))

    out = [mode for mode in GEOMETRY_PASSES
           if drawn(mode) and _kinds(styles.properties(cls, mode, zoom))]
    return out or ([LABEL] if drawn(LABEL) else [])


def _kinds(properties: dict) -> tuple[str, ...]:
    """The symbolizers that draw geometry; text is the legend's own."""
    return tuple(kind for kind in resolve.symbolizers(properties) if kind in ('polygon', 'line'))


def needs_entry(styles) -> list[str]:
    """The classes the legend must show: every one drawn in a mode other
    than `marker`. A marker is its category's icon, shown by the icon
    groups."""
    return sorted(cls for cls in styles.classes if styles.modes(cls) - {'marker'})


def iconic(classifier, styles) -> frozenset[str]:
    """The categories the map can draw as an icon: those a rule gives a
    class with an icon marker (the importer's `draws_marker`). A city has
    an icon too, but its class has none: on the map it is a name, and the
    icon is only the search result's."""
    marker = {cls for cls in styles.classes if 'marker' in styles.modes(cls)
              and styles.properties(cls, 'marker', 0).get('icon')}
    return frozenset(rule.category for rule in classifier.rules if rule.cls in marker)


def drawn_icons(details: dict, detail: str, classifier, icon_keys: dict[str, str],
                can_draw: frozenset[str]) -> dict[str, str]:
    """{category: icon key} of every icon `detail` draws at some zoom: the
    legend is of the map, not of one zoom."""
    zooms = styles_module.detail_symbols(details, detail)['icons']
    importance = classifier.categories.importance
    return {category: key for category, key in icon_keys.items()
            if category in can_draw
            and styles_module.symbol_start(zooms, importance[category]) is not None}


def _roots(group: dict) -> list[str]:
    value = group['icons']
    return value if isinstance(value, list) else [value]


def _under(categories, category: str, roots) -> bool:
    return any(root == category or root in categories.ancestors[category] for root in roots)


def check(document: dict, styles, details: dict, classifier, icon_keys: dict[str, str]
          ) -> list[str]:
    """Everything in `legend.yaml` that would draw a wrong or an empty
    entry, and everything a theme draws that no entry shows.

    `icon_keys` is {drawn category: icon key} (`icons.drawn_keys`). Text
    ids are checked to exist; that each has every language is
    `test_i18n.py`'s.
    """
    errors = []
    messages = i18n.messages()
    categories = classifier.categories
    zoom = document.get('zoom')
    if not isinstance(zoom, int) or zoom < 0:
        errors.append(f'legend.yaml: zoom {zoom!r} is not a zoom')
        zoom = 0
    listed: set[str] = set()
    listed_categories: set[str] = set()
    roots: list[str] = []
    for group in document.get('groups') or []:
        title = group.get('title')
        where_group = f'legend.yaml {title or group.get("icons")}'
        unknown = sorted(set(group) - {'title', 'icons', 'entries'})
        if unknown:
            errors.append(f'{where_group}: {", ".join(unknown)} is not title, icons or entries')
        if 'icons' in group:
            for root in _roots(group):
                if root in categories.nodes:
                    roots.append(root)
                else:
                    errors.append(f'{where_group}: no category {root!r}')
        elif title is None:
            errors.append(f'{where_group}: a group without icons needs a title')
        if title is not None and title not in messages:
            errors.append(f'legend.yaml: title {title!r} is not in lib/messages.yaml')
        for entry in group.get('entries') or []:
            where = f'{where_group}: {entry!r}'
            unknown = sorted(set(entry) - {'class', 'category', 'text', 'zoom'})
            if unknown:
                errors.append(f'{where}: {", ".join(unknown)} is not class, category, text or zoom')
            text = entry.get('text')
            if text is not None and text not in messages:
                errors.append(f'{where}: text {text!r} is not in lib/messages.yaml')
            if ('class' in entry) == ('category' in entry):
                errors.append(f'{where}: an entry is a class or a category')
            elif 'class' in entry:
                if 'icons' in group:
                    errors.append(f'{where}: an icons group shows icons, not classes')
                at = entry.get('zoom', zoom)
                for pattern in _patterns(entry):
                    if not fnmatch.filter(styles.classes, pattern):
                        errors.append(f'{where}: no class {pattern!r} in classes.yaml')
                named = classes(entry, styles.classes)
                listed.update(named)
                if named and not any(drawn_modes(styles, cls, at) for cls in named):
                    errors.append(f'{where}: {named[0]} draws nothing at z{at}')
                if text is None:
                    errors.append(f'{where}: a class entry needs a text')
            elif entry['category'] not in categories.nodes:
                errors.append(f'{where}: no category {entry["category"]!r}')
            elif entry['category'] not in icon_keys:
                errors.append(f'{where}: {entry["category"]} draws no icon (icons.yaml)')
            else:
                listed_categories.add(entry['category'])

    errors.extend(f'legend.yaml: no entry shows {cls}'
                  for cls in needs_entry(styles) if cls not in listed)
    can_draw = iconic(classifier, styles)
    missing = sorted({category for detail in details
                      for category in drawn_icons(details, detail, classifier, icon_keys,
                                                  can_draw)
                      if category not in listed_categories
                      and not _under(categories, category, roots)})
    errors.extend(f'legend.yaml: no group shows the icon of {category}' for category in missing)
    return errors


def groups(document: dict, theme, styles, details: dict, lang: str, *,
           classifier, icon_keys: dict[str, str]) -> list[Group]:
    """What `theme`'s legend shows in `lang`: the entries its detail draws.

    A class entry is drawn as the first of its classes the detail draws. An
    icon is shown once, in the first group that names its category or holds
    it under its `icons`; an icons group lists its icons by name. A category
    entry names its icon wherever that icon is drawn, whether for its own
    category or another: an icons group's entries are its names.
    """
    drawn = styles_module.detail_modes(details, theme.detail, styles.classes)
    categories = classifier.categories
    icons = drawn_icons(details, theme.detail, classifier, icon_keys,
                        iconic(classifier, styles))
    drawn_keys = set(icons.values())
    order = {category: n for n, category in enumerate(categories.nodes)}

    def name(category: str, text: str | None = None) -> str:
        return i18n.t(text, lang) if text else categories.nodes[category][f'name_{lang}']

    shown: set[str] = set()
    out = []
    for group in document.get('groups') or []:
        entries = []
        for entry in group.get('entries') or []:
            if 'class' in entry:
                zoom = entry.get('zoom', document['zoom'])
                for cls in classes(entry, drawn):
                    modes = drawn_modes(styles, cls, zoom, drawn[cls], theme.palette)
                    if modes:
                        entries.append(Entry(i18n.t(entry['text'], lang), cls=cls, zoom=zoom,
                                             modes=tuple(modes)))
                        break
                continue
            # Shown wherever its icon is drawn, for this category or another
            # one with the same icon: it names the icon.
            key = icon_keys[entry['category']]
            if key in drawn_keys and key not in shown:
                shown.add(key)
                entries.append(Entry(name(entry['category'], entry.get('text')), icon=key))
        if 'icons' in group:
            roots = _roots(group)
            by_key: dict[str, list[str]] = {}
            for category, key in icons.items():
                if key not in shown and _under(categories, category, roots):
                    by_key.setdefault(key, []).append(category)
            # An icon several categories share is named as the most general
            # of them -- the bed is "Hotel", not "Motel" -- but not as
            # the group itself: the hospital the health group's own category
            # shares is "Krankenhaus", not "Gesundheit" under "Gesundheit".
            for key, members in by_key.items():
                first = min(members, key=lambda c: (c in roots, len(categories.ancestors[c]),
                                                    -categories.importance[c], order[c]))
                entries.append(Entry(name(first), icon=key))
            shown.update(by_key)
            entries.sort(key=lambda entry: _collation(entry.text))
        if entries:
            title = (i18n.t(group['title'], lang) if group.get('title')
                     else name(_roots(group)[0]))
            out.append(Group(title, tuple(entries)))
    return out


def _collation(text: str) -> str:
    """Alphabetical as a reader expects it: case and accents ignored, so
    "Ärztehaus" sorts with "Arzt", not after "Zahnarzt"."""
    decomposed = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def layout(legend: list[Group]) -> tuple[list[dict], int]:
    """The features to draw, as GeoJSON with y upwards, and the height.

    A feature's `n` is its entry's row, which a class's rules filter on.
    """
    rows: list[tuple[float, str | Entry]] = []   # (middle from the top, title or entry)
    top = PAD
    for group in legend:
        rows.append((top + TITLE_ROW / 2, group.title))
        top += TITLE_ROW
        for entry in group.entries:
            height = ICON_ROW if entry.icon else ROW
            rows.append((top + height / 2, entry))
            top += height
    height = int(top + PAD)

    features = []
    for n, (middle, row) in enumerate(rows):
        y = height - middle
        if isinstance(row, str):
            features.append(_feature(n, 'title', 'Point', [PAD, y], text=row))
            continue
        if row.modes == (LABEL,):
            features.append(_feature(n, LABEL, 'Point', [TEXT_X, y], text=row.text))
            continue
        features.append(_feature(n, 'text', 'Point', [TEXT_X, y], text=row.text))
        if row.icon:
            features.append(_feature(n, 'icon', 'Point', [PAD + SYMBOL_WIDTH / 2, y],
                                     icon=row.icon))
            continue
        # Both a line and a box: a class's rules draw on the one its
        # symbolizers suit.
        right = PAD + SYMBOL_WIDTH
        low, high = y - AREA_HEIGHT / 2, y + AREA_HEIGHT / 2
        features.append(_feature(n, 'line', 'LineString', [[PAD, y], [right, y]]))
        features.append(_feature(n, 'area', 'Polygon', [[[PAD, low], [right, low], [right, high],
                                                          [PAD, high], [PAD, low]]]))
    return features, height


def _feature(n: int, shape: str, geometry: str, coordinates, **properties) -> dict:
    return {'type': 'Feature', 'geometry': {'type': geometry, 'coordinates': coordinates},
            'properties': {'n': n, 'shape': shape, **properties}}


def build(legend: list[Group], styles, palette: str, icons: Path) -> tuple[ET.Element, int]:
    """The Mapnik Map of one legend, and its height. `icons` is the icon
    set, with a directory per palette."""
    features, height = layout(legend)
    tokens = styles.palettes[palette]
    root = ET.Element('Map', {'srs': styles_module.SRS})
    source = json.dumps({'type': 'FeatureCollection', 'features': features})
    entries = [entry for group in legend for entry in (None, *group.entries)]

    def layer(name: str) -> ET.Element:
        style = ET.SubElement(root, 'Style', {'name': name})
        element = ET.SubElement(root, 'Layer', {'name': name, 'srs': styles_module.SRS})
        ET.SubElement(element, 'StyleName').text = name
        datasource = ET.SubElement(element, 'Datasource')
        ET.SubElement(datasource, 'Parameter', {'name': 'type'}).text = 'geojson'
        ET.SubElement(datasource, 'Parameter', {'name': 'inline'}).text = source
        return style

    for mode in GEOMETRY_PASSES:
        style = layer(mode)
        for n, entry in enumerate(entries):
            if entry is None or mode not in entry.modes:
                continue
            properties = styles.paint(styles.properties(entry.cls, mode, entry.zoom),
                                      palette, mode)
            # A class that is filled anywhere is an area, else a line: a
            # building's outline goes round its box, not along a line.
            area = any('polygon' in _kinds(styles.properties(entry.cls, m, entry.zoom))
                       for m in entry.modes)
            rule = ET.SubElement(style, 'Rule')
            ET.SubElement(rule, 'Filter').text = (
                f"[n] = {n} and [shape] = '{'area' if area else 'line'}'")
            for kind in _kinds(properties):
                styles_module.symbolizer(rule, kind, properties)

    rule = ET.SubElement(layer('icons'), 'Rule')
    ET.SubElement(rule, 'Filter').text = "[shape] = 'icon'"
    ET.SubElement(rule, 'MarkersSymbolizer', {
        'file': f'{icons / palette}/[icon].svg', 'placement': 'point', 'allow-overlap': 'true'})

    style = layer('text')
    for shape, face, size in (('title', FONT_BOLD, TITLE_SIZE), ('text', FONT, TEXT_SIZE)):
        rule = ET.SubElement(style, 'Rule')
        ET.SubElement(rule, 'Filter').text = f"[shape] = '{shape}'"
        # `right`: the text starts at the point and runs to its right.
        ET.SubElement(rule, 'TextSymbolizer', {
            'face-name': face, 'size': str(size), 'fill': tokens[TEXT_COLOR],
            'placement': 'point', 'horizontal-alignment': 'right',
            'vertical-alignment': 'middle', 'allow-overlap': 'true',
        }).text = '[text]'
    # A place is shown by its name as the map writes it: the entry's text in
    # the class's label style, at a point rather than along a line.
    for n, entry in enumerate(entries):
        if entry is None or entry.modes != (LABEL,):
            continue
        properties = styles.paint(styles.properties(entry.cls, LABEL, entry.zoom),
                                  palette, LABEL)
        properties = {name: value for name, value in properties.items()
                      if name not in ('spacing', 'dy')}
        properties.update(text='text', placement='point')
        rule = ET.SubElement(style, 'Rule')
        ET.SubElement(rule, 'Filter').text = f"[n] = {n} and [shape] = '{LABEL}'"
        styles_module.symbolizer(rule, 'text', properties)
        rule[-1].attrib.update({'horizontal-alignment': 'right', 'vertical-alignment': 'middle',
                                'allow-overlap': 'true'})
    return root, height


def render(root: ET.Element, height: int, background: str) -> bytes:
    """The legend as PNG, as wide as what it draws."""
    import mapnik

    from renderer import core

    mapnik.register_fonts(core.FONT_DIR)
    map_ = mapnik.Map(MAX_WIDTH, height)
    mapnik.load_map_from_string(map_, ET.tostring(root, encoding='unicode'))

    def draw(width: int):
        map_.resize(width, height)
        map_.zoom_to_box(mapnik.Box2d(0, 0, width, height))
        image = mapnik.Image(width, height)
        mapnik.render(map_, image)
        return image

    width = min(painted_width(draw(MAX_WIDTH)) + PAD, MAX_WIDTH)
    map_.background = mapnik.Color(background)
    return draw(width).to_string('png')


def painted_width(image) -> int:
    """One past the rightmost column with a painted pixel."""
    width = image.width()
    alpha = image.to_string()[3::4]
    return max((len(alpha[row:row + width].rstrip(b'\0'))
                for row in range(0, len(alpha), width)), default=0)


def write(styles_dir: Path, out_dir: Path, languages: list[str], *, icons: Path,
          icon_keys: dict[str, str], classifier,
          only_palettes=None, only_details=None) -> list[Path]:
    """`<out_dir>/<theme>.<lang>.png` for every selected theme and language.

    `legend.yaml` is checked by `styles.generate`, before any of this.
    """
    styles, _layers, details = styles_module.load_style_files(styles_dir)
    document = load(styles_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for theme in styles_module.themes(styles.palettes, details, only_palettes, only_details):
        background = styles.palettes[theme.palette][styles_module.BACKGROUND]
        for lang in languages:
            legend = groups(document, theme, styles, details, lang,
                            classifier=classifier, icon_keys=icon_keys)
            root, height = build(legend, styles, theme.palette, icons)
            path = out_dir / f'{theme.name}.{lang}.png'
            path.write_bytes(render(root, height, background))
            written.append(path)
    # A theme or language no longer selected is not served from an old run.
    for stale in out_dir.glob('*.png'):
        if stale not in written:
            stale.unlink()
    return written
