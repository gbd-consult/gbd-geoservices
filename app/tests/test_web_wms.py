"""WMS: the capabilities document and GetMap in every served CRS.

As for WMTS, the capabilities are a contract with QGIS and other clients
nobody here controls: what they advertise must be what GetMap serves.
"""

from __future__ import annotations

import struct
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from web import serving, wms
from web.main import app

NS = {'w': 'http://www.opengis.net/wms', 'x': 'http://www.w3.org/1999/xlink'}

THEMES = ('default_std',)


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', data[16:24])


@pytest.fixture(scope='module')
def served():
    from conftest import small_schema

    from lib import db
    from renderer import core, matrix

    schema = small_schema()
    if schema is None or not core.available_themes(schema):
        pytest.skip('no compiled styles for `li`; run manage.py compile-styles li')
    original = db.active_schema
    db.active_schema = lambda area=None: schema
    serving.reset()
    # Every served grid: each CRS renders with one of them.
    for matrix_set in matrix.load():
        core.get_registry().preload(
            THEMES, lambda theme, s: core.xml_path_for(theme, schema, s), matrix_set)
    try:
        yield TestClient(app)
    finally:
        db.active_schema = original
        serving.reset()


@pytest.fixture(scope='module')
def capabilities(served):
    response = served.get('/wms?SERVICE=WMS&REQUEST=GetCapabilities')
    assert response.status_code == 200
    assert 'xml' in response.headers['content-type']
    return ET.fromstring(response.content)


def get_map(client, crs, bbox, *, version='1.3.0', width=300, height=200, **extra):
    crs_param = 'SRS' if version == '1.1.1' else 'CRS'
    params = {'SERVICE': 'WMS', 'VERSION': version, 'REQUEST': 'GetMap',
              'LAYERS': 'std', 'STYLES': '', crs_param: crs,
              'BBOX': ','.join(repr(v) for v in bbox),
              'WIDTH': width, 'HEIGHT': height, 'FORMAT': 'image/png', **extra}
    return client.get('/wms', params=params)


# --- the document --------------------------------------------------------

def test_it_is_a_wms_1_3_0_capabilities(capabilities):
    assert capabilities.tag == '{http://www.opengis.net/wms}WMS_Capabilities'
    assert capabilities.get('version') == '1.3.0'
    assert capabilities.find('w:Service/w:Name', NS).text == 'WMS'


def test_the_four_crs_are_advertised_for_the_default_grids(capabilities):
    advertised = {e.text for e in capabilities.findall('w:Capability/w:Layer/w:CRS', NS)}
    assert advertised == set(wms.served_crs())
    assert advertised == {'EPSG:3857', 'EPSG:4326', 'EPSG:25832', 'EPSG:25833'}


def test_every_compiled_theme_is_a_layer(capabilities):
    from lib import db
    from renderer import core

    names = {e.text for e in capabilities.findall('.//w:Layer/w:Layer/w:Name', NS)}
    assert names == {serving.url_name(t) for t in core.available_themes(db.active_schema())}


def test_the_key_is_carried_into_the_operation_urls(served):
    """QGIS can only send `?key=`; without it every GetMap is unauthorised."""
    response = served.get('/wms?SERVICE=WMS&REQUEST=GetCapabilities&key=demo123')
    root = ET.fromstring(response.content)
    hrefs = [e.get(f'{{{NS["x"]}}}href')
             for e in root.findall('.//w:DCPType/w:HTTP/w:Get/w:OnlineResource', NS)]
    assert hrefs and all(h.endswith('/wms?key=demo123') for h in hrefs)
    legends = root.findall('.//w:LegendURL/w:OnlineResource', NS)
    assert legends and not any('key=' in e.get(f'{{{NS["x"]}}}href') for e in legends)


def test_the_wmts_document_keeps_its_default_namespace(served, capabilities):
    """Building the WMS document must not take WMTS's default prefix."""
    response = served.get('/wmts?SERVICE=WMTS&REQUEST=GetCapabilities')
    assert b'<Capabilities' in response.content


