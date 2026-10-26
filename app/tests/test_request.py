"""The search request model.

Validation lives here rather than in the query builder because a bad value
that reaches SQL surfaces as a database error the caller cannot act on.
Every check below exists because the failure it prevents is silent or
misleading, not because the field could be wrong in principle.
"""

from __future__ import annotations

import pytest

from search.request import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Request,
    RequestError,
    parse,
)


def body(**over):
    return {'mode': 'name', 'text': 'kiel', **over}


# --- mode and query ------------------------------------------------------

def test_the_mode_is_named_not_inferred():
    # Inferring it from which of name/address was filled would make
    # "name wins when both are given" a rule the caller had to know.
    assert parse(body()).mode == 'name'
    with pytest.raises(RequestError, match='mode must be one of'):
        parse(body(mode='fuzzy'))
    with pytest.raises(RequestError, match='mode is required'):
        parse({'text': 'kiel'})


def test_a_request_with_neither_q_nor_categories_is_refused():
    # It is a full-table scan that ranks nothing.
    with pytest.raises(RequestError, match='text or categories'):
        parse({'mode': 'name'})


def test_categories_alone_is_the_category_browse():
    req = parse({'mode': 'name', 'categories': ['amenity_restaurant']})
    assert req.text == '' and req.categories == ('amenity_restaurant',)


def test_a_single_category_may_be_a_string():
    assert parse(body(categories='water')).categories == ('water',)


def test_an_empty_category_id_is_refused():
    with pytest.raises(RequestError, match='non-empty ids'):
        parse(body(categories=['amenity', '  ']))


# --- the address fields --------------------------------------------------

def address(**over):
    return {'mode': 'address', 'street': 'Hauptstraße', 'housenumber': '5', **over}


def test_the_address_mode_takes_its_parts_as_fields():
    req = parse(address(postcode='24105', city='Kiel'))
    assert (req.street, req.housenumber, req.postcode, req.city) == \
        ('Hauptstraße', '5', '24105', 'Kiel')


@pytest.mark.parametrize('missing', ['street', 'housenumber'])
def test_street_and_housenumber_are_required(missing):
    body = address()
    del body[missing]
    with pytest.raises(RequestError, match=f'{missing} is required'):
        parse(body)


def test_a_housenumber_that_is_no_number_is_refused():
    with pytest.raises(RequestError, match='housenumber must be a number'):
        parse(address(housenumber='abc'))


def test_a_housenumber_and_postcode_may_be_numbers():
    # What a numeric input field sends.
    req = parse(address(housenumber=5, postcode=24105))
    assert (req.housenumber, req.postcode) == ('5', '24105')


def test_free_text_is_not_an_address():
    """Parsing free text into an address is the phrase mode's; here the
    parts are fields, so a `q` would be silently ignored."""
    with pytest.raises(RequestError, match='not text or categories'):
        parse(address(text='Hauptstraße 5 Kiel'))
    with pytest.raises(RequestError, match='not text or categories'):
        parse(address(categories=['cat_poi']))


def test_the_address_fields_are_refused_outside_the_address_mode():
    with pytest.raises(RequestError, match='city: only in the address mode'):
        parse(body(city='Kiel'))


# --- bbox and area -------------------------------------------------------

def test_bbox_and_area_are_alternatives():
    """Which one applied would be invisible in the result."""
    with pytest.raises(RequestError, match='send one'):
        parse(body(bbox=[9, 54, 10, 55], area='POLYGON((0 0,1 0,1 1,0 0))'))


def test_a_bbox_corner_order_is_normalised():
    # Some clients send top-left first; the box means the same either way.
    assert parse(body(bbox=[10, 55, 9, 54])).bbox == (9.0, 54.0, 10.0, 55.0)


def test_a_bbox_may_be_a_comma_string():
    assert parse(body(bbox='9,54,10,55')).bbox == (9.0, 54.0, 10.0, 55.0)


@pytest.mark.parametrize('bad', [[9, 54, 10], [9, 54, 10, 'x'], 'nonsense'])
def test_a_malformed_bbox_is_refused(bad):
    with pytest.raises(RequestError):
        parse(body(bbox=bad))


def test_a_degenerate_bbox_is_refused():
    with pytest.raises(RequestError, match='zero width'):
        parse(body(bbox=[9, 54, 9, 55]))


def test_coordinates_out_of_range_are_refused():
    # The message names the axis order because that is the usual cause --
    # though only a swap that lands outside the range is detectable at all,
    # and a German bbox read as lat,lon (54, 9) is not one of them.
    with pytest.raises(RequestError, match='lon, lat'):
        parse(body(bbox=[9, 54, 10, 95]))
    with pytest.raises(RequestError, match='lon, lat'):
        parse(body(near=[181, 54]))


# --- near and the point --------------------------------------------------

def test_the_point_defaults_to_the_bbox_centre():
    # So sort=distance works without the caller sending `near` too.
    assert parse(body(bbox=[9, 54, 11, 56])).point == (10.0, 55.0)


