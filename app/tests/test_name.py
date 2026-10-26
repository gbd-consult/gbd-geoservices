"""The name mode, against the imported `li` schema.

The name mode is the normalised name, exactly; only when that finds
nothing does it fall back to the fuzzy name search, `name.fuzzy_plan`,
which the phrase LIKE rules run too. Tested here as well:
which index a probe uses, whether distance is metric, the hand-worked
score -- none of it visible in a string.
"""

from __future__ import annotations

import pytest

from search import api, name, rank
from search.request import parse

pytestmark = pytest.mark.usefixtures('small')


def find(**body):
    return api.find(parse({'mode': 'name', **body}))


def names(page):
    return [f['properties']['name'] for f in page['results']['features']]


def fuzzy(q, **body):
    """Rows of the fuzzy name search, as a phrase LIKE rule runs it."""
    req = parse({'mode': 'name', 'text': q, **body})
    plan = name.fuzzy_plan(req)
    w = rank.weights()
    conn = api._connect()
    try:
        rank.set_thresholds(conn, *rank.trgm_thresholds(req.similarity, w))
        return conn.execute(api._statement(rank.build_sql(plan, req, count_only=False)),
                            {**rank.base_params(plan, req, w), 'min_score': w.min_score}).fetchall()
    finally:
        conn.close()


# --- the plan ------------------------------------------------------------

def test_the_name_mode_is_one_equality_probe():
    plan = name.plan(parse({'mode': 'name', 'text': 'Holtenauer Str.'}))
    assert plan.probes == (name.EXACT_PROBE,)
    assert plan.params['q_name'] == 'holtenauer strasse'
    assert 'similarity' not in plan.score and 'phon' not in plan.score


def test_a_category_narrows_the_equality_probe():
    plan = name.plan(parse({'mode': 'name', 'text': 'adler', 'categories': ['cat_poi_food_restaurant']}))
    assert plan.probes == (f'{name.EXACT_PROBE} AND {name.CATEGORY_PROBE}',)


def test_a_narrowed_text_query_probes_every_channel():
    """One probe per channel, so a row the letter channel misses entirely
    can still be found by another."""
    plan = name.fuzzy_plan(parse({'mode': 'name', 'text': 'meyer'}), narrowed=True)
    assert any('search_name %%' in p for p in plan.probes)          # letters
    assert any('<%% o.search_name' in p for p in plan.probes)       # fragment
    assert any('phon_name = ANY' in p for p in plan.probes)         # exact code
    assert any('phon_name %%' in p for p in plan.probes)            # near code


def test_an_unnarrowed_query_has_no_near_code_probe():
    """Codes are digit strings, whose trigrams hardly discriminate: over the
    whole of `de` `phon_name % code` returned 90 k to 844 k index
    candidates, each a heap page to recheck. Only a probe something else
    narrows -- a place, a category -- can afford it."""
    plan = name.fuzzy_plan(parse({'mode': 'name', 'text': 'meyer'}))
    assert any('phon_name = ANY' in p for p in plan.probes)
    assert not any('phon_name %%' in p for p in plan.probes)
    plan = name.fuzzy_plan(parse({'mode': 'name', 'text': 'meyer',
                                  'categories': ['cat_poi_food_restaurant']}))
    assert any('phon_name %%' in p for p in plan.probes)


def test_the_text_probes_never_touch_search_text():
    """search_text carries each row's city.

    Probing it for a bare city name matches every row in that city --
    measured at 440 ms of a 550 ms query. It is still *scored*:
    ranking wants the city context, finding candidates does not.
    """
    plan = name.fuzzy_plan(parse({'mode': 'name', 'text': 'vaduz'}))
    assert not any('search_text' in p for p in plan.probes)
    assert 'search_text' in plan.score


def test_a_category_narrows_every_probe_rather_than_adding_a_branch():
    """As a branch it would *widen* the candidate set.

    A branch matching `categories && ARRAY['cat_poi']` alone is most of
    the table; ANDed into the text probes it is a BitmapAnd of two indexes.
    """
    plan = name.fuzzy_plan(parse({'mode': 'name', 'text': 'adler',
                                  'categories': ['cat_poi_food_restaurant']}))
    assert all(name.CATEGORY_PROBE in p for p in plan.probes)


def test_categories_without_text_are_the_browse():
    plan = name.plan(parse({'mode': 'name', 'categories': ['cat_poi_food_restaurant']}))
    assert plan.probes == (name.CATEGORY_PROBE,)
    # Nothing to compare text against, so the three text channels would all
    # score 0 and every row would fall below min_score.
    assert 'similarity' not in plan.score


# --- finding things ------------------------------------------------------

def test_an_exact_name_comes_first():
    assert names(find(text='Vaduz'))[0] == 'Vaduz'


