"""The ranking engine."""

from __future__ import annotations

import re

import pytest

from search import rank


@pytest.fixture(scope='module')
def w() -> rank.Weights:
    return rank.weights()


def test_the_name_channels_still_sum_to_one(w):
    # Not arithmetic that has to hold, but the three channels were chosen
    # as a division of one unit of confidence; a change would be a
    # redesign and should not happen by editing one number.
    assert w.similarity + w.word_similarity + w.phonetic == pytest.approx(1.0)


def test_the_default_lands_on_pg_trgm_s_own_defaults(w):
    assert rank.trgm_thresholds(4, w) == (0.30, 0.60)


def test_similarity_is_clamped_not_rejected(w):
    # The request model already bounds it; this is the second line, for a
    # rule query the phrase mode builds without going through parse().
    assert rank.trgm_thresholds(-5, w) == rank.trgm_thresholds(1, w)
    assert rank.trgm_thresholds(99, w) == rank.trgm_thresholds(10, w)


# --- the SQL the module emits --------------------------------------------

#: `%` in a psycopg query is a placeholder introducer, so pg_trgm's `%` and
#: `<%` operators have to be doubled. A single one raises
#: `ProgrammingError: incomplete placeholder` at execute time -- loud, but
#: only on the code path that runs it, which for a rarely-taken probe could
#: be a long time.
_PLACEHOLDER = re.compile(r'%\(\w+\)s')


def percent_is_escaped(sql: str) -> bool:
    without_params = _PLACEHOLDER.sub('', sql)
    return '%' not in without_params.replace('%%', '')


def test_the_percent_check_catches_what_it_is_for():
    assert not percent_is_escaped('a % %(q)s')
    assert percent_is_escaped('a %% %(q)s')
    assert percent_is_escaped('a <%% %(q)s')


@pytest.mark.parametrize('sql', [
    rank.name_score(has_phonetic=True, spatial=True),
    rank.name_score(has_phonetic=False, spatial=False),
    rank.spatial_clause(True, within=True),
    rank.distance_expr(),
    rank.VIEW,
])
def test_every_emitted_expression_escapes_its_percents(sql):
    assert percent_is_escaped(sql)


def test_no_weight_is_written_into_the_sql_as_a_literal(w):
    """A weight interpolated as `0.40 * similarity(...)`.

    parameters.yaml and the running query could then disagree with nothing
    to say so, and every `similarity` setting got its own query text and so
    its own plan cache entry.
    """
    sql = rank.name_score(has_phonetic=True, spatial=True)
    for value in (w.similarity, w.word_similarity, w.phonetic,
                  w.exact_bonus, w.prefix_bonus):
        assert f'{value}' not in sql
    assert '%(w_similarity)s' in sql and '%(w_phonetic)s' in sql


def test_the_weight_params_cover_every_placeholder_in_the_scores(w):
    names = set(rank.Weights.params(w))
    sql = rank.name_score(has_phonetic=True, spatial=True)
    for placeholder in set(_PLACEHOLDER.findall(sql)):
        key = placeholder[2:-2]
        if key.startswith('w_'):
            assert key in names, key


# --- expression shapes ---------------------------------------------------

def test_a_channel_with_nothing_to_compare_contributes_zero():
    # An unpronounceable query has no phonetic codes; the term has to
    # disappear rather than multiply a weight by NULL.
    assert rank.phonetic_term('o.phon_name', '%(p)s', False) == '0.0'
    assert 'unnest' in rank.phonetic_term('o.phon_name', '%(p)s', True)


def test_the_spatial_clause_tests_each_geometry_column_separately():
    """One OR branch per column, not a COALESCE.

    The coalesce would be opaque to all three GiST indexes and force a
    sequential scan; the OR lets the planner BitmapOr them.
    """
    clause = rank.spatial_clause(True, within=True)
    for column in ('geom_point', 'geom_line', 'geom_polygon'):
        assert f'o.{column} && ' in clause
    assert 'COALESCE' not in clause
    assert clause.count('ST_Within') == 3


def test_within_false_means_intersects():
    assert 'ST_Intersects' in rank.spatial_clause(True, within=False)
    assert 'ST_Within' not in rank.spatial_clause(True, within=False)


def test_no_spatial_restriction_emits_nothing():
    assert rank.spatial_clause(False, within=True) == ''
    assert rank.area_params(None, None) == {}


