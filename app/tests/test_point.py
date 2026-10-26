"""The point mode: what is at a point.

The order is the answer: what lies at the point comes first, nearest
first, and then the areas that contain it -- a point in a city is inside a
country, a municipality and a park at once -- the most specific first.
Everything below checks that ordering, the radii, and that the query
reaches its indexes rather than scanning.
"""

from __future__ import annotations

import math

import pytest

from search import api, point
from search.request import parse

#: In the middle of Vaduz, where there is something to find.
VADUZ = (9.5215, 47.1410)
#: Outside the extract entirely.
NOWHERE = (9.0, 47.0)

pytestmark = pytest.mark.usefixtures('small')


def at(lon=VADUZ[0], lat=VADUZ[1], **kw):
    return api.find(parse({'mode': 'point', 'near': [lon, lat], **kw}))


def objects(body):
    """The results after the address, which comes first whatever its distance."""
    return [f for f in body['results']['features'] if not f['id'].startswith('a')]


def parts(body):
    return [(f['properties']['name'], f['properties']['match_distance']) for f in objects(body)]


# --- configuration (no database) -----------------------------------------

def test_the_radii_come_from_parameters_yaml():
    assert point.radii() == {'point_radius_m': 50.0, 'line_radius_m': 25.0}


def test_one_radius_overrides_both():
    """A caller who widens the search means "look further", not "look
    further for points but not for lines"."""
    params = point.params(*VADUZ, radius=200)
    assert params['point_radius'] == params['line_radius'] == 200


def test_without_an_override_each_part_keeps_its_own():
    params = point.params(*VADUZ)
    assert params['point_radius'] == 50 and params['line_radius'] == 25


@pytest.mark.parametrize('lat', [0.0, 47.14, 54.32, 60.0])
def test_the_prefilter_box_covers_the_radius_in_both_axes(lat):
    """The box only stands in front of an exact ST_DWithin, so it has to be
    a superset of it.

    It was not. One `ST_Expand(g, d)` widened both axes by the same degree
    count, and a degree of longitude is cos(latitude) of a degree of
    latitude -- 25 m north-south but 14.7 m east-west at 54 N. A line 20 m
    due east passed ST_DWithin(25) and was dropped by the box in front of
    it. Nothing failed; the row was simply never seen."""
    params = point.params(9.0, lat)
    metres = params['line_radius']
    # What the box is worth in metres, along each axis, at this latitude.
    east_west = params['line_degrees_lon'] * 111_320.0 * math.cos(math.radians(lat))
    north_south = params['line_degrees_lat'] * 111_320.0
    assert east_west >= metres, f'{east_west:.1f} m east-west covers only {metres} m'
    assert north_south >= metres


def test_the_address_box_covers_the_address_radius():
    params = point.params(*VADUZ)
    east_west = (params['address_degrees_lon'] * 111_320.0
                 * math.cos(math.radians(VADUZ[1])))
    assert east_west >= params['address_radius']


# --- against the data ----------------------------------------------------

def is_area(feature):
    return feature['geometry']['type'] in ('Polygon', 'MultiPolygon')


def test_containing_areas_come_smallest_first():
    body = at()
    areas = [f for f in objects(body) if is_area(f)]
    assert len(areas) >= 2
    # Vaduz (level 8) before Oberland (6) before Liechtenstein (2).
    # From `categories`: a town's area row is filed as the town.
    prefix = 'cat_geography_admin_'
    levels = [int(c['id'].removeprefix(prefix)) for f in areas
              for c in f['properties']['categories'] if c['id'].startswith(prefix)]
    assert len(levels) >= 2
    assert levels == sorted(levels, reverse=True)


def test_everything_near_precedes_the_areas():
    """A click on a bar means the bar; the boundaries it lies in are where
    it is, so they come after it."""
    kinds = [is_area(f) for f in objects(at())]
    assert False in kinds and True in kinds
    assert kinds == sorted(kinds)


def test_nearby_things_come_back_by_distance():
    body = at()
    near = [d for _, d in parts(body) if d and d > 0]
    assert near == sorted(near)


def test_everything_near_is_inside_the_radius():
    body = at()
    assert all(d <= 50.0 for _, d in parts(body) if d)


def test_a_wider_radius_finds_more():
    assert at(radius=200)['count'] > at()['count']


def test_a_point_with_nothing_there_returns_an_empty_collection():
    body = at(*NOWHERE)
    assert body['count'] == 0
    assert body['results'] == {'type': 'FeatureCollection', 'features': []}