def test_the_town_outranks_everything_else_of_the_same_name():
    # Importance is what separates rows the text channels score equally.
    top = find(text='Vaduz')['results']['features'][0]
    assert top['properties']['category'] == 'cat_geography_places_town'


def test_only_the_exact_name_comes_back():
    page = find(text='Vaduz', limit=100)
    assert page.get('fallback') is None
    assert {n.lower() for n in names(page)} == {'vaduz'}
    assert all(f['properties']['match_relevance'] == 99 for f in page['results']['features'])


def test_spelling_is_normalised_before_the_comparison():
    assert names(find(text='VADUZ')) == names(find(text='Vaduz'))
    assert 'Landstrasse' in names(find(text='Landstr.'))


def test_a_typo_or_a_fragment_falls_back_to_the_fuzzy_search():
    for q in ('Vaduzz', 'Vadu'):
        page = find(text=q, limit=100)
        assert 'Vaduz' in names(page), q
        assert {f['properties']['match_relevance'] for f in page['results']['features']} == {20}, q
        assert api.count(parse({'mode': 'name', 'text': q})) == page['total'], q


def test_nothing_like_any_name_finds_nothing():
    page = find(text='qqzzxx')
    assert page['total'] == 0 and 'interpretation' not in page
    assert api.count(parse({'mode': 'name', 'text': 'qqzzxx'})) == 0


def test_a_relevance_floor_above_the_exact_name_s_drops_it():
    assert find(text='Vaduz', relevance=100)['total'] == 0
    assert api.count(parse({'mode': 'name', 'text': 'Vaduz', 'relevance': 100})) == 0


def test_a_relevance_floor_above_the_fallback_s_skips_it():
    assert find(text='Vaduzz', relevance=21)['total'] == 0
    assert api.count(parse({'mode': 'name', 'text': 'Vaduzz', 'relevance': 21})) == 0


@pytest.mark.parametrize('q, similarity, relaxed', [
    ('landstrase', 4, False),
    # Found by the relaxed pass only, so the pages after the first have to
    # choose the relaxed thresholds again rather than run strict and be empty.
    ('Flsrse', 10, True),
])
def test_the_fallback_pages_like_the_exact_name(q, similarity, relaxed):
    """Page 3 of a misspelling is still the fuzzy search, not an empty
    exact one; and its total is what paging through returns."""
    body = {'mode': 'name', 'text': q, 'similarity': similarity}
    conn = api._connect()
    try:
        strict = api._fuzzy_count(conn, parse(body), rank.weights(), relax=False)
    finally:
        conn.close()
    assert (strict == 0) == relaxed
    total = api.count(parse(body))
    seen = []
    for page_number in range(50):
        page = find(text=q, similarity=similarity, limit=2, page=page_number)
        seen += [f['id'] for f in page['results']['features']]
        if not page['has_more']:
            break
    assert total == len(seen) == len(set(seen)) > 2


# --- filters -------------------------------------------------------------

def test_a_bbox_narrows_the_result():
    everywhere = find(categories=['cat_poi_food_restaurant'])['total']
    inside = find(categories=['cat_poi_food_restaurant'], bbox=[9.50, 47.13, 9.53, 47.15])['total']
    assert 0 < inside < everywhere


def test_a_parent_category_finds_its_leaves():
    """`categories` stores every ancestor, so a parent is the same indexed
    containment test as a leaf -- no recursion, no path prefixes."""
    leaves = find(categories=['cat_poi_food_restaurant'])['total']
    parent = find(categories=['cat_poi_food'])['total']
    assert leaves > 0 and parent > leaves


def test_a_street_ranks_above_the_bus_stop_named_after_it():
    top = find(text='Landstrasse', limit=1)['results']['features'][0]['properties']
    assert top['category'].startswith('cat_built_roads_')


def test_equal_names_come_nearest_first():
    """Exact names tie by the dozen; the nearest of equals is the one meant."""
    page = find(text='Landstrasse', near=[9.52, 47.14], limit=50)
    rows = [f['properties'] for f in page['results']['features']]
    top = [r['match_distance'] for r in rows if r['match_score'] == rows[0]['match_score']]
    assert len(top) > 1 and top == sorted(top)


def test_the_key_fallback_holds_only_the_leftovers():
    """`amenity=*` gives the amenities iD has no preset for their category.
    Counted for every amenity, filtering by it would return all of them."""
    other = find(categories=['cat_poi_other_amenity'])['total']
    everything = find(categories=['cat_poi'])['total']
    assert other < everything


def test_an_unknown_category_finds_nothing():
    assert find(categories=['no_such_category'])['total'] == 0


# --- ordering ------------------------------------------------------------

def test_distance_is_metres_and_ascending():
    page = find(categories=['cat_poi_food_restaurant'], near=[9.5215, 47.1410],
                sort='distance', limit=5)
    distances = [f['properties']['match_distance'] for f in page['results']['features']]
    assert distances == sorted(distances)
    assert distances[0] < 500          # metres, not degrees


