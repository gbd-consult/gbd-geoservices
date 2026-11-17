"""The reverse search: the address nearest a coordinate, in any served CRS.

What it can get wrong silently: an x/y in UTM read as lon/lat (or the axes
swapped) finds nothing or a wrong house, and "nearest" in degrees rather
than metres picks the wrong one. Each test below pins one of those.
"""

from __future__ import annotations

import pytest

from search import api, point
from search.request import RequestError, parse, parse_reverse

#: In the middle of Vaduz, where there are addresses.
VADUZ = (9.5215, 47.1410)
#: Outside the extract entirely.
NOWHERE = (9.0, 47.0)


def reverse(x, y, **kw):
    return api.reverse(parse_reverse({'x': x, 'y': y, **kw}))


def features(body):
    return body['results']['features']


# --- validation (no database) --------------------------------------------

def test_the_maximum_distance_comes_from_parameters_yaml():
    assert point.radii()['reverse_max_m'] == 500.0


def test_wgs84_is_the_default_and_x_is_lon():
    req = parse_reverse({'x': VADUZ[0], 'y': VADUZ[1]})
    assert (req.mode, req.near, req.crs) == ('reverse', VADUZ, 'EPSG:4326')


def test_the_crs_is_normalised():
    assert parse_reverse({'x': 1, 'y': 2, 'crs': ' epsg:25832 '}).crs == 'EPSG:25832'


@pytest.mark.parametrize('body, fragment', [
    ({'y': 47}, 'x is required'),
    ({'x': 9}, 'y is required'),
    ({'x': 'nine', 'y': 47}, 'x must be a number'),
    ({'x': True, 'y': 47}, 'x must be a number'),
    ({'x': 'nan', 'y': 47}, 'finite'),
    ({'x': 9, 'y': 47, 'crs': 'EPSG:31467'}, 'crs must be one of'),
    ({'x': 9, 'y': 100}, 'out of range'),
    # A UTM pair sent without its CRS: refused, not searched as lon/lat.
    ({'x': 574000, 'y': 6020000}, 'out of range'),
    ({'x': 9, 'y': 47, 'text': 'kiel'}, 'not in the reverse search'),
    ({'x': 9, 'y': 47, 'mode': 'point'}, 'not in the reverse search'),
])
def test_a_bad_body_is_refused_naming_the_field(body, fragment):
    with pytest.raises(RequestError, match=fragment):
        parse_reverse(body)


def test_search_does_not_take_reverse_as_a_mode():
    with pytest.raises(RequestError, match='mode must be one of'):
        parse({'mode': 'reverse', 'near': list(VADUZ)})


# --- against li ------------------------------------------------------------

@pytest.mark.usefixtures('small')
def test_it_returns_one_address_within_the_maximum():
    found = features(reverse(*VADUZ))
    assert len(found) == 1
    address = found[0]
    assert address['id'].startswith('a')
    assert address['properties']['address_street']
    assert address['properties']['match_relevance'] == 100
    assert address['properties']['match_distance'] <= 500


@pytest.mark.usefixtures('small')
def test_nothing_within_the_maximum_is_an_empty_page():
    body = reverse(*NOWHERE)
    assert body['count'] == body['total'] == 0
    assert features(body) == []


def test_it_is_the_nearest_address_in_metres(small, db):
    """Not the nearest in degrees, which at 47 N favours north-south."""
    address = features(reverse(*VADUZ))[0]
    nearest = db.execute(
        f'SELECT id FROM "{small}".osm_search_address'
        ' ORDER BY ST_Distance(geom::geography,'
        ' ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography), id LIMIT 1', VADUZ).fetchone()[0]
    assert address['id'] == f'a{nearest}'


@pytest.mark.parametrize('crs', ['EPSG:3857', 'EPSG:25832', 'EPSG:25833'])
def test_the_same_point_in_another_crs_finds_the_same_address(small, db, crs):
    """A swapped axis or a missing transform finds nothing or another house."""
    x, y = db.execute(
        'SELECT ST_X(g), ST_Y(g) FROM ST_Transform('
        'ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) g',
        (*VADUZ, int(crs.split(':')[1]))).fetchone()
    expected = features(reverse(*VADUZ))[0]
    found = features(reverse(x, y, crs=crs))
    assert [f['id'] for f in found] == [expected['id']]
    assert found[0]['properties']['match_distance'] == pytest.approx(
        expected['properties']['match_distance'], abs=0.01)


@pytest.mark.usefixtures('small')
def test_a_projected_point_off_the_globe_is_refused():
    """PROJ answers Infinity for UTM far off its zone; that is the client's
    mistake (a 422), not a query to run. (EPSG:3857 wraps instead, and finds
    nothing.)"""
    with pytest.raises(RequestError, match='out of range'):
        reverse(1e9, 1e9, crs='EPSG:25832')
