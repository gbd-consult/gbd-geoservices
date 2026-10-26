"""Category icons: `styles/icons.yaml` -> icon files, and each point's icon.

Written by `manage.py compile-styles` (which the app also runs when it starts),
never by the importer. The importer stores a point's own category in
`osm_point.category`; this module resolves `styles/icons.yaml` -- icon,
colour and `draw`, each inherited down the tree on its own -- and writes

- one file per (icon, colour) pair actually used, per palette:
  `styles/icons/template.svg` filled in with the icon and the palette's
  colour. The key names the pair (`maki-restaurant.clr_poi_food`), so a
  category that inherits its icon shares its parent's file rather than
  getting a copy of its own;
- `osm_point.icon`: that key for every point whose category is drawn, NULL
  for one whose category is not. The marker layer reads
  `<set>/<palette>/[icon].svg` and skips NULL, so an undrawn category is
  never fetched at all -- a missing marker file is logged by Mapnik per
  object per render, which is what this replaced.

The colour is baked into the file rather than applied by Mapnik, because a
MarkersSymbolizer's `fill` recolours every shape of the SVG -- the white disc
and the white icon included. Changing an icon, a colour or whether a
category is drawn is a style run: new files and one UPDATE, never a
re-import.

A set lives in a directory named by its content hash, and `current` names
the one in use. A changed icon is therefore a new path, and a reloaded Map
cannot be served a stale SVG from Mapnik's in-process marker cache, which
is keyed by path. `keys.json` in the set maps every category, drawn or not,
to its key, for search results (`/icons/<category>.svg`).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import string
from pathlib import Path

import yaml
from psycopg import sql

CURRENT = 'current'
KEYS = 'keys.json'
TEMPLATE = 'template.svg'

#: The palette search results show.
DEFAULT_PALETTE = 'default'


class IconError(ValueError):
    """icons.yaml names a category, a file or a colour that does not exist."""


def resolve(tree: list[dict], entries: list[dict]) -> dict[str, tuple[str, bool, str]]:
    """{category: (icon path, draw, colour token)} for every category of the deep tree."""
    by_category: dict[str, dict] = {}
    for entry in entries:
        category = entry['category']
        if category in by_category:
            raise IconError(f'icons.yaml: {category!r} is listed twice')
        by_category[category] = entry

    out: dict[str, tuple[str, bool, str]] = {}

    def walk(nodes, icon, draw, color):
        for node in nodes:
            entry = by_category.get(node['id'], {})
            own_icon = entry.get('icon', icon)
            own_draw = bool(entry.get('draw', draw))
            own_color = entry.get('color', color)
            if own_icon is None:
                raise IconError(f'icons.yaml: {node["id"]!r} has no icon and inherits none')
            if own_color is None:
                raise IconError(f'icons.yaml: {node["id"]!r} has no color and inherits none')
            out[node['id']] = (own_icon, own_draw, own_color)
            walk(node.get('subs') or [], own_icon, own_draw, own_color)

    walk(tree, None, False, None)
    unknown = sorted(set(by_category) - set(out))
    if unknown:
        raise IconError(f'icons.yaml names categories the tree does not have: {", ".join(unknown)}')
    return out


def key(icon: str, color: str) -> str:
    """The file name of an (icon, colour) pair: `maki/restaurant.svg`, `clr_poi_food`
    -> `maki-restaurant.clr_poi_food`."""
    return f'{icon.removesuffix(".svg").replace("/", "-")}.{color}'


def glyph(path: Path) -> str:
    """The drawing inside an icon's `<svg>`, to put into the template."""
    match = re.search(r'<svg\b[^>]*>(.*)</svg>', path.read_text(), re.S)
    if not match:
        raise IconError(f'{path}: no <svg> element')
    return match.group(1).strip()


def build(tree: list[dict], entries: list[dict], vendored: Path, palettes: dict[str, dict]
          ) -> tuple[dict[str, dict[str, str]], dict[str, str], dict[str, str]]:
    """({palette: {key: svg text}}, {category: key}, {drawn category: key})."""
    resolved = resolve(tree, entries)
    template = string.Template((vendored / TEMPLATE).read_text())
    glyphs: dict[str, str] = {}
    texts: dict[str, dict[str, str]] = {palette: {} for palette in palettes}
    keys: dict[str, str] = {}
    for category, (relative, _draw, token) in resolved.items():
        name = keys[category] = key(relative, token)
        if name in texts[next(iter(texts))]:
            continue
        if relative not in glyphs:
            path = vendored / relative
            if not path.is_file():
                raise IconError(f'icons.yaml: no file {relative!r} under {vendored}')
            glyphs[relative] = glyph(path)
        for palette, tokens in palettes.items():
            if token not in tokens:
                raise IconError(f'icons.yaml: color {token!r} of {category!r} is not in palette {palette!r}')
            texts[palette][name] = template.substitute(color=tokens[token], icon=glyphs[relative])
    drawn = {category: keys[category] for category, (_icon, draw, _color) in resolved.items() if draw}
    return texts, keys, drawn


