"""The search routes.

Thin by design -- a body becomes a `search.request.Request` and the result is
already the response shape -- so what is worth testing is the boundary: that
a bad body is refused the same way it is refused off-HTTP, and that the
response really is the documented contract (DESIGN.md "Shape"), checked as
a schema test since it is a public contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.main import app

#: Every property DESIGN.md "Shape" promises on a feature, in its order --
#: exactly these, on every feature, whichever table found it.
FEATURE_PROPERTIES = (
    'name', 'category', 'category_name', 'categories', 'icon',
    'center', 'places',
    'match_relevance', 'match_score', 'match_rule', 'match_distance',
    'address_street', 'address_housenumber', 'address_postcode', 'address_city',
    'osm_ids', 'osm_tags',
)

#: And on the page itself.
PAGE_FIELDS = {'page', 'limit', 'count', 'total', 'has_more', 'results'}


@pytest.fixture(scope='module')
def served():
    """The app pointed at the imported `li` schema.

    No Map pool: these routes never render a tile, so the lifespan is
    skipped entirely -- `TestClient(app)` without the context manager.
    """
    from conftest import small_schema

    from lib import db as db_module

    schema = small_schema()
    if schema is None:
        pytest.skip("no 'li' import; run tools/manage.py import li")

    original = db_module.active_schema
    db_module.active_schema = lambda area=None: schema
    from search import api
    api.clear_cache()
    try:
        yield TestClient(app)
    finally:
        db_module.active_schema = original
        api.clear_cache()


def post(served, body, path='/search'):
    return served.post(path, json=body)


def features(body):
    return body['results']['features']


# --- the three modes -----------------------------------------------------

def test_name_mode(served):
    body = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 3}).json()
    assert body['total'] > 0
    assert features(body)[0]['properties']['name'] == 'Vaduz'


def test_address_mode(served):
    body = post(served, {'mode': 'address', 'street': 'Landstrasse', 'housenumber': '11',
                         'limit': 3}).json()
    assert features(body)[0]['properties']['address_street'] == 'Landstrasse'


def test_phrase_mode_reports_its_interpretation(served):
    """A phrase search that returns the wrong thing is unexplainable
    without it: the user sees a list and cannot tell how it was read."""
    body = post(served, {'mode': 'phrase', 'text': 'restaurant vaduz', 'limit': 3}).json()
    assert 'category_in_place' in {i['rule'] for i in body['interpretation']}
    assert all(f['properties']['match_rule'] is not None for f in features(body))


def test_the_interpretation_is_absent_outside_phrase_mode(served):
    assert 'interpretation' not in post(served, {'mode': 'name', 'text': 'vaduz'}).json()


# --- the response contract -----------------------------------------------

def test_the_page_carries_every_documented_field(served):
    body = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 2}).json()
    assert set(body) == PAGE_FIELDS
    assert body['results']['type'] == 'FeatureCollection'
    assert set(body['results']) == {'type', 'features'}
    assert body['count'] == len(features(body)) == 2
    assert body['has_more'] is True


@pytest.mark.parametrize('body', [
    {'mode': 'name', 'text': 'vaduz', 'limit': 3},
    {'mode': 'address', 'street': 'Landstrasse', 'housenumber': '11', 'limit': 3},
    {'mode': 'phrase', 'text': 'restaurant vaduz', 'limit': 3},
    {'mode': 'phrase', 'text': 'Landstrasse 11 Vaduz', 'limit': 3},
])
def test_a_feature_carries_exactly_the_documented_properties(served, body):
    found = features(post(served, body).json())
    assert found
    for feature in found:
        assert set(feature) == {'type', 'id', 'properties', 'geometry'}
        assert tuple(feature['properties']) == FEATURE_PROPERTIES
        assert isinstance(feature['properties']['name'], str)


def test_the_geometry_is_the_highlight_and_the_centre_is_separate(served):
    """So a list view can fly to a result without parsing a boundary
    polygon it is not going to draw."""
    feature = features(post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1}).json())[0]
    assert feature['geometry']['type'] in ('Point', 'MultiLineString', 'MultiPolygon')
    assert len(feature['properties']['center']) == 2


def test_category_names_follow_lang(served):
    de = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1, 'lang': 'de'}).json()
    en = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1, 'lang': 'en'}).json()
    assert (features(de)[0]['properties']['categories']
            != features(en)[0]['properties']['categories'])


def test_the_score_is_returned(served):
    """A score computed and never returned is no use to the client.

    Without it a client cannot tell a confident hit from a desperate one,
    and neither can anyone debugging the ranking.
    """
    feature = features(post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1}).json())[0]
    assert isinstance(feature['properties']['match_score'], (int, float))


# --- the body round-trips ------------------------------------------------

def test_a_bbox_narrows_the_result(served):
    wide = post(served, {'mode': 'name', 'categories': ['cat_poi_food_restaurant']}).json()['total']
    narrow = post(served, {'mode': 'name', 'categories': ['cat_poi_food_restaurant'],
                           'bbox': [9.50, 47.13, 9.53, 47.15]}).json()['total']
    assert 0 < narrow < wide


def test_categories_filter(served):
    body = post(served, {'mode': 'name', 'categories': ['cat_poi_food_restaurant'],
                         'limit': 3}).json()
    assert body['total'] > 0
    assert all('cat_poi_food_restaurant' in [c['id'] for c in f['properties']['categories']]
               for f in features(body))


def test_near_and_sort_distance_round_trip(served):
    body = post(served, {'mode': 'name', 'categories': ['cat_poi_food_restaurant'],
                         'near': [9.5215, 47.1410], 'sort': 'distance',
                         'limit': 5}).json()
    distances = [f['properties']['match_distance'] for f in features(body)]
    assert distances == sorted(distances)


def test_paging_round_trips(served):
    first = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 5, 'page': 0}).json()
    second = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 5, 'page': 1}).json()
    assert second['page'] == 1
    assert not {f['id'] for f in features(first)} & {f['id'] for f in features(second)}


# --- refusals ------------------------------------------------------------

def test_a_bad_body_is_422_naming_the_field(served):
    """422, not 400: the body parsed as JSON and was the wrong *content*,
    which is the distinction a client acts on."""
    response = post(served, {'mode': 'fuzzy', 'text': 'x'})
    assert response.status_code == 422
    assert 'mode' in response.json()['detail']


@pytest.mark.parametrize('body,fragment', [
    ({'mode': 'name'}, 'text or categories'),
    ({'mode': 'name', 'text': 'x', 'limit': 5000}, 'between 1 and 100'),
    ({'mode': 'name', 'text': 'x', 'similarity': 0}, 'between 1 and 10'),
    ({'mode': 'name', 'text': 'x', 'page': -1}, 'negative'),
    ({'mode': 'name', 'text': 'x', 'bbox': [9, 54, 10, 95]}, 'lon, lat'),
    ({'mode': 'name', 'text': 'x', 'bbox': [9, 54, 10, 55],
      'area': 'POLYGON((0 0,1 0,1 1,0 0))'}, 'send one'),
    ({'mode': 'address', 'street': 'x'}, 'housenumber is required'),
    ({'mode': 'address', 'text': 'x 1'}, 'not text or categories'),
    ({'mode': 'name', 'text': 'x', 'street': 'y'}, 'only in the address mode'),
])
def test_every_validation_reaches_http_unchanged(served, body, fragment):
    """The same refusals `search/request.py` gives a non-HTTP caller.

    The validation is there rather than in a pydantic model precisely so
    `manage.py`, the profilers and the tests are refused for the same
    reasons; this checks the wiring does not soften any of them.
    """
    response = post(served, body)
    assert response.status_code == 422
    assert fragment in response.json()['detail']


# --- /search/count -------------------------------------------------------

def test_count_agrees_with_the_page_total(served):
    body = {'mode': 'name', 'text': 'vaduz'}
    total = post(served, body, '/search/count').json()['total']
    assert total == post(served, body).json()['total']


# --- /search/fuzzy -------------------------------------------------------

def test_fuzzy_finds_a_misspelled_name_at_the_fuzzy_relevance(served):
    from search import rank

    body = post(served, {'mode': 'name', 'text': 'vadutz', 'limit': 3}, '/search/fuzzy').json()
    assert features(body)[0]['properties']['name'] == 'Vaduz'
    assert {f['properties']['match_relevance'] for f in features(body)} == {
        rank.weights().relevance['name_fuzzy']}


def test_fuzzy_skips_the_exact_name(served):
    """An exact name is not answered at the exact relevance: the route is
    the fuzzy search alone, which is what the devtools box switches to."""
    from search import rank

    body = post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 3}, '/search/fuzzy').json()
    assert features(body)
    assert all(f['properties']['match_relevance'] == rank.weights().relevance['name_fuzzy']
               for f in features(body))


@pytest.mark.parametrize('body', [
    {'mode': 'phrase', 'text': 'vaduz'},
    {'mode': 'name', 'categories': ['cat_geography']},
    # No text once normalised: the plan had no probes, and the empty
    # candidate CTE was a syntax error, a 500.
    {'mode': 'name', 'text': '!!!'},
])
def test_fuzzy_refuses_what_it_cannot_take(served, body):
    for path in ('/search/fuzzy', '/search/fuzzy/count'):
        assert post(served, body, path).status_code == 422


def test_fuzzy_count_agrees_with_the_page_total(served):
    body = {'mode': 'name', 'text': 'vadutz'}
    total = post(served, body, '/search/fuzzy/count').json()['total']
    assert total and total == post(served, body, '/search/fuzzy').json()['total']


# --- the point mode ---------------------------------------------------

def point(served, **over):
    return post(served, {'mode': 'point', 'near': [9.5215, 47.1410], **over}).json()


def test_point_returns_what_is_near_by_distance_then_areas(served):
    body = point(served)
    assert body['count'] > 0
    assert set(body) == PAGE_FIELDS
    found = features(body)
    areas = [f['geometry']['type'] in ('Polygon', 'MultiPolygon') for f in found]
    assert areas == sorted(areas)
    near = [f['properties']['match_distance'] for f, area in zip(found, areas, strict=True)
            if not area and not f['id'].startswith('a')]
    assert near and near == sorted(near)


def test_point_starts_with_the_nearest_address(served):
    address = features(point(served))[0]
    assert address['properties']['address_street']
    assert tuple(address['properties']) == FEATURE_PROPERTIES
    assert address['properties']['icon']
    assert address['properties']['match_relevance'] == 100


def test_point_can_leave_the_address_out(served):
    assert not any(f['id'].startswith('a') for f in features(point(served, address=False)))


def test_a_wider_radius_finds_more(served):
    assert point(served, radius=200)['count'] > point(served)['count']


def test_point_count_agrees_with_the_page_total(served):
    body = {'mode': 'point', 'near': [9.5215, 47.1410]}
    assert (post(served, body, '/search/count').json()['total']
            == post(served, body).json()['total'])


@pytest.mark.parametrize('over', [
    {'near': [200, 47]}, {'near': [9, 100]}, {'radius': 0}, {'radius': 99999}, {'near': None},
])
def test_an_out_of_range_point_or_radius_is_422(served, over):
    body = {'mode': 'point', 'near': [9.5215, 47.1410], **over}
    assert post(served, body).status_code == 422


def test_there_is_no_get_route_for_a_point(served):
    assert served.get('/search/here', params={'lon': 9.5215, 'lat': 47.1410}).status_code \
        in (404, 405)


# --- icons -------------------------------------------------------------------

def test_a_result_carries_its_categorys_icon_url(served):
    feature = features(post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1}).json())[0]
    properties = feature['properties']
    assert properties['icon'] == f"http://testserver/icons/{properties['category']}.svg"


def test_the_icon_url_is_not_written_into_the_cached_body(served):
    """The search module caches bodies; the URL depends on the caller's host."""
    from search import api
    from search.request import parse

    post(served, {'mode': 'name', 'text': 'vaduz', 'limit': 1})
    cached = api.find(parse({'mode': 'name', 'text': 'vaduz', 'limit': 1}))
    assert features(cached)[0]['properties']['icon'] is None
