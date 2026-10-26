"""WMTS: both bindings and the capabilities document.

The capabilities document is a contract with clients nobody here controls --
QGIS above all, which is also the client that can only send `?key=`. So most
of what is checked is the document's *shape*: that what it advertises is what
the server serves, and that a URL taken out of it works.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from web import serving, wmts
from web.main import app

NS = {'w': 'http://www.opengis.net/wmts/1.0',
      'o': 'http://www.opengis.net/ows/1.1',
      'x': 'http://www.w3.org/1999/xlink'}

#: Vaduz, computed from each grid rather than guessed.
WEB_MERCATOR = (14, 8624, 5749)
UTM = (8, 119, 220)

THEMES = ('default_std',)


@pytest.fixture(scope='module')
def served():
    from conftest import small_schema

    from lib import db
    from renderer import core

    schema = small_schema()
    if schema is None or not core.available_themes(schema):
        pytest.skip('no compiled styles for `li`; run manage.py compile-styles li')
    original = db.active_schema
    db.active_schema = lambda area=None: schema
    from web import serving
    serving.reset()
    # Both grids, because that is what this module is about. Two themes'
    # worth of Mapnik parses rather than twenty-four.
    for matrix_set in ('GoogleMapsCompatible', 'DE_EPSG_25832_ADV'):
        core.get_registry().preload(
            THEMES, lambda theme, s: core.xml_path_for(theme, schema, s), matrix_set)
    try:
        yield TestClient(app)
    finally:
        db.active_schema = original
        serving.reset()


@pytest.fixture(scope='module')
def capabilities(served):
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetCapabilities')
    assert response.status_code == 200
    assert 'xml' in response.headers['content-type']
    return ET.fromstring(response.content)


# --- the document --------------------------------------------------------

def test_it_is_a_wmts_1_0_0_capabilities(capabilities):
    assert capabilities.tag == '{http://www.opengis.net/wmts/1.0}Capabilities'
    assert capabilities.get('version') == '1.0.0'
    identification = capabilities.find('o:ServiceIdentification', NS)
    assert identification.find('o:ServiceType', NS).text == 'OGC WMTS'
    assert identification.find('o:ServiceTypeVersion', NS).text == '1.0.0'


def test_every_compiled_theme_is_a_layer(capabilities, served):
    from lib import db
    from renderer import core

    advertised = {e.text for e in capabilities.findall('.//w:Layer/o:Identifier', NS)}
    assert advertised == {serving.url_name(theme) for theme in core.available_themes(db.active_schema())}


def test_exactly_the_configured_sets_are_advertised(capabilities):
    """Computed from `styles/grids.yaml` through `renderer.matrix`, not
    hand-defined, so what is advertised and what is served cannot
    drift.
    """
    contents = capabilities.find('w:Contents', NS)
    sets = {tms.find('o:Identifier', NS).text
            for tms in contents.findall('w:TileMatrixSet', NS)}
    assert sets == set(wmts.matrix_sets())


def test_each_set_carries_its_crs_and_every_level(capabilities):
    contents = capabilities.find('w:Contents', NS)
    for element in contents.findall('w:TileMatrixSet', NS):
        identifier = element.find('o:Identifier', NS).text
        tms = wmts.matrix_sets()[identifier]
        assert element.find('o:SupportedCRS', NS).text == tms.crs
        levels = element.findall('w:TileMatrix', NS)
        assert len(levels) == tms.levels


def test_the_web_mercator_scale_denominators_are_the_standard_ones(capabilities):
    """Every WMTS GoogleMapsCompatible table lists these; a client that
    knows the set compares them."""
    contents = capabilities.find('w:Contents', NS)
    gmc = next(e for e in contents.findall('w:TileMatrixSet', NS)
               if e.find('o:Identifier', NS).text == 'GoogleMapsCompatible')
    levels = gmc.findall('w:TileMatrix', NS)
    assert float(levels[0].find('w:ScaleDenominator', NS).text) == pytest.approx(
        559_082_264.0287178)
    assert float(levels[1].find('w:ScaleDenominator', NS).text) == pytest.approx(
        279_541_132.0143589)


def test_a_matrix_declares_its_grid(capabilities):
    contents = capabilities.find('w:Contents', NS)
    first = contents.find('w:TileMatrixSet', NS).findall('w:TileMatrix', NS)[0]
    assert first.find('w:TileWidth', NS).text == '256'
    assert first.find('w:MatrixWidth', NS).text == '1'     # one tile at level 0
    assert len(first.find('w:TopLeftCorner', NS).text.split()) == 2


def test_a_layer_advertises_every_raster_format(capabilities):
    from web import formats

    layer = capabilities.find('.//w:Layer', NS)
    advertised = {e.text for e in layer.findall('w:Format', NS)}
    assert advertised == {formats.mime_for(f) for f in formats.RASTER}


def test_a_layer_links_every_set(capabilities):
    """True because the generator writes every theme for every set or
    fails before writing anything."""
    layer = capabilities.find('.//w:Layer', NS)
    linked = {e.text for e in layer.findall('w:TileMatrixSetLink/w:TileMatrixSet', NS)}
    assert linked == set(wmts.matrix_sets())


def test_a_layer_has_a_global_bounding_box(capabilities):
    """The pyramid is global even where the data is not.

    Advertising the imported extent would make a client refuse to request
    the empty tiles it is entitled to.
    """
    box = capabilities.find('.//w:Layer/o:WGS84BoundingBox', NS)
    assert box.find('o:LowerCorner', NS).text.startswith('-180')
    assert box.find('o:UpperCorner', NS).text.startswith('180')


# --- the ResourceURL contract --------------------------------------------

def test_a_resource_url_from_the_document_actually_works(served, capabilities):
    """The only check that matters for a client: take a template, fill it
    in, and fetch it."""
    layer = next(e for e in capabilities.findall('.//w:Layer', NS)
                 if e.find('o:Identifier', NS).text == 'std')
    template = next(e.get('template') for e in layer.findall('w:ResourceURL', NS)
                    if e.get('format') == 'image/png')
    level, col, row = WEB_MERCATOR
    url = (template
           .replace('{TileMatrixSet}', 'GoogleMapsCompatible')
           .replace('{TileMatrix}', str(level))
           .replace('{TileCol}', str(col))
           .replace('{TileRow}', str(row)))
    path = url.split('/', 3)[-1]
    response = served.get('/' + path)
    assert response.status_code == 200
    assert response.content[:4] == b'\x89PNG'


def test_the_key_is_carried_into_the_templates(served):
    """QGIS is the client that matters most and `?key=` is the only carrier
    it can send, so a capabilities document fetched with a key must
    advertise tile URLs that have it -- otherwise every layer a user adds
    from it is unauthorised."""
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetCapabilities&key=demo123')
    root = ET.fromstring(response.content)
    templates = [e.get('template') for e in root.findall('.//w:ResourceURL', NS)]
    assert templates and all(t.endswith('?key=demo123') for t in templates)


def test_no_key_sent_means_no_key_advertised(capabilities):
    templates = [e.get('template') for e in capabilities.findall('.//w:ResourceURL', NS)]
    assert templates and not any('key=' in t for t in templates)


# --- the legend ----------------------------------------------------------

def test_a_layer_names_its_legend_and_the_url_serves_it(served, capabilities):
    """QGIS shows a WMTS layer's legend from its default style's
    `LegendURL` and from nowhere else; a Style without `ows:Identifier` is
    not valid WMTS either."""
    for layer in capabilities.findall('.//w:Layer', NS):
        style = layer.find('w:Style', NS)
        assert style.find('o:Identifier', NS).text == 'default'
        href = style.find('w:LegendURL', NS).get(f'{{{NS["x"]}}}href')
        theme = layer.find('o:Identifier', NS).text
        assert href.endswith(f'/legend/{theme}.png')
    response = served.get('/' + href.split('/', 3)[-1])
    assert response.status_code == 200
    assert response.content[:4] == b'\x89PNG'


def test_the_legend_url_carries_the_language_and_no_key(served):
    """The key stays in the tile templates: `/legend` takes none, and a
    client that follows a `LegendURL` need not be one that sends it."""
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetCapabilities&key=demo123&lang=en')
    root = ET.fromstring(response.content)
    hrefs = [e.get(f'{{{NS["x"]}}}href') for e in root.findall('.//w:LegendURL', NS)]
    assert hrefs and all(h.endswith('.png?lang=en') for h in hrefs)


def test_an_unserved_language_is_not_written_into_the_legend_url(served):
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetCapabilities&lang=x%26y')
    root = ET.fromstring(response.content)
    hrefs = [e.get(f'{{{NS["x"]}}}href') for e in root.findall('.//w:LegendURL', NS)]
    assert hrefs and not any('x&y' in h for h in hrefs)


# --- GetTile, both bindings ----------------------------------------------

def test_the_restful_binding_serves(served):
    level, col, row = WEB_MERCATOR
    response = served.get(f'/wmts/std/GoogleMapsCompatible/{level}/{col}/{row}.png')
    assert response.status_code == 200
    assert len(response.content) > 10_000


def test_the_reprojected_set_serves(served):
    """EPSG:25832, the whole reason the sets are computed rather than
    assumed to be Web Mercator."""
    level, col, row = UTM
    response = served.get(f'/wmts/std/DE_EPSG_25832_ADV/{level}/{col}/{row}.png')
    assert response.status_code == 200
    assert len(response.content) > 10_000


def test_the_kvp_binding_serves_the_same_bytes(served):
    level, col, row = WEB_MERCATOR
    rest = served.get(f'/wmts/std/GoogleMapsCompatible/{level}/{col}/{row}.png')
    kvp = served.get('/wmts', params={
        'SERVICE': 'WMTS', 'VERSION': '1.0.0', 'REQUEST': 'GetTile',
        'LAYER': 'std', 'TILEMATRIXSET': 'GoogleMapsCompatible',
        'TILEMATRIX': str(level), 'TILEROW': str(row), 'TILECOL': str(col),
        'FORMAT': 'image/png'})
    assert kvp.status_code == 200
    assert kvp.content == rest.content


def test_kvp_parameter_names_are_case_insensitive(served):
    """The spec says names are; values are not, and a theme is a filename."""
    level, col, row = WEB_MERCATOR
    response = served.get('/wmts', params={
        'service': 'WMTS', 'request': 'GetTile', 'layer': 'std',
        'tilematrixset': 'GoogleMapsCompatible', 'tilematrix': str(level),
        'tilerow': str(row), 'tilecol': str(col), 'format': 'image/png'})
    assert response.status_code == 200


def test_format_is_optional_and_defaults_to_png(served):
    """Several clients omit it, and refusing them over a parameter with one
    sensible answer helps nobody."""
    level, col, row = WEB_MERCATOR
    response = served.get('/wmts', params={
        'SERVICE': 'WMTS', 'REQUEST': 'GetTile', 'LAYER': 'std',
        'TILEMATRIXSET': 'GoogleMapsCompatible', 'TILEMATRIX': str(level),
        'TILEROW': str(row), 'TILECOL': str(col)})
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'


def test_tilematrixset_defaults_to_web_mercator(served):
    level, col, row = WEB_MERCATOR
    response = served.get('/wmts', params={
        'SERVICE': 'WMTS', 'REQUEST': 'GetTile', 'LAYER': 'std',
        'TILEMATRIX': str(level), 'TILEROW': str(row), 'TILECOL': str(col)})
    assert response.status_code == 200
    assert wmts.default_set() == 'GoogleMapsCompatible'


# --- refusals ------------------------------------------------------------

def test_an_unconfigured_set_is_404(served):
    """Not an on-demand render in a projection nothing was compiled for."""
    response = served.get('/wmts/std/EPSG4326/5/1/1.png')
    assert response.status_code == 404
    assert 'EPSG4326' in response.json()['detail']


def test_an_unknown_layer_is_404(served):
    assert served.get('/wmts/nosuch/GoogleMapsCompatible/5/1/1.png').status_code == 404


def test_an_address_outside_the_pyramid_is_404(served):
    assert served.get(
        '/wmts/std/GoogleMapsCompatible/2/99/99.png').status_code == 404


@pytest.mark.parametrize('missing', ['LAYER', 'TILEMATRIX', 'TILEROW', 'TILECOL'])
def test_a_missing_required_parameter_names_itself(served, missing):
    params = {'SERVICE': 'WMTS', 'REQUEST': 'GetTile', 'LAYER': 'std',
              'TILEMATRIX': '5', 'TILEROW': '1', 'TILECOL': '1'}
    del params[missing]
    response = served.get('/wmts', params=params)
    assert response.status_code == 400
    assert missing in response.json()['detail']


def test_a_non_numeric_tile_address_is_400_not_500(served):
    response = served.get('/wmts', params={
        'SERVICE': 'WMTS', 'REQUEST': 'GetTile', 'LAYER': 'std',
        'TILEMATRIX': 'five', 'TILEROW': '1', 'TILECOL': '1'})
    assert response.status_code == 400


def test_an_unknown_operation_is_400(served):
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetFeatureInfo')
    assert response.status_code == 400
    assert 'GetCapabilities' in response.json()['detail']


def test_head_is_answered_on_the_restful_binding(served):
    level, col, row = WEB_MERCATOR
    response = served.head(f'/wmts/std/GoogleMapsCompatible/{level}/{col}/{row}.png')
    assert response.status_code == 200


def test_the_reprojected_tile_comes_from_the_reprojected_xml(served, db, small):
    """The check `test_the_reprojected_set_serves` cannot make.

    That one asserts 200 and a plausible size, which a tile rendered from
    the *wrong* grid's XML also satisfies -- and did. This renders the same
    address both ways and requires the served bytes to be the DE_EPSG_25832_ADV ones.

    The address is *searched for* rather than picked: the two XMLs differ by
    two thirds of a zoom, so at most addresses nothing crosses a rule
    boundary and they agree byte for byte. A hand-picked tile that happens
    to agree is a test that passes against the bug.
    """
    from renderer import core, matrix, precache

    tms = matrix.load()['DE_EPSG_25832_ADV']
    extent = precache.extent_for(db, small, 'EPSG:25832')

    for level in (6, 7, 8):
        for col, row in tms.tiles_in(level, extent):
            bbox = tms.bbox(level, col, row)
            correct = core.render_tile('default_std', bbox, 'png', tms.crs, tms.identifier)
            other = core.render_tile('default_std', bbox, 'png', tms.crs,
                                     'GoogleMapsCompatible')
            if correct != other:
                response = served.get(f'/wmts/std/DE_EPSG_25832_ADV/{level}/{col}/{row}.png')
                assert response.status_code == 200
                assert response.content == correct, 'served the wrong grid\'s XML'
                assert response.content != other
                return
    pytest.fail('no address found where the two grids disagree; '
                'the fixture cannot tell them apart')