def test_the_view_is_a_constant_to_the_planner():
    """Read from a CTE, the view was opaque to the planner, taken for one
    row, and a Germany-wide area was scanned through the GiST indexes ahead
    of the name index: 94 s for "berlin" on de, 12 ms without it."""
    for sql in (rank.spatial_clause(True, within=False), rank.inside_view_term(True)):
        assert 'FROM area' not in sql and rank.VIEW in sql
    assert rank.area_params((9, 54, 10, 55), None) == {
        'area_wkt': 'POLYGON((9 54,10 54,10 55,9 55,9 54))'}


def test_distance_goes_through_geography():
    """`<->` on a 4326 geometry returns degrees.

    At 54 N a degree of longitude is 0.59 of one of latitude, so the
    ordering is anisotropically wrong rather than merely mis-scaled. The
    importer built a functional GiST on (geom_center::geography) for this.
    """
    expr = rank.distance_expr()
    assert '::geography' in expr and expr.count('::geography') == 2
    assert 'ST_Distance' in expr


def test_the_inside_view_bonus_only_exists_with_a_view():
    assert rank.inside_view_term(False) == '0.0'
    assert '%(w_inside)s' in rank.inside_view_term(True)


# --- ordering ------------------------------------------------------------

def test_relevance_is_the_default_and_the_fallback():
    assert rank.order_by(None, has_distance=False) == rank.order_by('score',
                                                                    has_distance=False)
    assert rank.order_by('sideways', has_distance=False).startswith('score DESC')


def test_distance_sort_falls_back_without_a_point():
    """Ordering by a column that is not in the select list is an error.

    Without `near` or a bbox there is nothing to measure from, so the
    request asked for something it did not supply the input for.
    """
    assert rank.order_by('distance', has_distance=False).startswith('score DESC')
    assert rank.order_by('distance', has_distance=True).startswith('distance ASC')


def test_every_order_ends_in_a_unique_column():
    # Without it, two rows scoring equally can swap between pages and a
    # user paging through sees one twice and another never.
    for sort in ('score', 'name', 'address', 'distance'):
        assert rank.order_by(sort, has_distance=True).endswith('id ASC')


def test_an_object_order_names_only_object_columns():
    """These order the `scored` CTE, where nothing else is in scope.

    `address` sorted on `number` -- the integer part of a house number,
    which is a column of `osm_search_address` and not of
    `osm_search_object` -- so every name query asking for `sort=address`
    failed with `column "number" does not exist`.
    """
    available = {name.split('.', 1)[1] for name in rank.ORDER_COLUMNS}
    available |= {'score', 'distance'}
    for sort in ('score', 'name', 'address', 'distance'):
        for term in rank.order_by(sort, has_distance=True).split(','):
            column = term.strip().split()[0]
            assert column in available, f'{sort}: {column}'


def test_the_numeric_house_number_order_lives_where_the_column_does():
    # So a street comes back 1, 2, 2a, 3 rather than 1, 10, 11, 2 -- but
    # only in the address mode, which reads the table that has the column.
    from search import address
    order = address._SORTS['address']
    assert order.index('number ASC') < order.index('number_part ASC')


# --- the response cache --------------------------------------------------

def test_the_cache_returns_what_it_stored():
    cache = rank.ResultCache()
    cache.set('k', {'a': 1}, 60, 8)
    assert cache.get('k') == {'a': 1}


def test_an_expired_entry_is_gone():
    cache = rank.ResultCache()
    cache.set('k', 1, 60, 8)
    cache._entries['k'] = (0.0, 1)            # already expired
    assert cache.get('k') is None
    assert len(cache) == 0


def test_the_oldest_entry_is_evicted_first():
    cache = rank.ResultCache()
    for i in range(4):
        cache.set(str(i), i, 60, 3)
    assert cache.get('0') is None and cache.get('3') == 3


def test_a_read_makes_an_entry_the_newest():
    cache = rank.ResultCache()
    for i in range(3):
        cache.set(str(i), i, 60, 3)
    cache.get('0')
    cache.set('3', 3, 60, 3)
    assert cache.get('0') == 0 and cache.get('1') is None


def test_caching_can_be_turned_off_by_either_bound():
    cache = rank.ResultCache()
    cache.set('k', 1, 0, 8)
    cache.set('j', 1, 60, 0)
    assert cache.get('k') is None and cache.get('j') is None