# --- GetMap ---------------------------------------------------------------

@pytest.mark.parametrize('crs', ['EPSG:3857', 'EPSG:25832', 'EPSG:25833', 'EPSG:4326'])
def test_get_map_serves_the_requested_size_in_each_crs(served, db, small, crs):
    from renderer import precache

    bbox = precache.extent_for(db, small, crs)
    if crs == 'EPSG:4326':
        bbox = (bbox[1], bbox[0], bbox[3], bbox[2])
    response = get_map(served, crs, bbox, width=640, height=480)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'image/png'
    assert png_size(response.content) == (640, 480)


def test_4326_is_lat_lon_in_1_3_0_and_lon_lat_in_1_1_1(served, db, small):
    """The same ground both ways must be the same image; read the wrong way
    round the 1.3.0 bbox is a different place."""
    from renderer import precache

    lon_lat = precache.extent_for(db, small, 'EPSG:4326')
    lat_lon = (lon_lat[1], lon_lat[0], lon_lat[3], lon_lat[2])
    new = get_map(served, 'EPSG:4326', lat_lon)
    old = get_map(served, 'EPSG:4326', lon_lat, version='1.1.1')
    swapped = get_map(served, 'EPSG:4326', lon_lat)
    assert new.status_code == old.status_code == swapped.status_code == 200
    assert new.content == old.content
    assert new.content != swapped.content


def test_a_tile_after_a_map_is_tile_sized_again(served, db, small):
    """A WMS render resizes a pooled tile handle; the next tile on it must
    size it back, or the cache fills with maps of the wrong size."""
    from lib import config
    from renderer import core, matrix, precache

    bbox = precache.extent_for(db, small, 'EPSG:3857')
    assert get_map(served, 'EPSG:3857', bbox, width=500, height=300).status_code == 200
    tms = matrix.load()['GoogleMapsCompatible']
    for _ in range(int(config.opt('map_pool_size', 4)) + 1):
        data = core.render_tile('default_std', tms.bbox(14, 8624, 5749), 'png',
                                tms.crs, tms.identifier)
        assert png_size(data) == (core.TILE_SIZE, core.TILE_SIZE)


def test_parameter_names_are_case_insensitive(served):
    response = served.get('/wms?service=WMS&request=GetMap&layers=std&styles=&crs=EPSG:3857'
                          '&bbox=1059000,5960000,1061000,5962000&width=64&height=64')
    assert response.status_code == 200
    assert png_size(response.content) == (64, 64)


@pytest.mark.parametrize('missing', ['LAYERS', 'CRS', 'BBOX', 'WIDTH', 'HEIGHT'])
def test_a_missing_parameter_names_itself(served, missing):
    params = {'SERVICE': 'WMS', 'REQUEST': 'GetMap', 'LAYERS': 'std', 'CRS': 'EPSG:3857',
              'BBOX': '0,0,1,1', 'WIDTH': '10', 'HEIGHT': '10'}
    del params[missing]
    response = served.get('/wms', params=params)
    assert response.status_code == 400
    assert missing in response.json()['detail']


@pytest.mark.parametrize('change, status', [
    ({'CRS': 'EPSG:31467'}, 400),
    ({'WIDTH': 100_000}, 400),
    ({'BBOX': '0,0,1'}, 400),
    ({'BBOX': '1,0,0,1'}, 400),
    ({'WIDTH': 'ten'}, 400),
    ({'LAYERS': 'std,max'}, 400),
    ({'LAYERS': 'nonexistent'}, 404),
])
def test_a_bad_request_is_refused_not_rendered(served, change, status):
    response = get_map(served, 'EPSG:3857', (0, 0, 1, 1), **change)
    assert response.status_code == status


def test_an_unknown_operation_is_400(served):
    assert served.get('/wms?SERVICE=WMS&REQUEST=GetFeatureInfo').status_code == 400
