"""The four style files -> Mapnik XML.

A theme is `<palette>_<detail>`, so four palettes times four details is
sixteen themes, all computed from `layers.yaml`, `classes.yaml`,
`palettes.yaml` and `details.yaml`. There is no file per
theme and no CartoCSS.

Built with ElementTree rather than string templates on purpose. The
datasource query contains `geom && !bbox!`, and an unescaped `&` makes an
XML file Mapnik refuses to parse -- a whole class of bug that a real
serialiser cannot produce.

The datasource carries `table`, `geometry_field`, `srid` and `extent` and
nothing else: the connection comes from libpq's environment (lib.db), so the XML
holds no credentials and is byte-identical on every deployment.

ONE FILE PER THEME *AND PER TILEMATRIXSET*

Sixteen themes, but not sixteen files: a theme is compiled once per
configured TileMatrixSet, into `<out_dir>/<set identifier>/<theme>.xml`.

The reason is `metres_factor`, and it is not cosmetic. Two things in this
file are compared against Mapnik's `!scale_denominator!` -- each rule's
`Min`/`MaxScaleDenominator`, and the `minzoom <= z` expression in the
datasource query -- and Mapnik computes that denominator in the units of
the **Map's own srs**, which `core.render_tile` repoints per request. For
EPSG:3857 those are Web Mercator units, which is what every `minzoom`
column is written in. For a true-metre CRS they are ground metres, and at
51 N a ground metre is 1/cos(51) = 1.59 Web Mercator units -- so the same
tile reports a denominator 0.63 times the Web Mercator one and resolves
two thirds of a zoom too high.

Measured without it: every EPSG:25832 level resolved exactly one zoom
too fine -- level 8, the configured pre-cache depth, asked for
`minzoom <= 13` and so read the full table where `_z12` was meant, which
is the cost the band tables exist to avoid. `metres_factor` is a constant
of the *set*, so it has to be baked in at generation, and a file that
bakes in one cannot serve the other.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import itertools
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import yaml

from importer import elevation
from importer.rules import NO_CLASS
from renderer import icons as icons_module
from renderer import queries
from renderer import resolve as resolve_module
from renderer.resolve import Styles

log = logging.getLogger('renderer')

SRS = 'epsg:3857'

#: property name -> Mapnik attribute, per symbolizer.
POLYGON_ATTRS = {'polygon-fill': 'fill', 'polygon-opacity': 'fill-opacity'}
LINE_ATTRS = {
    'line-color': 'stroke', 'line-width': 'stroke-width', 'line-cap': 'stroke-linecap',
    'line-join': 'stroke-linejoin', 'line-dasharray': 'stroke-dasharray',
    'line-opacity': 'stroke-opacity',
}
TEXT_ATTRS = {
    'font': 'face-name', 'size': 'size', 'fill': 'fill', 'halo': 'halo-fill',
    'halo-radius': 'halo-radius', 'placement': 'placement', 'spacing': 'spacing',
    'dy': 'dy', 'wrap': 'wrap-width',
}
#: A shield is an icon and its text. `size` is the icon's, so the text's
#: size is `text-size` there.
SHIELD_ATTRS = {**{name: attr for name, attr in TEXT_ATTRS.items() if name != 'size'},
                'text-size': 'size'}

#: The canvas of every icon file (`styles/icons/template.svg`). `size` on an
#: icon marker is this canvas's size in pixels.
ICON_SIZE = 27


class GenerationError(Exception):
    """The style files would produce a wrong map. Refuse to write one."""


@dataclass(frozen=True)
class Theme:
    palette: str
    detail: str

    @property
    def name(self) -> str:
        return f'{self.palette}_{self.detail}'


def themes(palettes, details, only_palettes=None, only_details=None) -> list[Theme]:
    """The palettes x details the `serve_palettes` and `serve_details` options name (None:
    all). A theme left out is not compiled, and a server loads,
    lists and serves only what is compiled -- which is the point on a dev
    server, where loading a theme costs ~0.06 s per Map (through pgbouncer) at every restart."""
    for name, what, wanted, known in (('serve_palettes', 'palette', only_palettes, palettes),
                                      ('serve_details', 'detail', only_details, details)):
        unknown = sorted(set(wanted or ()) - set(known))
        if unknown:
            raise GenerationError(f'option {name}: no such {what} {", ".join(unknown)}')
    return [Theme(p, detail) for p in sorted(palettes) for detail in sorted(details)
            if (not only_palettes or p in only_palettes) and (not only_details or detail in only_details)]


def detail_entries(detail: dict) -> list[tuple[str, frozenset[str] | None]]:
    """A detail's `classes` as (glob, modes): a plain glob draws the class in
    every mode (None), `{glob: [modes]}` only in those -- buildings
    without their names, say."""
    out = []
    for entry in detail.get('classes') or []:
        if isinstance(entry, dict):
            out.extend((pattern, frozenset(modes)) for pattern, modes in entry.items())
        else:
            out.append((entry, None))
    return out


def detail_modes(details: dict, name: str, known) -> dict[str, frozenset[str] | None]:
    """{class: the modes this detail draws it in, None for all}, globs
    expanded. Entries add up: a plain glob wins over a restricted one."""
    out: dict[str, frozenset[str] | None] = {}
    for pattern, modes in detail_entries(details[name]):
        for cls in fnmatch.filter(known, pattern):
            if modes is None or out.get(cls, frozenset()) is None:
                out[cls] = None
            else:
                out[cls] = out.get(cls, frozenset()) | modes
    return out


#: The maps under a detail's `symbols`: importance -> the zoom icons, and
#: their labels, of at least that importance start at.
SYMBOLS = ('icons', 'labels')

#: What a detail may say. Anything else is refused: a key the generator
#: does not read -- `icons` where `symbols.icons` is meant -- would leave
#: the detail with no icons and no error.
DETAIL_KEYS = frozenset({'classes', 'symbols'})


def detail_symbols(details: dict, name: str) -> dict[str, dict[int, int]]:
    """{'icons': {importance: zoom}, 'labels': {importance: zoom}} -- from
    which zoom this detail draws the icons of each importance, and their
    labels. Empty: none at all."""
    symbols = details[name].get('symbols') or {}
    return {kind: {int(importance): int(zoom)
                   for importance, zoom in (symbols.get(kind) or {}).items()}
            for kind in SYMBOLS}


def symbol_start(zooms: dict[int, int], importance: int) -> int | None:
    """The zoom a row of this importance starts at: that of the highest
    entry its importance reaches, None below the lowest."""
    reached = [key for key in zooms if key <= importance]
    return zooms[max(reached)] if reached else None


#: Where a rule boundary sits between two zooms. The scale halves per
#: zoom, so the geometric mean of two neighbours is scale / sqrt(2) -- as
#: far from both as a multiplicative quantity can be.
_BETWEEN = 2 ** 0.5


def scale_range(low: int, high: int, zoom_max: int,
                metres_factor: float = 1.0) -> tuple[float | None, float | None]:
    """Mapnik's (min, max) scale denominators for a zoom range.

    A rule applies while `min <= scale < max`, and the scale halves with
    every zoom, so the *minimum* comes from the highest zoom and the
    maximum from the lowest. Both are omitted at the ends of the pyramid,
    where Mapnik's own defaults are wider than anything a client can ask
    for.

    The boundaries sit *between* zooms rather than exactly on one, and
    that is not tidiness. Writing the exact denominator of the neighbouring
    zoom puts a float equality on the hot path: the XML carries six
    decimals, and rounding the last of them upwards makes `scale < max`
    true at a zoom the rule was never meant to cover. That is how
    `poi_cafe` came to draw from z15 when `classes.yaml` says 16 -- a whole
    zoom of extra detail, from a rounding step, visible to nobody until
    someone compares tiles.
    """
    minimum = (None if high >= zoom_max
               else queries.scale_denominator(high, metres_factor) / _BETWEEN)
    maximum = (None if low <= 0
               else queries.scale_denominator(low, metres_factor) * _BETWEEN)
    return minimum, maximum


def symbolizer(parent, kind: str, properties: dict, icons: Path | None = None) -> None:
    if kind == 'polygon':
        element = ET.SubElement(parent, 'PolygonSymbolizer')
        attrs = POLYGON_ATTRS
    elif kind == 'line':
        element = ET.SubElement(parent, 'LineSymbolizer')
        attrs = LINE_ATTRS
    elif kind == 'marker':
        # A marker is the row's category icon and nothing else: no shapes,
        # no dots. `icon: false` would draw nothing and say nothing.
        if not properties.get('icon'):
            raise GenerationError(f'a marker is an icon (icon: true), got {properties!r}')
        if icons is None:
            raise GenerationError('an icon marker needs the icon directory')
        element = ET.SubElement(parent, 'MarkersSymbolizer')
        # Everything it looks like is in the file: `size` is a scale below,
        # and a MarkersSymbolizer's fill would recolour every shape of the
        # SVG, the white disc and the white icon too.
        attrs = {}
        # The row names its file: `osm_point.icon`, which the style run
        # sets from the row's category (renderer/icons.py).
        element.set('file', f'{icons}/[icon].svg')
        # Never width/height on an SVG: Mapnik fits the *drawn shape's*
        # bounding box to them, not the icon's canvas, so a 10 px wide fork
        # and knife was stretched to 15 x 15 and every icon came out a
        # different, non-integer scale -- blurred and distorted. Unscaled,
        # the icon is drawn on its own 15 px grid, as designed.
        size = properties.get('size')
        if size is not None and size != ICON_SIZE:
            element.set('transform', f'scale({size / ICON_SIZE:g})')
        element.set('allow-overlap', 'false')
        element.set('avoid-edges', 'true')
        element.set('placement', 'point')
    elif kind == 'shield':
        if icons is None:
            raise GenerationError('an icon shield needs the icon directory')
        element = ET.SubElement(parent, 'ShieldSymbolizer')
        attrs = SHIELD_ATTRS
        element.set('file', f'{icons}/[icon].svg')
        size = properties.get('size')
        if size is not None and size != ICON_SIZE:
            element.set('transform', f'scale({size / ICON_SIZE:g})')
        # The icon stays on the point and `dy` moves only the text; locked,
        # the icon would follow the text below its own position.
        element.set('unlock-image', 'true')
        element.set('placement', 'point')
        element.set('allow-overlap', 'false')
        element.set('avoid-edges', 'true')
        element.text = f"[{properties['text']}]"
    else:
        element = ET.SubElement(parent, 'TextSymbolizer')
        attrs = TEXT_ATTRS
        element.set('avoid-edges', 'true')
        # The column the text comes from: `name` or `label`.
        element.text = f"[{properties['text']}]"

    for name, value in properties.items():
        attribute = attrs.get(name)
        if attribute:
            element.set(attribute, _text(value))


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        return ','.join(str(v) for v in value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _datasource(parent, schema: str, source: queries.Source, extent: str,
                metres_factor: float, db_pool_size: int) -> None:
    element = ET.SubElement(parent, 'Datasource')
    parameters = {
        'type': 'postgis',
        'table': queries.sql(schema, source, metres_factor),
        'geometry_field': 'geom',
        'srid': '3857',
        'extent': extent,
        # No host, dbname, user or password: libpq reads PGHOST, PGPASSWORD
        # and the rest from the environment lib.config sets from the
        # deployment's options and postgres.env, so this file is the same on
        # every machine and carries no secret.
        'key_field': '',
        # The plugin's connection pool, shared by every layer of every Map
        # in the process. A render that finds it full fails with "Null
        # connection" rather than waiting.
        'max_size': str(db_pool_size),
    }
    for name, value in parameters.items():
        if value == '':
            continue
        ET.SubElement(element, 'Parameter', {'name': name}).text = value


def build(schema: str, theme: Theme, styles: Styles, layers: list[dict], details: dict,
          params, present: dict, extent: str, *, metres_factor: float = 1.0,
          buffer_px: int = 64, db_pool_size: int = 40,
          icons: Path | None = None) -> ET.Element:
    """One Mapnik Map for one theme.

    `buffer_px` is a deployment option, not a model parameter: it is how
    far beyond the tile each layer fetches features, so a road cap or an
    outline near the edge is not clipped.

    It is a Layer buffer, and the Map's is 0. Mapnik measures `avoid-edges`
    against the Map extent *plus* the Map buffer, so with a Map buffer an
    icon or label crossing the tile edge still counts as inside: each tile
    runs its own collision detection, one places the symbol and its
    neighbour drops it, and the seam shows half of it. A Layer buffer
    widens only the query, so `avoid-edges` measures against the tile.
    """
    drawn = detail_modes(details, theme.detail, styles.classes)
    palette = styles.palettes[theme.palette]
    # The icon set has a directory per palette: the colour is baked in.
    icons = icons / theme.palette if icons is not None else None
    root = ET.Element('Map', {
        'background-color': palette[BACKGROUND],
        'srs': SRS,
        'buffer-size': '0',
    })

    # Which icons and labels, from which zoom, is the detail's `symbols` and
    # each row's importance -- not the detail's class list and not the
    # class's zoom. A marker layer therefore takes all its classes, starts
    # where the earliest importance does, and leaves the rest to the query.
    symbols = detail_symbols(details, theme.detail)
    icon_zooms = tuple(sorted(symbols['icons'].items()))
    label_zooms = tuple(sorted(symbols['labels'].items()))
    icon_floor = min((zoom for _, zoom in icon_zooms), default=None)
    # Classes a marker layer draws as an icon: where they are labelled as
    # well, the label yields to the icon from where the icon starts. Not
    # every class with a marker entry -- one no marker layer lists would
    # lose its label to an icon that is never drawn.
    iconic = frozenset(cls for layer in layers if layer['mode'] == 'marker'
                       for pattern in layer['classes']
                       for cls in fnmatch.filter(styles.classes, pattern)
                       if 'marker' in styles.modes(cls)
                       and styles.properties(cls, 'marker', 0).get('icon'))

    for index, layer in enumerate(layers):
        name = layer.get('name') or f'{layer["mode"]}_{index}'
        mode = layer['mode']
        if mode == 'marker' and not icon_zooms:
            continue
        classes = {c for pattern in layer['classes']
                   for c in fnmatch.filter(styles.classes, pattern)}
        if mode != 'marker':
            classes = {c for c in classes if c in drawn and (drawn[c] is None or mode in drawn[c])}
        classes = {c for c in classes if mode in styles.modes(c)}
        if not classes:
            continue

        for source in queries.sources(classes, present, params.bands,
                                      params.zoom_max, mode=mode):
            if source.icon:
                source = dataclasses.replace(source, icon_zooms=icon_zooms,
                                             label_zooms=label_zooms)
            elif source.table == 'osm_label' and iconic & set(source.classes):
                source = dataclasses.replace(source, icon_zooms=icon_zooms,
                                             yields=tuple(sorted(iconic & set(source.classes))))
            style_name = f'{name}_{source.table}'
            style = ET.SubElement(root, 'Style', {'name': style_name})
            rules = 0
            for cls in sorted(source.classes):
                keys = styles.zoom_keys(cls, mode)
                for position, zoom in enumerate(keys):
                    low = max(zoom, source.min_zoom)
                    if mode == 'marker' and position == 0:
                        low = max(icon_floor, source.min_zoom)
                    high = (keys[position + 1] - 1 if position + 1 < len(keys)
                            else params.zoom_max)
                    high = min(high, source.max_zoom)
                    if low > high:
                        continue
                    if styles.omits(styles.properties(cls, mode, zoom), theme.palette):
                        continue
                    properties = styles.paint(styles.properties(cls, mode, zoom),
                                              theme.palette, mode)
                    kinds = _rule(style, cls, properties, low, high,
                                  params.zoom_max, metres_factor, icons)
                    rules += bool(kinds)
            if not rules:
                root.remove(style)
                continue

            element = ET.SubElement(root, 'Layer', {'name': style_name, 'srs': SRS,
                                                    'buffer-size': str(buffer_px)})
            ET.SubElement(element, 'StyleName').text = style_name
            _datasource(element, schema, source, extent, metres_factor, db_pool_size)

    return root


def _rule(style, cls: str, properties: dict, low: int, high: int,
          zoom_max: int, metres_factor: float, icons: Path | None = None) -> tuple[str, ...]:
    from renderer import resolve

    kinds = resolve.symbolizers(properties)
    if not kinds:
        return ()
    minimum, maximum = scale_range(low, high, zoom_max, metres_factor)

    def add(condition: str, drawn: tuple[str, ...]) -> None:
        rule = ET.SubElement(style, 'Rule')
        ET.SubElement(rule, 'Filter').text = f"[class] = '{cls}'{condition}"
        if minimum is not None:
            ET.SubElement(rule, 'MinScaleDenominator').text = f'{minimum:.6f}'
        if maximum is not None:
            ET.SubElement(rule, 'MaxScaleDenominator').text = f'{maximum:.6f}'
        for kind in drawn:
            symbolizer(rule, kind, properties, icons)

    if properties.get('icon') and 'text' in kinds:
        # An icon's text is placed together with it, as one shield, or not
        # at all. Two symbolizers would each run their own collision test,
        # and a label whose icon lost its spot would stand there alone.
        # A row without the text column gets the plain icon: a shield with
        # nothing to say draws nothing.
        column = properties['text']
        add(f' and [{column}] != null', ('shield',))
        add(f' and [{column}] = null', ('marker',))
    else:
        add('', kinds)
    return kinds


def write(root: ET.Element, path: Path) -> None:
    ET.indent(root, '  ')
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                    + ET.tostring(root, encoding='unicode') + '\n')


def load_style_files(styles_dir: Path):
    from renderer import resolve

    return (resolve.load(styles_dir),
            yaml.safe_load((styles_dir / 'layers.yaml').read_text()),
            yaml.safe_load((styles_dir / 'details.yaml').read_text()))


# --- checks --------------------------------------------------------------

#: The class the water import assigns; no rule produces it.
WATER_CLASS = 'cls_ocean'

#: The palette token for the map background.
BACKGROUND = 'clr_land'

#: Tokens the *generator* reads directly rather than through an entry in
#: `classes.yaml`. `_check_tokens` walks the entries, so it never sees
#: these two -- and a palette missing one failed with a bare KeyError from
#: `build` or `paint`, halfway through writing, rather than with a message
#: naming the palette. DESIGN.md "palettes.yaml" requires both of every
#: palette: `clr_land` is the map background, `casing_scale` multiplies every
#: casing width.
GENERATOR_TOKENS = (BACKGROUND, resolve_module.CASING_SCALE)


def check(styles: Styles, layers: list[dict], details: dict, classifier,
          faces: frozenset[str] | None = None,
          imported: dict | None = None) -> tuple[list[str], list[str]]:
    """Everything that would make a wrong map rather than an error.

    Returns (errors, warnings). The generator refuses to write on any
    error: a style file that is wrong produces tiles that render fine and
    show the wrong thing, which is the failure mode worth spending checks
    on.

    Globs are matched against the *model*, not against imported data. A
    landlocked extract has no `ocean`, no `aeroway_*` and no `rail_*` rows
    at all, and checking against data would refuse to generate styles for a
    perfectly good area.

    `imported` is what the import wrote the rows for (`import_meta.style_zooms`);
    None skips that check.
    """
    errors: list[str] = []
    warnings: list[str] = []
    classified = {rule.cls for rule in classifier.rules
                  if rule.cls and rule.cls != NO_CLASS} | {WATER_CLASS, *elevation.classes()}

    for cls in sorted(styles.classes - classified):
        errors.append(f'classes.yaml styles {cls!r}, which no rule produces')
    for cls in sorted(classified - styles.classes):
        warnings.append(f'{cls!r} is classified but nothing styles it')

    for layer in layers:
        for pattern in layer['classes']:
            if not fnmatch.filter(classified, pattern):
                errors.append(f'layers.yaml: {pattern!r} matches no class')
    for name, detail in details.items():
        for pattern, modes in detail_entries(detail):
            if not fnmatch.filter(classified, pattern):
                errors.append(f'details.yaml {name}: {pattern!r} matches no class')
            for mode in sorted((modes or frozenset()) - (set(resolve_module.MODES) - {'*'})):
                errors.append(f'details.yaml {name}: {pattern!r} names {mode!r}, which is not a mode')
        unknown = sorted(set(detail) - DETAIL_KEYS)
        if unknown:
            errors.append(f'details.yaml {name}: {", ".join(unknown)} is not one of '
                          f'{", ".join(sorted(DETAIL_KEYS))}')
        errors.extend(_check_symbols(name, detail))

    errors.extend(_check_names(styles, details))
    errors.extend(_check_generator_tokens(styles))
    errors.extend(_check_tokens(styles))
    if imported is not None:
        errors.extend(_check_imported_zooms(styles, imported))
    if faces is not None:
        errors.extend(_check_fonts(styles, faces))
    return errors, warnings


def _check_symbols(name: str, detail: dict) -> list[str]:
    """A detail's `symbols`: `icons` and `labels`, each importance 1-100 to
    a zoom, never later for more; and no label before its icon.

    Importance 0 is "ignored" and never gets an icon. A mapping where a more
    important icon starts later than a less important one would draw the
    less important first; the query's floor (queries.importance_floor)
    assumes it cannot. A label is drawn with its icon or not at all, and the
    row is not fetched below its icon's floor, so a label zoom before the
    icon's would silently mean the icon's.
    """
    if 'symbols' not in detail:
        return []
    symbols = detail['symbols'] or {}
    where = f'details.yaml {name}: symbols'
    if not isinstance(symbols, dict):
        return [f'{where} must map icons and labels']
    errors = [f'{where}.{kind} is not one of {", ".join(SYMBOLS)}'
              for kind in sorted(set(symbols) - set(SYMBOLS))]
    maps = {}
    for kind in SYMBOLS:
        zooms = symbols.get(kind) or {}
        if not isinstance(zooms, dict):
            errors.append(f'{where}.{kind} must map importance to zoom')
            continue
        pairs = []
        for importance, zoom in zooms.items():
            if not isinstance(importance, int) or not 1 <= importance <= 100:
                errors.append(f'{where}.{kind} importance {importance!r} is not 1-100')
            elif not isinstance(zoom, int) or zoom < 0:
                errors.append(f'{where}.{kind} zoom {zoom!r} for {importance} is not a zoom')
            else:
                pairs.append((importance, zoom))
        pairs.sort()
        for (low, low_zoom), (high, high_zoom) in itertools.pairwise(pairs):
            if high_zoom > low_zoom:
                errors.append(f'{where}.{kind} draw importance {high} from z{high_zoom}, '
                              f'later than {low} from z{low_zoom}')
        maps[kind] = dict(pairs)
    if len(maps) == len(SYMBOLS):
        icons, labels = maps['icons'], maps['labels']
        # Both are step functions of the importance, constant between keys.
        for importance in sorted(set(icons) | set(labels)):
            label, icon = symbol_start(labels, importance), symbol_start(icons, importance)
            if label is not None and (icon is None or label < icon):
                since = 'never' if icon is None else f'from z{icon}'
                errors.append(f'{where}.labels draw importance {importance} from z{label}, '
                              f'but its icon {since}')
    return errors


def _check_names(styles: Styles, details: dict) -> list[str]:
    """A URL names a theme by its palette or its detail alone
    (`web.serving.url_name`), which is unambiguous only while no name is both."""
    return [f'{name!r} is both a palette and a detail'
            for name in sorted(set(styles.palettes) & set(details))]


def _check_generator_tokens(styles: Styles) -> list[str]:
    """The two tokens no entry names but every palette needs."""
    errors = []
    for palette in sorted(styles.palettes):
        for token in GENERATOR_TOKENS:
            if token not in styles.palettes[palette]:
                errors.append(f'palette {palette!r} defines no {token!r}, which '
                              f'every palette must')
    return errors


def _check_tokens(styles: Styles) -> list[str]:
    errors = []
    for cls in sorted(styles.classes):
        for mode in sorted(styles.modes(cls)):
            for zoom in styles.zoom_keys(cls, mode):
                for name, value in styles.properties(cls, mode, zoom).items():
                    if name not in resolve_module.TOKEN_PROPERTIES or not isinstance(value, str):
                        continue
                    if value.startswith('#'):
                        errors.append(
                            f'{cls} {mode} {zoom}: {name} is the literal {value!r}, '
                            f'not a palette token')
                        continue
                    missing = sorted(p for p, tokens in styles.palettes.items()
                                     if value not in tokens)
                    if missing:
                        errors.append(f'{cls} {mode} {zoom}: token {value!r} is missing '
                                      f'from {", ".join(missing)}')
    return errors


def _check_imported_zooms(styles: Styles, imported: dict) -> list[str]:
    """No class starts earlier than the import wrote its rows for.

    `minzoom` and `minzoom_label` are written at import from this file
    (`Styles.start`, `Styles.text_start`), so a start moved earlier only
    takes effect after a re-import. Until then the rule fires where the rows
    say not yet, and draws nothing. Moved later is fine: the rule starts
    later, and the rows only cost a few reads until the next import.
    """
    errors = []
    for cls in sorted(styles.classes):
        was_start, was_text = imported.get(cls, (None, None))
        for what, now, was in (('drawn', styles.start(cls), was_start),
                               ('labelled', styles.text_start(cls), was_text)):
            if now is not None and (was is None or now < was):
                since = 'never' if was is None else f'from z{was}'
                errors.append(f'{cls} is {what} from z{now}, but was imported as {what} '
                              f'{since}: re-import the area')
    return errors


def _check_fonts(styles: Styles, faces: frozenset[str]) -> list[str]:
    errors = []
    named = set()
    for cls in styles.classes:
        for mode in styles.modes(cls):
            for zoom in styles.zoom_keys(cls, mode):
                font = styles.properties(cls, mode, zoom).get('font')
                if font:
                    named.add(font)
    for font in sorted(named - faces):
        errors.append(f'font {font!r} is not installed; a style must fail here, '
                      f'not silently at render')
    return errors


def installed_faces() -> frozenset[str]:
    """The faces the renderer will have: the wheel's own and those it
    registers from the image. Without registering, only the wheel's DejaVu
    counted, and every Noto face was refused as not installed."""
    import mapnik

    from renderer import core

    mapnik.register_fonts(core.FONT_DIR)
    return frozenset(mapnik.FontEngine.face_names())


# --- generation ----------------------------------------------------------

def generate(schema: str, styles_dir: Path, out_dir: Path, present: dict, extent: str,
             params, classifier, sets, *, buffer_px: int = 64, db_pool_size: int = 40,
             faces: frozenset[str] | None = None, icons: Path | None = None,
             only_palettes=None, only_details=None, imported: dict | None = None) -> list[Path]:
    """Write one XML per theme per TileMatrixSet.

    Refuses to write anything if a check fails -- and checks once, not per
    set: the style files do not depend on the grid, only the scale
    arithmetic does.

    `sets` is `{identifier: TileMatrixSet}` as `matrix.load()` returns it. Each
    one contributes its `metres_factor`, which is the whole reason a theme
    is compiled more than once (see the module docstring).
    """
    from importer.run import MODEL
    from renderer import legend

    styles, layers, details = load_style_files(styles_dir)
    errors, warnings = check(styles, layers, details, classifier, faces, imported)
    errors.extend(legend.check(legend.load(styles_dir), styles, details, classifier,
                               icons_module.drawn_keys(MODEL, styles_dir)))
    for warning in warnings:
        print(f'warning: {warning}')
    if errors:
        raise GenerationError('\n'.join(errors))

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for tms in sets.values():
        directory = out_dir / tms.identifier
        directory.mkdir(parents=True, exist_ok=True)
        wanted = themes(styles.palettes, details, only_palettes, only_details)
        for theme in wanted:
            root = build(schema, theme, styles, layers, details, params, present, extent,
                         metres_factor=tms.metres_factor, buffer_px=buffer_px,
                         db_pool_size=db_pool_size, icons=icons)
            path = directory / f'{theme.name}.xml'
            write(root, path)
            written.append(path)
        # A theme no longer selected must not be left behind to be loaded
        # and served from an old compile.
        for stale in directory.glob('*.xml'):
            if stale not in written:
                stale.unlink()
    return written


#: The render tables a layer can read.
RENDERED = ('osm_point', 'osm_line', 'osm_polygon', 'osm_building', 'osm_label', 'osm_contour')


def schema_extent(conn, schema: str) -> str:
    """The area's extent, as Mapnik's `extent` parameter.

    From `import_meta`, which the importer fills from the pbf header.
    Telling the datasource the extent stops Mapnik asking the database for
    it when it opens the layer -- once per Map object per layer, and there
    are twelve themes times a pool of them.
    """
    from psycopg import sql

    row = conn.execute(sql.SQL(
        'select st_xmin(bbox_3857), st_ymin(bbox_3857),'
        ' st_xmax(bbox_3857), st_ymax(bbox_3857) from {}'
    ).format(sql.Identifier(schema, 'import_meta'))).fetchone()
    if row is None or row[0] is None:
        raise GenerationError(
            f'{schema}.import_meta has no bbox: the import did not finish, or predates it')
    return ','.join(f'{v:.4f}' for v in row)


def run(schema: str | None = None, out_dir: Path | None = None) -> list[Path]:
    """Write the icons and set each point's, then every theme for the area and its legends.

    What `manage.py compile-styles` calls, and the app when it starts -- so
    nothing here may cost a scan of the tables when nothing changed. The
    classes per table come from `import_meta.table_classes`, counted by the
    import (and counted here once, then stored, for an import that predates
    it); the icons are written to the rows only when the mapping differs
    from the one `import_meta.icons_applied` says they carry. On de
    the two scans were 22 s and at least 16 s of every start.
    """
    from importer import meta
    from importer import params as params_module
    from importer import rules as rules_module
    from importer.run import MODEL, STYLES
    from lib import config, db, i18n
    from renderer import legend, matrix

    schema = schema or db.active_schema()
    data_dir = Path(config.opt('data_dir', '/data'))
    out_dir = out_dir or data_dir / 'styles' / schema

    log.info('compiling styles for %s', schema)
    started = time.monotonic()
    params = params_module.load(MODEL, STYLES)
    classifier = rules_module.load(MODEL)
    icon_set, drawn = icons_module.write(MODEL, STYLES, data_dir)
    lap = time.monotonic()
    with db.connection() as conn:
        imported_meta = meta.read(conn, schema) or {}
        key = icons_module.mapping_key(drawn)
        if imported_meta.get('icons_applied') == key:
            log.info('icons unchanged since the last style run')
        else:
            log.info('updating icons ...')
            changed = icons_module.update_points(conn, schema, drawn)
            meta.update(conn, schema, icons_applied=key)
            log.info('icons updated in %.1f s, %d rows', time.monotonic() - lap, changed)
        present = imported_meta.get('table_classes')
        if present is None:
            lap = time.monotonic()
            present = db.table_classes(conn, schema, RENDERED)
            meta.update(conn, schema, table_classes=present)
            log.info('classes per table counted and stored (the import predates them), %.1f s',
                     time.monotonic() - lap)
        extent = schema_extent(conn, schema)
    imported = imported_meta.get('style_zooms')
    if imported is None:
        log.warning('%s.import_meta has no style_zooms: the import predates them, '
                    'so a class moved earlier than its rows is not caught', schema)

    written = generate(schema, STYLES, out_dir, present, extent, params, classifier,
                       matrix.load(),
                       buffer_px=int(config.opt('buffer_px', 64)),
                       db_pool_size=int(config.opt('db.mapnik_pool_size', 40)),
                       faces=installed_faces(), icons=icon_set,
                       only_palettes=config.opt('serve_palettes'),
                       only_details=config.opt('serve_details'),
                       imported=imported)
    legends = legend.write(STYLES, out_dir / 'legend', i18n.languages(), icons=icon_set,
                           icon_keys=drawn, classifier=classifier,
                           only_palettes=config.opt('serve_palettes'),
                           only_details=config.opt('serve_details'))
    log.info('%d themes and %d legends written for %s, %.1f s in all', len(written),
             len(legends), schema, time.monotonic() - started)
    return written