def test_near_wins_over_the_bbox_centre():
    assert parse(body(bbox=[9, 54, 11, 56], near=[9.5, 54.2])).point == (9.5, 54.2)


def test_without_either_there_is_no_point():
    assert parse(body()).point is None


# --- limits --------------------------------------------------------------

def test_limit_defaults_and_caps():
    assert parse(body()).limit == DEFAULT_LIMIT
    assert parse(body(limit=MAX_LIMIT)).limit == MAX_LIMIT


def test_a_limit_over_the_cap_is_an_error_not_a_clamp():
    """`limit: 5000` means the caller expects 5000 rows.

    Quietly returning 100 looks to them like the data ran out.
    """
    with pytest.raises(RequestError, match='between 1 and 100'):
        parse(body(limit=5000))


def test_similarity_is_bounded():
    assert parse(body()).similarity == 7
    assert parse(body(similarity=10)).similarity == 10
    with pytest.raises(RequestError, match='between 1 and 10'):
        parse(body(similarity=0))


def test_relevance_is_a_floor_from_0_to_100():
    assert parse(body()).relevance == 0
    assert parse(body(relevance=60)).relevance == 60
    with pytest.raises(RequestError, match='between 0 and 100'):
        parse(body(relevance=101))


def test_a_negative_page_is_refused():
    with pytest.raises(RequestError, match='must not be negative'):
        parse(body(page=-1))


def test_the_offset_follows_page_and_limit():
    assert parse(body(page=3, limit=20)).offset == 60


def test_an_unknown_sort_falls_back_rather_than_raising():
    # sort is a display preference; a typo should not be a 422.
    assert parse(body(sort='sideways')).sort == 'score'
    assert parse(body(sort='distance')).sort == 'distance'


# --- the point mode ----------------------------------------------------

def point(**over):
    return {'mode': 'point', 'near': [9.5, 47.1], **over}


def test_point_takes_a_point_and_optionally_a_radius_and_categories():
    req = parse(point(radius=40, categories=['cat_poi'], address=False, limit=10))
    assert (req.near, req.radius, req.categories, req.with_address, req.limit) == \
        ((9.5, 47.1), 40.0, ('cat_poi',), False, 10)


def test_point_needs_neither_q_nor_categories():
    req = parse(point())
    assert req.text == '' and req.categories == () and req.radius is None and req.with_address


def test_point_requires_the_point():
    with pytest.raises(RequestError, match='near is required'):
        parse({'mode': 'point'})


@pytest.mark.parametrize('field, value', [
    ('text', 'kiel'), ('bbox', [9, 47, 10, 48]), ('area', 'POLYGON((0 0,1 0,1 1,0 0))'),
    ('within', True), ('sort', 'name'), ('similarity', 5), ('relevance', 10), ('page', 1),
    ('street', 'x'),
])
def test_point_refuses_what_a_point_has_no_use_for(field, value):
    """Accepted and ignored, a `page: 1` would return page 0 again and a
    `bbox` would look like a filter that found nothing outside it."""
    with pytest.raises(RequestError, match=f'{field}: not in the point mode'):
        parse(point(**{field: value}))


@pytest.mark.parametrize('radius', [0, -5, 10_001, 'far', True])
def test_an_out_of_range_radius_is_refused(radius):
    with pytest.raises(RequestError, match='radius must'):
        parse(point(radius=radius))


@pytest.mark.parametrize('field, value', [('radius', 40), ('address', False)])
def test_the_point_fields_are_refused_elsewhere(field, value):
    with pytest.raises(RequestError, match=f'{field}: only in the point mode'):
        parse(body(**{field: value}))


# --- the cache key -------------------------------------------------------

def test_the_cache_key_covers_every_field_that_changes_the_result():
    """A key on a subset serves the wrong answer the moment a field starts
    being used, and that looks like a ranking bug rather than a cache one."""
    base = parse(body(bbox=[9, 54, 10, 55]))
    for field, value in [
        ('mode', 'phrase'), ('text', 'other'), ('categories', ('water',)),
        ('bbox', (8.0, 53.0, 9.0, 54.0)), ('within', True), ('near', (9.0, 54.0)),
        ('sort', 'name'), ('similarity', 3), ('page', 1), ('limit', 10), ('lang', 'en'),
        ('relevance', 60), ('street', 'x'), ('housenumber', '1'), ('postcode', '24105'),
        ('city', 'Kiel'), ('radius', 100.0), ('with_address', False),
    ]:
        other = base.for_rule(**{field: value})
        assert other.cache_key('find') != base.cache_key('find'), field


def test_the_prefix_separates_find_from_count():
    req = parse(body())
    assert req.cache_key('find') != req.cache_key('count')


def test_a_value_cannot_spell_another_key():
    # The separator is \x1f, which no query string carries.
    a = Request(mode='name', text='a', lang='b')
    b = Request(mode='name', text='a\x1fb')
    assert a.cache_key('find') != b.cache_key('find')