def test_categories_narrow_what_is_found():
    """`categories` holds a row's ancestors, so a root id keeps its
    whole subtree -- here the boundaries -- and drops everything else."""
    body = at(categories=['cat_geography'])
    found = body['results']['features']
    assert found and len(found) < at()['count']
    assert all(f['properties']['category'].startswith('cat_geography') for f in found)


def test_the_limit_cuts_the_list_and_total_counts_the_rest():
    full = at()
    body = at(limit=2)
    assert body['count'] == 2
    assert body['total'] == full['total'] == full['count']
    assert body['has_more']
    assert body['results']['features'] == full['results']['features'][:2]


def test_the_page_envelope_is_the_other_modes_one():
    assert list(at()) == ['page', 'limit', 'count', 'total', 'has_more', 'results']


# --- the address ---------------------------------------------------------

def test_the_nearest_address_comes_first_at_address_relevance():
    """No separate `address` beside the results: a client shows one list,
    and the address that names the click heads it."""
    features = at()['results']['features']
    first = features[0]
    assert first['id'].startswith('a')
    properties = first['properties']
    assert properties['address_street'] and properties['address_housenumber']
    assert properties['match_distance'] < 100
    assert properties['match_relevance'] == 100
    assert {f['properties']['match_relevance'] for f in features[1:]} == {99}


def test_the_address_can_be_left_out():
    body = at(address=False)
    assert not any(f['id'].startswith('a') for f in body['results']['features'])
    assert body['total'] == at()['total'] - 1


def test_no_address_nearby_means_none_in_the_list():
    assert at(*NOWHERE)['results']['features'] == []


def test_the_address_object_is_not_listed_again():
    """A POI with its own address came back twice, as the address and
    among the results (a school in Berlin)."""
    body = at(9.4971214, 47.0613768)
    names = [f['properties']['name'] for f in body['results']['features']]
    assert names[0] == 'marvo AG'
    assert names.count('marvo AG') == 1
    assert at(9.4971214, 47.0613768, address=False)['total'] == body['total']


# --- the plan ------------------------------------------------------------

def test_each_part_uses_its_own_index(db, small):
    conn = api._connect()
    try:
        statement = api._statement(point.sql())
        rows = conn.execute(b'explain (analyze, costs off) ' + statement.as_bytes(conn),
                            point.params(*VADUZ)).fetchall()
        plan = '\n'.join(r['QUERY PLAN'] for r in rows)
    finally:
        conn.close()
    assert 'geom_polygon_idx' in plan, plan
    assert 'geom_center_geography_idx' in plan or 'geom_center_idx' in plan, plan
    assert 'Seq Scan' not in plan, plan


def test_the_nearest_address_is_the_nearest_in_metres(db, small):
    """`ORDER BY a.geom <-> pt` measures degrees, and at 54 N a degree of
    longitude is 0.59 of one of latitude -- so an address 40 m north sorted
    ahead of one 30 m east and "nearest" was the wrong house.

    Checked against the data rather than against the SQL text: whatever the
    statement says, the address it returns has to be the one with the
    smallest distance in metres of everything inside the radius."""
    from psycopg import sql

    for lon, lat in (VADUZ, (9.5074, 47.1660), (9.5400, 47.1200)):
        first = at(lon, lat, radius=400)['results']['features'][:1]
        if not first or not first[0]['id'].startswith('a'):
            continue
        params = point.params(lon, lat, radius=400)
        closest = db.execute(sql.SQL(
            'select min(ST_Distance(a.geom::geography,'
            ' ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)) from {} a'
            ' where ST_DWithin(a.geom::geography,'
            ' ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)'
        ).format(sql.Identifier(small, 'osm_search_address')),
            (lon, lat, lon, lat, params['address_radius'])).fetchone()[0]
        assert first[0]['properties']['match_distance'] == pytest.approx(closest, abs=0.1)


def test_the_address_lookup_stays_off_a_sequential_scan(db, small):
    """The metric ordering costs nothing only because the `&&` box gets the
    candidate set down to a handful first. `ST_DWithin` on a cast to
    geography cannot use an index here -- there is no functional GiST on
    `(geom::geography)` -- so removing the box would turn this into a scan
    of every address in the extract."""
    conn = api._connect()
    try:
        statement = api._statement(point.ADDRESS_SQL)
        rows = conn.execute(b'explain (analyze, costs off) ' + statement.as_bytes(conn),
                            point.params(*VADUZ)).fetchall()
        plan = '\n'.join(r['QUERY PLAN'] for r in rows)
    finally:
        conn.close()
    assert 'Seq Scan' not in plan, plan
    assert 'geom_idx' in plan, plan
