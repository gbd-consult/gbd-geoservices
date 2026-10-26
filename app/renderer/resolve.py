"""Style resolution: (class, mode, zoom) -> the properties to draw with.

`styles/classes.yaml` has a section per mode (`*` for every mode), keyed
`"<class> <zoom>"` or just `"<class>"` for every zoom. One key does not
describe a symbolizer on its own -- it describes a *change*. What a class
looks like at a given zoom in a given mode is every entry that applies, in a
defined order, each overriding single properties of the ones before it.
That is the whole of the resolution (DESIGN.md "Style files"), and it is the
reason a few hundred entries cover every class at every zoom without a file
per theme.

The same file says where a class starts: the lowest zoom it has in a drawn
mode (`start`) and in a text mode (`text_start`). The importer writes both
into the rows, so this module is read at import as well as at style time.

Colours are palette tokens, never literals, so the same resolution feeds
four palettes. The substitution is separate (`paint`) because the
generator resolves once per class and then paints once per theme.

No Mapnik here, and no database: this is arithmetic over two YAML files and
is tested as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

#: The symbolizer follows from the property names, not from the mode
#: (DESIGN.md "Compiling"). A `fill` layer over line classes draws the inner
#: stroke of a road, which is a line symbolizer.
#:
#: Only the properties that actually *draw* count. `line-cap`, `line-join`,
#: `line-dasharray` and `line-opacity` modify a stroke that some other
#: entry has to provide -- `road_primary * *` is nothing but a cap and a
#: join, and treating that as a line symbolizer would emit a rule that
#: draws an invisible zero-width line at every zoom below the first real
#: one.
#: Order matters: Mapnik draws a rule's symbolizers in document order, so
#: this is the z-order within one rule. Fill, then its outline, then the
#: icon, then text. An icon with text is not two symbolizers at all: the
#: generator draws the pair as one shield (styles._rule).
DRAWS = (
    ('polygon', ('polygon-fill',)),
    ('line', ('line-color', 'line-width')),
    ('marker', ('icon',)),
    ('text', ('text',)),
)

#: Multiplied into every line-width drawn in casing mode, so a palette can
#: have thicker casings without a second set of widths.
CASING_SCALE = 'casing_scale'

#: The only properties whose value is a palette token. Substituting on
#: value alone -- "is this string a token name?" -- is wrong, because the
#: namespaces overlap: `label` is a palette token (a text colour) *and* the
#: name of the column a shield draws its text from, so `text: label` would
#: become `text: '#333333'` and Mapnik would look for a column called
#: #333333. Everything else -- `font`, `placement`, `text` -- is a
#: literal whatever it happens to spell.
TOKEN_PROPERTIES = frozenset({
    'polygon-fill', 'line-color', 'fill', 'halo', 'stroke', 'halo-radius',
})

#: The token value by which a palette leaves out whatever is painted with
#: it: the rule is not compiled, so a layer left without rules does not
#: query either, and the legend does not show it.
NONE = 'none'


#: Modes that draw the geometry itself. The lowest zoom a class has in any
#: of them is where its rows start (`Styles.start`).
GEOMETRY_MODES = ('fill', 'line', 'casing')

#: A class carries text from the lowest zoom at which any of these is
#: styled. `shield` counts because a motorway with a ref and no name still
#: has to get one; `number` is a second text from the `label` column -- a
#: building's house number, drawn whether or not it has a name.
TEXT_MODES = ('label', 'shield', 'number')

MARKER_MODE = 'marker'

MODES = (*GEOMETRY_MODES, *TEXT_MODES, MARKER_MODE, '*')

#: Top-level keys of classes.yaml that are not modes. `templates` only
#: holds YAML anchors for the entries to merge; `defaults` is read.
TEMPLATES = 'templates'
DEFAULTS = 'defaults'


class StyleError(ValueError):
    """A style file that would produce a wrong map rather than an error."""


@dataclass(frozen=True, slots=True)
class Key:
    cls: str
    mode: str          # 'fill' | 'line' | 'casing' | 'marker' | 'label' | 'shield' | '*'
    zoom: int | None   # None: every zoom

    @property
    def order(self) -> tuple[int, int, int]:
        """Application order: `*` zoom first, then ascending; at equal zoom
        the `*` mode before the specific one."""
        return (0 if self.zoom is None else 1,
                0 if self.zoom is None else self.zoom,
                0 if self.mode == '*' else 1)


def parse_key(key: str, mode: str) -> Key:
    """`"<class> <zoom>"` or `"<class>"` under `mode`."""
    parts = str(key).split()
    if len(parts) not in (1, 2):
        raise StyleError(f'{mode}: expected "<class> <zoom>" or "<class>", got {key!r}')
    cls = parts[0]
    if '*' in cls:
        # That would be cascading across classes. Sharing goes through
        # templates and tokens, which are explicit and greppable.
        raise StyleError(f'{mode}: a class glob is not allowed in classes.yaml: {key!r}')
    if len(parts) == 1:
        return Key(cls, mode, None)
    if not parts[1].isdigit():
        raise StyleError(f'{mode}: zoom must be a number, got {key!r}')
    return Key(cls, mode, int(parts[1]))


def parse(document: dict) -> tuple[list[tuple[Key, dict]], dict[str, dict]]:
    """The file -> (entries, defaults per mode).

    An unknown section is refused rather than skipped: `lable:` would
    otherwise drop every label from the map without an error.
    """
    entries: list[tuple[Key, dict]] = []
    defaults: dict[str, dict] = {}
    for section, body in (document or {}).items():
        if section == TEMPLATES:
            continue
        if section == DEFAULTS:
            for mode, properties in (body or {}).items():
                if mode not in MODES or mode == '*':
                    raise StyleError(f'defaults: {mode!r} is not a mode')
                if not isinstance(properties, dict):
                    raise StyleError(f'defaults: {mode!r} must map to properties')
                defaults[mode] = properties
            continue
        if section not in MODES:
            raise StyleError(f'{section!r} is not a mode, {TEMPLATES!r} or {DEFAULTS!r}')
        for raw, properties in (body or {}).items():
            key = parse_key(raw, section)
            if not isinstance(properties, dict):
                raise StyleError(f'{section} {raw!r} must map to properties, got {properties!r}')
            entries.append((key, properties))
    return entries, defaults


class Styles:
    def __init__(self, document: dict, palettes: dict[str, dict]):
        self.palettes = palettes
        entries, self.defaults = parse(document)
        self._entries: dict[str, list[tuple[Key, dict]]] = {}
        for key, properties in entries:
            self._entries.setdefault(key.cls, []).append((key, properties))
        for entries in self._entries.values():
            entries.sort(key=lambda e: e[0].order)
        for cls in self._entries:
            for mode in self.modes(cls):
                if not self.zoom_keys(cls, mode):
                    # Nothing says where it starts, so it would never be drawn.
                    raise StyleError(f'{mode} {cls}: no entry has a zoom')

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self._entries)

    def modes(self, cls: str) -> frozenset[str]:
        """The modes this class is actually drawn in.

        `*` is not one of them: it carries shared properties and never
        draws on its own.
        """
        return frozenset(key.mode for key, _ in self._entries.get(cls, ())
                         if key.mode != '*')

    def zoom_keys(self, cls: str, mode: str) -> tuple[int, ...]:
        """The zooms at which this class changes appearance in this mode.

        One Mapnik `<Rule>` per key, so these are the scale-denominator
        bands the generator emits.

        An entry without a zoom is never a key: it has no zoom of its own and
        applies from the first real one onwards. A `*`-*mode* entry at a
        zoom is a key, because it changes what this mode draws -- but only
        above the zoom where the mode starts drawing at all. Below that
        there is nothing to change.

        A marker always has the key 0. Where its icon starts is the row's
        importance and the detail, not this file, so the first rule is
        the icon as the defaults and the zoomless entries describe it; the
        generator moves its lower end to where the detail's icons start.
        """
        entries = self._entries.get(cls, ())
        own = {key.zoom for key, _ in entries if key.mode == mode and key.zoom is not None}
        if mode == MARKER_MODE and mode in self.modes(cls):
            own.add(0)
        if not own:
            return ()
        shared = {key.zoom for key, _ in entries
                  if key.mode == '*' and key.zoom is not None and key.zoom > min(own)}
        return tuple(sorted(own | shared))

    def start(self, cls: str) -> int | None:
        """The lowest zoom at which the class is drawn in a geometry mode, or
        None when it never is -- a POI, drawn only as a marker, or a place,
        drawn only as text."""
        keys = [self.zoom_keys(cls, mode)[0] for mode in self.modes(cls)
                if mode in GEOMETRY_MODES]
        return min(keys, default=None)

    def text_start(self, cls: str) -> int | None:
        """The lowest zoom at which the class is given text, or None."""
        keys = [self.zoom_keys(cls, mode)[0] for mode in self.modes(cls)
                if mode in TEXT_MODES]
        return min(keys, default=None)

    def properties(self, cls: str, mode: str, zoom: int) -> dict:
        """Everything that applies at (cls, mode, zoom), later overriding
        earlier, over the mode's defaults."""
        out: dict = dict(self.defaults.get(mode, {}))
        for key, properties in self._entries.get(cls, ()):
            if key.mode not in (mode, '*'):
                continue
            if key.zoom is not None and key.zoom > zoom:
                continue
            out.update(properties)
        return out

    def omits(self, properties: dict, palette: str) -> bool:
        """Whether `palette` leaves these (unpainted) properties out: one of
        their colour tokens is `none` there."""
        tokens = self.palettes[palette]
        return any(tokens.get(value) == NONE for name, value in properties.items()
                   if name in TOKEN_PROPERTIES and isinstance(value, str))

    def paint(self, properties: dict, palette: str, mode: str) -> dict:
        """Substitute palette tokens and apply casing_scale.

        Substitution is driven by the *property*, not by the value. Asking
        "is this string a palette token?" looks simpler and is wrong: the
        two namespaces overlap, and `text: label` would be rewritten to a
        colour because `label` is also a token.
        """
        tokens = self.palettes[palette]
        out = {name: tokens.get(value, value)
               if name in TOKEN_PROPERTIES and isinstance(value, str) else value
               for name, value in properties.items()}
        if mode == 'casing' and 'line-width' in out:
            out['line-width'] = out['line-width'] * tokens[CASING_SCALE]
        return out


def symbolizers(properties: dict) -> tuple[str, ...]:
    """Which Mapnik symbolizers these properties describe, in draw order.

    More than one is normal, not an edge case: a protected area is a
    translucent fill *and* a dashed outline, a building is a fill and a
    stroke from z15. Returning a single kind would silently drop one of
    them.
    """
    return tuple(kind for kind, drawing in DRAWS
                 if any(name in properties for name in drawing))


def load(styles_dir: Path) -> Styles:
    return Styles(
        yaml.safe_load((styles_dir / 'classes.yaml').read_text()),
        yaml.safe_load((styles_dir / 'palettes.yaml').read_text()),
    )