def drawn_keys(model_dir: Path, styles_dir: Path) -> dict[str, str]:
    """{drawn category: key}, as `write` returns it, without building or
    writing a file: what the style checks need before anything is written."""
    tree = yaml.safe_load((model_dir / 'generated' / 'categories.yaml').read_text())
    entries = yaml.safe_load((styles_dir / 'icons.yaml').read_text()) or []
    return {category: key(icon, color)
            for category, (icon, draw, color) in resolve(tree, entries).items() if draw}


def digest(texts: dict[str, dict[str, str]], keys: dict[str, str]) -> str:
    payload = json.dumps({'texts': texts, 'keys': keys}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write(model_dir: Path, styles_dir: Path, data_dir: Path) -> tuple[Path, dict[str, str]]:
    """Write the icon set, point `current` at it; its directory and {drawn category: key}."""
    tree = yaml.safe_load((model_dir / 'generated' / 'categories.yaml').read_text())
    entries = yaml.safe_load((styles_dir / 'icons.yaml').read_text()) or []
    palettes = yaml.safe_load((styles_dir / 'palettes.yaml').read_text())
    texts, keys, drawn = build(tree, entries, styles_dir / 'icons', palettes)
    root = data_dir / 'styles' / 'icons'
    name = digest(texts, keys)
    target = root / name
    if not target.is_dir():
        staging = root / f'.{name}.tmp'
        shutil.rmtree(staging, ignore_errors=True)
        for palette, by_key in texts.items():
            (staging / palette).mkdir(parents=True)
            for icon_key, text in by_key.items():
                (staging / palette / f'{icon_key}.svg').write_text(text)
        (staging / KEYS).write_text(json.dumps(keys, sort_keys=True))
        staging.rename(target)

    previous = current(data_dir)
    pointer = root / f'.{CURRENT}.tmp'
    pointer.write_text(name)
    pointer.replace(root / CURRENT)
    # The set before this one stays: a process that has not reloaded yet
    # still has XML pointing into it.
    keep = {name, previous.name if previous else None}
    for stale in root.iterdir():
        if stale.is_dir() and not stale.name.startswith('.') and stale.name not in keep:
            shutil.rmtree(stale)
    return target, drawn


#: The tables whose `icon` the style run sets. osm_label's says whether the
#: object's label yields to its icon (renderer/queries.py).
ICON_TABLES = ('osm_point', 'osm_label')


def mapping_key(drawn: dict[str, str]) -> str:
    """What `update_points` was given, as a short hash: equal keys, equal icons."""
    return hashlib.sha256(json.dumps(sorted(drawn.items())).encode()).hexdigest()[:16]


def update_points(conn, schema: str, drawn: dict[str, str]) -> int:
    """Set `icon` on osm_point and osm_label from {drawn category: key};
    NULL for every other.

    One transaction, so a tile rendered meanwhile sees the old icons or the
    new ones, never a mix -- and never an icon on one table and not yet on
    the other, which would draw a label and its icon both, or neither. Rows
    whose icon does not change are left alone, so a style run that changed
    nothing about icons writes nothing. Returns the rows changed.
    """
    changed = 0
    with conn.transaction():
        conn.execute('create temporary table _icon (category text primary key, icon text not null)'
                     ' on commit drop')
        with conn.cursor().copy('copy _icon (category, icon) from stdin') as copy:
            for category, icon_key in drawn.items():
                copy.write_row((category, icon_key))
        for name in ICON_TABLES:
            table = sql.Identifier(schema, name)
            changed += conn.execute(sql.SQL(
                'update {} p set icon = i.icon from _icon i'
                ' where i.category = p.category and p.icon is distinct from i.icon'
            ).format(table)).rowcount
            # An array, not `not exists` against _icon: the import's
            # statistics say no row has an icon, so after the update above
            # the planner still expects one row and rescans _icon for each of
            # millions (on de: minutes at 100 % CPU).
            changed += conn.execute(sql.SQL(
                'update {} p set icon = null where p.icon is not null'
                ' and (p.category is null or p.category <> all(%(drawn)s))'
            ).format(table), {'drawn': list(drawn)}).rowcount
    return changed


def current(data_dir: Path) -> Path | None:
    """The icon set in use, or None before the first `manage.py compile-styles`."""
    root = data_dir / 'styles' / 'icons'
    try:
        name = (root / CURRENT).read_text().strip()
    except FileNotFoundError:
        return None
    path = root / name
    return path if name and path.is_dir() else None