def test_distance_ordering_is_metric_not_angular(db, small):
    """The regression test for the `geography` fix.

    `<->` on a 4326 geometry returns degrees, and a degree of longitude is
    cos(lat) of one of latitude -- 0.68 at 47 N, 0.59 at 54 N. Two points
    the same number of metres away in different directions would come back
    in the wrong order, and the result would look merely odd rather than
    wrong.
    """
    row = db.execute("""
        select ST_Distance(
                   ST_SetSRID(ST_MakePoint(9.52, 47.14), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(9.52, 47.15), 4326)::geography) as north,
               ST_Distance(
                   ST_SetSRID(ST_MakePoint(9.52, 47.14), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(9.5347, 47.14), 4326)::geography) as east,
               ST_SetSRID(ST_MakePoint(9.52, 47.15), 4326) <->
                   ST_SetSRID(ST_MakePoint(9.52, 47.14), 4326) as north_deg,
               ST_SetSRID(ST_MakePoint(9.5347, 47.14), 4326) <->
                   ST_SetSRID(ST_MakePoint(9.52, 47.14), 4326) as east_deg
    """).fetchone()
    north, east, north_deg, east_deg = row
    # Same distance in metres, near enough...
    assert north == pytest.approx(east, rel=0.02)
    # ...but 47% further in degrees, because a degree of longitude is
    # shorter there, so covering the same ground takes more of them. An
    # ORDER BY on the degree distance puts the eastern one last.
    assert east_deg > north_deg * 1.4


def test_sorting_by_name_is_alphabetical():
    # Case-insensitively: Postgres sorts under the database collation,
    # where "Alp" precedes "ALTENBACH", and Python's default sort is
    # codepoint order, where it does not.
    page = find(categories=['cat_poi_food_restaurant'], sort='name', limit=10)
    lowered = [n.lower() for n in names(page)]
    assert lowered == sorted(lowered)


# --- paging and the total ------------------------------------------------

def test_count_equals_what_paging_through_returns():
    """The page's `total` and `/count` are two different statements and
    have to agree."""
    total = api.count(parse({'mode': 'name', 'text': 'landstrasse'}))
    seen = []
    for page_number in range(50):
        page = find(text='landstrasse', limit=3, page=page_number)
        seen += [f['id'] for f in page['results']['features']]
        if not page['has_more']:
            break
    assert total == len(seen) == len(set(seen)) > 3


def test_a_page_past_the_end_is_empty_and_says_so():
    page = find(text='vaduz', limit=10, page=999)
    assert page['results']['features'] == [] and page['has_more'] is False


def test_pages_do_not_overlap():
    first = [f['id'] for f in find(text='vaduz', limit=5, page=0)['results']['features']]
    second = [f['id'] for f in find(text='vaduz', limit=5, page=1)['results']['features']]
    assert not set(first) & set(second)


# --- the cache -----------------------------------------------------------

def test_the_same_request_twice_is_served_from_the_cache():
    api.clear_cache()
    first = find(text='hauptstrasse')
    assert find(text='hauptstrasse') is first          # the same object, not an equal one


def test_a_different_page_is_a_different_entry():
    api.clear_cache()
    assert find(text='vaduz', limit=5, page=0) is not find(text='vaduz', limit=5, page=1)


# --- the plan the database actually chooses ------------------------------

def explain(db, req) -> str:
    plan = name.fuzzy_plan(req)
    w = rank.weights()
    statement = api._statement(rank.build_sql(plan, req, count_only=False))
    params = {**rank.base_params(plan, req, w), 'min_score': w.min_score}
    conn = api._connect()
    try:
        rank.set_thresholds(conn, *rank.trgm_thresholds(req.similarity, w))
        rows = conn.execute(b'explain (analyze, costs off) ' + statement.as_bytes(conn),
                            params).fetchall()
        return '\n'.join(r['QUERY PLAN'] for r in rows)
    finally:
        conn.close()


def test_the_text_probes_use_a_trigram_index(db, small):
    """`search_name %% q` and `q <%% search_name` need a GIN trigram index.

    With one on `search_text` and only a btree on `search_name`, which a
    trigram operator cannot use, both hot probes are sequential scans.
    Invisible on `li`; on a region it is the whole query.
    """
    plan = explain(db, parse({'mode': 'name', 'text': 'hauptstrasse'}))
    assert 'search_name_gin_trgm_ops_idx' in plan, plan
    assert 'Bitmap Index Scan' in plan


