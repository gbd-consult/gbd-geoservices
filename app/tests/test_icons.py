"""Category icons: styles/icons.yaml -> one SVG per category and palette.

What is worth pinning is the inheritance -- of the icon, the colour and the
`draw` flag -- because all three are resolved here, into files and into
`osm_point.icon`, and nothing downstream sees them again: the marker layer
only reads `<set>/<palette>/[icon].svg` and skips a NULL icon.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from renderer import icons

TREE = [
    {'id': 'cat_a', 'subs': [
        {'id': 'cat_a_b', 'subs': [{'id': 'cat_a_b_c'}]},
        {'id': 'cat_a_d'},
    ]},
]

MAKI = ('<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 15 15">'
        '<path d="M1 1h13v13H1z"/></svg>')

TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="11" fill="$color"/><g fill="#ffffff">$icon</g></svg>')

PALETTES = {'default': {'clr_x': '#b06a20', 'clr_y': '#5a6472'},
            'dark': {'clr_x': '#c98a4b', 'clr_y': '#8f97a3'}}


@pytest.fixture
def vendored(tmp_path) -> Path:
    for relative, text in (('maki/one.svg', MAKI), ('maki/two.svg', MAKI.replace('13', '12')),
                           ('generic/three.svg', MAKI.replace('13', '11')),
                           (icons.TEMPLATE, TEMPLATE)):
        path = tmp_path / 'icons' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path / 'icons'


def test_a_category_without_an_entry_inherits_its_ancestors():
    resolved = icons.resolve(TREE, [
        {'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x', 'draw': True},
        {'category': 'cat_a_b', 'icon': 'maki/two.svg'},
    ])
    assert resolved == {'cat_a': ('maki/one.svg', True, 'clr_x'),
                        'cat_a_b': ('maki/two.svg', True, 'clr_x'),
                        'cat_a_b_c': ('maki/two.svg', True, 'clr_x'),
                        'cat_a_d': ('maki/one.svg', True, 'clr_x')}


def test_draw_and_colour_are_inherited_on_their_own():
    resolved = icons.resolve(TREE, [
        {'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x', 'draw': True},
        {'category': 'cat_a_b', 'draw': False},
        {'category': 'cat_a_d', 'color': 'clr_y'},
    ])
    assert resolved['cat_a_b_c'] == ('maki/one.svg', False, 'clr_x')
    assert resolved['cat_a_d'] == ('maki/one.svg', True, 'clr_y')


@pytest.mark.parametrize('entries,message', [
    ([], 'no icon'),
    ([{'category': 'cat_a', 'icon': 'maki/one.svg'}], 'no color'),
])
def test_a_root_without_an_icon_or_a_colour_is_refused(entries, message):
    with pytest.raises(icons.IconError, match=message):
        icons.resolve(TREE, entries)


def test_an_entry_for_a_category_the_tree_lacks_is_refused():
    """A generated id changes when the tree does; a stale entry is an icon
    nobody sees, so it fails here rather than silently."""
    with pytest.raises(icons.IconError, match='cat_gone'):
        icons.resolve(TREE, [{'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x'},
                             {'category': 'cat_gone', 'icon': 'maki/two.svg'}])


def test_the_template_bakes_in_each_palettes_colour(vendored):
    """Mapnik's marker `fill` would recolour the white disc and the white
    icon too, so the colour has to be in the file -- one file per palette."""
    texts, keys, _ = icons.build(
        TREE, [{'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x'}], vendored, PALETTES)
    name = keys['cat_a']
    assert name == 'maki-one.clr_x'
    assert 'fill="#b06a20"' in texts['default'][name]
    assert 'fill="#c98a4b"' in texts['dark'][name]
    assert '<path d="M1 1h13v13H1z"/>' in texts['default'][name]
    assert '<svg' not in texts['default'][name].split('<g', 1)[1], 'the icon goes in without its <svg>'


def test_a_file_per_icon_and_colour_not_per_category(vendored):
    """A category that inherits both shares its ancestor's file; one that
    sets only a colour gets a file of its own."""
    texts, keys, drawn = icons.build(TREE, [
        {'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x', 'draw': True},
        {'category': 'cat_a_d', 'color': 'clr_y', 'draw': False},
    ], vendored, PALETTES)
    assert keys == {'cat_a': 'maki-one.clr_x', 'cat_a_b': 'maki-one.clr_x',
                    'cat_a_b_c': 'maki-one.clr_x', 'cat_a_d': 'maki-one.clr_y'}
    assert set(texts['default']) == {'maki-one.clr_x', 'maki-one.clr_y'}
    # Only drawn categories get an icon on the map; search shows every one.
    assert drawn == {'cat_a': 'maki-one.clr_x', 'cat_a_b': 'maki-one.clr_x',
                     'cat_a_b_c': 'maki-one.clr_x'}


def test_a_colour_missing_from_a_palette_is_refused(vendored):
    with pytest.raises(icons.IconError, match="not in palette 'dark'"):
        icons.build(TREE, [{'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x'}],
                    vendored, {**PALETTES, 'dark': {'clr_y': '#000000'}})


def test_write_puts_one_file_per_key_and_the_keys_of_every_category(tmp_path, vendored):
    model = tmp_path / 'model'
    (model / 'generated').mkdir(parents=True)
    (model / 'generated' / 'categories.yaml').write_text(yaml.safe_dump(TREE))
    styles = vendored.parent
    (styles / 'palettes.yaml').write_text(yaml.safe_dump(PALETTES))
    (styles / 'icons.yaml').write_text(yaml.safe_dump([
        {'category': 'cat_a', 'icon': 'maki/one.svg', 'color': 'clr_x', 'draw': True},
        {'category': 'cat_a_d', 'icon': 'generic/three.svg', 'draw': False},
    ]))
    data = tmp_path / 'data'
    first, drawn = icons.write(model, styles, data)
    assert icons.current(data) == first
    assert set(drawn) == {'cat_a', 'cat_a_b', 'cat_a_b_c'}
    for palette in PALETTES:
        assert {p.stem for p in (first / palette).iterdir()} == {
            'maki-one.clr_x', 'generic-three.clr_x'}
    keys = json.loads((first / icons.KEYS).read_text())
    assert keys['cat_a_d'] == 'generic-three.clr_x'

    # A changed icon is a new directory, so a reloaded Map cannot get the
    # old file from Mapnik's marker cache, which is keyed by path.
    (styles / 'icons.yaml').write_text(yaml.safe_dump([
        {'category': 'cat_a', 'icon': 'maki/two.svg', 'color': 'clr_x', 'draw': True}]))
    second, _ = icons.write(model, styles, data)
    assert second != first and icons.current(data) == second
    assert first.is_dir(), 'the set before stays for a process that has not reloaded'


def test_update_points_sets_the_drawn_and_clears_the_rest(db, temp_schema):
    """The style run owns `icon` on osm_point and osm_label: a category
    turned off in icons.yaml loses its icon, and with it every marker, without
    a re-import -- and its label no longer yields to an icon that is gone."""
    from importer import tables as t

    db.execute(t.ddl(temp_schema, t.OSM_POINT))
    db.execute(t.ddl(temp_schema, t.OSM_LABEL))
    for osm_id, category, icon in ((1, 'cat_a', None), (2, 'cat_a_d', 'stale.clr_x'),
                                   (3, 'cat_a_b', 'maki-one.clr_x')):
        db.execute(f"insert into {temp_schema}.osm_point (osm_id, class, z_order, minzoom,"
                   f" category, icon, geom) values (%s, 'cls_poi_x', 0, 14, %s, %s,"
                   f" st_setsrid(st_point(0, 0), 3857))", (osm_id, category, icon))
        db.execute(f"insert into {temp_schema}.osm_label (osm_id, class, z_order, minzoom_label,"
                   f" category, icon, geom) values (%s, 'cls_poi_x', 0, 14, %s, %s,"
                   f" st_setsrid(st_point(0, 0), 3857))", (osm_id, category, icon))
    changed = icons.update_points(db, temp_schema, {'cat_a': 'maki-one.clr_x',
                                                    'cat_a_b': 'maki-one.clr_x'})
    for table in ('osm_point', 'osm_label'):
        rows = dict(db.execute(f'select osm_id, icon from {temp_schema}.{table}').fetchall())
        assert rows == {1: 'maki-one.clr_x', 2: None, 3: 'maki-one.clr_x'}, table
    assert changed == 4, 'a row whose icon is already right is not rewritten'


def test_the_real_files_resolve():
    from importer.run import MODEL, STYLES

    tree = yaml.safe_load((MODEL / 'generated' / 'categories.yaml').read_text())
    entries = yaml.safe_load((STYLES / 'icons.yaml').read_text())
    palettes = yaml.safe_load((STYLES / 'palettes.yaml').read_text())
    texts, keys, drawn = icons.build(tree, entries, STYLES / 'icons', palettes)
    assert set(texts) == set(palettes)
    assert set(drawn) < set(keys)
    assert len(texts['default']) < len(keys) / 2, 'inheriting categories share their files'


# --- the route ---------------------------------------------------------------

def test_the_route_serves_an_icon_with_a_day_of_cache(tmp_path, monkeypatch):
    from web import icons as icon_routes
    from web.main import app

    icon_set = tmp_path / 'set'
    (icon_set / icons.DEFAULT_PALETTE).mkdir(parents=True)
    (icon_set / icons.DEFAULT_PALETTE / 'maki-one.clr_x.svg').write_text(MAKI)
    (icon_set / icons.KEYS).write_text(json.dumps({'cat_a': 'maki-one.clr_x'}))
    monkeypatch.setattr(icon_routes.icons_module, 'current', lambda data_dir: icon_set)
    client = TestClient(app)
    response = client.get('/icons/cat_a.svg')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('image/svg+xml')
    assert response.headers['cache-control'] == 'public, max-age=86400'
    assert client.get('/icons/cat_nope.svg').status_code == 404
    assert client.get('/icons/..%2Fsecret.svg').status_code == 404


def test_nocache_serves_icons_no_store(tmp_path, monkeypatch):
    """An icon edit under the devtools watcher is a new file at the same
    URL; a day of browser cache would keep showing the old one."""
    from lib import config
    from web import icons as icon_routes
    from web.main import app

    icon_set = tmp_path / 'set'
    (icon_set / icons.DEFAULT_PALETTE).mkdir(parents=True)
    (icon_set / icons.DEFAULT_PALETTE / 'maki-one.clr_x.svg').write_text(MAKI)
    (icon_set / icons.KEYS).write_text(json.dumps({'cat_a': 'maki-one.clr_x'}))
    monkeypatch.setattr(icon_routes.icons_module, 'current', lambda data_dir: icon_set)
    real = config.opt
    monkeypatch.setattr(config, 'opt',
                        lambda path, default=None: True if path == 'nocache' else real(path, default))
    response = TestClient(app).get('/icons/cat_a.svg')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