def test_scoring_runs_on_the_candidates_not_on_the_table(db, small):
    """The whole performance story, and it rests on one keyword.

    Without MATERIALIZED the planner inlines `scored` and pushes
    `WHERE score >= min_score` down into the base scan, so the three
    trigram similarities and the phonetic subplan are evaluated on every
    row of the table and only then joined to the candidates. It returns
    the same rows, which is why nothing fails -- it just costs the whole
    table.
    """
    rows = db.execute(
        f'select count(*) from {small}.osm_search_object').fetchone()[0]
    plan = explain(db, parse({'mode': 'name', 'text': 'hauptstrasse'}))
    subplan_loops = [int(part.split('=')[1].rstrip(')'))
                     for line in plan.splitlines() if 'unnest' in line
                     for part in line.split() if part.startswith('loops=')]
    assert subplan_loops, plan
    assert max(subplan_loops) < rows / 2, f'scored {max(subplan_loops)} of {rows} rows'


# --- the formula, against hand-computed values ---------------------------

def test_an_exact_name_scores_one_plus_its_weighted_importance(small):
    top = find(text='Vaduz')['results']['features'][0]['properties']
    assert top['category'] == 'cat_geography_places_town'
    assert top['match_score'] == pytest.approx(2.00, abs=1e-4)


def test_a_perfect_match_scores_every_channel_and_every_bonus(small):
    """The score against hand-worked numbers.

    "vaduz" against the row whose `search_name` is exactly "vaduz":

        0.40 * similarity            = 0.40   (identical strings)
      + 0.35 * word_similarity       = 0.35   (identical strings)
      + 0.25 * phonetic              = 0.25   (equal Koelner codes -> 1.0)
      + 0.30 exact-name bonus        = 0.30
      + 0.10 prefix bonus            = 0.10   (LIKE 'vaduz%')
      + 1.00 importance              = 1.00   (a town: 100 x ranking.importance_weight)
                                     = 2.40

    If any weight, bonus or channel changes, this number moves -- which is
    the point: a change to the ranking has to be deliberate.
    """
    w = rank.weights()
    expected = (w.similarity + w.word_similarity + w.phonetic
                + w.exact_bonus + w.prefix_bonus + 100 * w.importance_weight)
    top = fuzzy('Vaduz')[0]
    assert top['name'] == 'Vaduz' and top['class'] == 'cls_place_town'
    assert top['score'] == pytest.approx(expected, abs=1e-4)
    assert top['score'] == pytest.approx(2.40, abs=1e-4)


def test_the_view_bonus_is_exactly_the_configured_amount(small):
    """The same row, once outside any view and once centred in one."""
    plain = find(text='Vaduz')['results']['features'][0]['properties']['match_score']
    viewed = find(text='Vaduz', bbox=[9.50, 47.13, 9.54, 47.15])['results']['features'][0]
    viewed = viewed['properties']['match_score']
    assert viewed - plain == pytest.approx(rank.weights().inside_view_bonus, abs=1e-4)


def test_a_prefix_match_scores_the_prefix_bonus_but_not_the_exact_one(small):
    # "vaduz" is a prefix of "vaduz sued", so 0.10 applies and 0.30 does not.
    w = rank.weights()
    prefixes = [row for row in fuzzy('Vaduz', limit=100)
                if row['name'].lower().startswith('vaduz') and row['name'].lower() != 'vaduz']
    if not prefixes:
        pytest.skip('no prefix-only match in this extract')
    # `match`, the score before importance, which alone can be worth 1.0.
    assert all(p['match'] < 1.0 + w.exact_bonus for p in prefixes)


@pytest.mark.parametrize('sort', ['score', 'name', 'address', 'distance'])
def test_every_sort_runs_in_name_mode(db, small, sort):
    """`sort=address` ordered on `number`, which is a column of
    `osm_search_address` and not of `osm_search_object` -- so it failed with
    `column "number" does not exist` for every name query that asked for it.
    """
    assert find(text='vaduz', sort=sort, near=[9.52, 47.14], limit=3)['total'] > 0


def test_a_town_is_one_result_with_its_outline():
    """"Berlin" was the place node first and the Land's polygon below it;
    a client highlighted a point (importer/places.py `merge_nodes`)."""
    towns = [f for f in find(text='Vaduz')['results']['features']
             if f['properties']['category'].startswith('cat_geography_places')
             or f['properties']['category'].startswith('cat_geography_admin')]
    assert len(towns) == 1
    town = towns[0]
    assert town['properties']['category'] == 'cat_geography_places_town'
    assert town['geometry']['type'] in ('Polygon', 'MultiPolygon')


def test_a_town_on_a_path_is_named_by_its_admin_level():
    features = find(text='Städtle')['results']['features']
    vaduz = [p for f in features for p in f['properties']['places'] if p['name'] == 'Vaduz']
    assert vaduz and all(p['category'] == 'cat_geography_admin_8' for p in vaduz)
    assert vaduz[0]['category_name'] == 'Gemeinde'
