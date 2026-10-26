"""The phrase mode: the parser's readings, the rules run on them, the merge.

The design is a refusal to parse -- "restaurant Kiel" and "restaurant Maxim"
have the same shape -- so what is tested here is that every reading the
dictionaries support is produced, that each rule runs on the readings with
its parts, and that the steps stop where they should, not that any one
string is read the "right" way.
"""

from __future__ import annotations

import pytest

from search import api, phrase, place, rules
from search.request import parse

pytestmark = pytest.mark.usefixtures('small')


def find(q, **body):
    return api.find(parse({'mode': 'phrase', 'text': q, **body}))


def ran(page):
    return [i['rule'] for i in page['interpretation']]


def found(page):
    return [i['rule'] for i in page['interpretation'] if i['rows']]


def props(page):
    return [f['properties'] for f in page['results']['features']]


def rules_of(page):
    return [p['match_rule'] for p in props(page)]


# --- tokens and spans (no database) --------------------------------------

def test_spans_are_longest_first():
    got = [text for *_, text in phrase.spans(['a', 'b', 'c'])]
    assert got[0] == 'a b c'
    assert got[-3:] == ['a', 'b', 'c']


def test_a_query_of_n_tokens_offers_n_times_n_plus_one_over_two_spans():
    # Two to four tokens, so at most ten strings and one `= ANY(...)`
    # probe per dictionary.
    assert len(phrase.spans(['a', 'b', 'c', 'd'])) == 10


# --- readings ------------------------------------------------------------

def parsed(q, lang='de'):
    conn = api._connect()
    try:
        return phrase.parse(conn, api._statement, q, lang)
    finally:
        conn.close()


def shapes(q):
    return {(r.name, r.category, r.place.name if r.place else None, r.street) for r in parsed(q)}


def test_a_category_and_a_place_and_a_name_and_a_place_are_both_readings():
    """"restaurant vaduz" is the restaurants in Vaduz and anything called
    "Restaurant" there; the rules decide, not the parser."""
    got = shapes('restaurant vaduz')
    assert (None, 'cat_poi_food_restaurant', 'Vaduz', None) in got
    assert ('restaurant', None, 'Vaduz', None) in got


def test_the_rest_is_no_name_when_it_is_a_place():
    """"restaurant Kiel" is not a restaurant named like Kiel."""
    assert ('vaduz', 'cat_poi_food_restaurant', None, None) not in shapes('restaurant vaduz')


def test_a_stop_word_between_parts_is_dropped():
    assert any(r.category and r.place.name == 'Schaan' and r.name is None
               for r in parsed('hotel in schaan') if r.place)


@pytest.mark.parametrize('q', ['staedtle vaduz', 'Vaduz Städtle', 'Städtle in Vaduz'])
def test_a_place_at_either_end_leaves_a_name(q):
    assert ('staedtle', None, 'Vaduz', None) in shapes(q)


def test_a_street_is_read_anywhere():
    assert (None, 'cat_poi_food_restaurant', 'Vaduz', 'landstrasse') in \
        shapes('restaurant Landstrasse vaduz')


def test_a_single_word_has_no_readings_of_parts():
    """It is step 1's: the whole query as a name or a category."""
    assert parsed('vaduz') == ()


def test_every_reading_has_two_parts_at_least():
    assert all(len(r.parts) >= 2 for r in parsed('restaurant Landstrasse vaduz') if not r.addresses)


def test_the_node_of_a_place_with_a_border_adds_no_radius():
    """Vaduz is a town node inside Vaduz's boundary; its 5 km would reach
    into Schaan and Triesen."""
    vaduz = next(r.place for r in parsed('Städtle Vaduz') if r.place)
    assert vaduz.ids and vaduz.points == ()


def test_a_place_without_a_border_is_its_centre_and_a_radius():
    gaflei = next(r.place for r in parsed('Matustrasse Gaflei') if r.place)
    assert gaflei.ids == () and gaflei.points
    assert all(radius == place.radius_for('cls_place_hamlet') for *_, radius in gaflei.points)


def test_an_address_is_one_reading_with_every_split():
    readings = [r for r in parsed('Vaduz Landstrasse 11') if r.addresses]
    assert len(readings) == 1 and len(readings[0].addresses) >= 1


# --- place radii ---------------------------------------------------------

def test_a_place_without_a_polygon_gets_a_radius_by_rank():
    radii = place.radii()
    assert radii['cls_place_city'] == 10_000 and radii['cls_place_village'] == 2_000
    assert place.radius_for('cls_place_town') == 5_000


def test_an_unranked_place_gets_the_smallest_radius():
    """Guessing large on a place nobody ranked sweeps in a whole region's
    restaurants and calls them that place's."""
    assert place.radius_for(None) == min(place.radii().values())
    assert place.radius_for('place_other') == min(place.radii().values())


# --- step 1: the whole query ---------------------------------------------

def test_an_exact_name_ends_the_search():
    """Found in step 1, so nothing else runs: "Vaduz" is the places called
    that, not "Vaduz Au" as well."""
    page = find('vaduz', limit=100)
    assert names(page)[0] == 'Vaduz'
    assert set(rules_of(page)) == {'name_text'}
    assert ran(page) == ['name_text']


def test_step_one_needs_no_parse(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('parsed')
    monkeypatch.setattr(phrase, 'parse', refuse)
    api.clear_cache()
    assert find('vaduz')['results']['features']
    assert find('restaurant')['results']['features']


def test_a_bare_category_is_the_category_nearest_first():
    page = find('restaurant', near=[9.52, 47.14], limit=20)
    assert 'category_text' in found(page)
    rows = [p for p in props(page) if p['match_rule'] == 'category_text']
    assert all(p['category'].startswith('cat_poi_food_restaurant') for p in rows)
    distances = [p['match_distance'] for p in rows]
    assert distances == sorted(distances)


def test_the_bare_category_is_narrowed_by_a_bbox():
    everywhere = find('restaurant')['total']
    inside = find('restaurant', bbox=[9.50, 47.13, 9.53, 47.15])['total']
    assert 0 < inside < everywhere


# --- the rules on readings -----------------------------------------------

def names(page):
    return [p['name'] for p in props(page)]


def test_category_in_place_returns_the_category_in_the_place():
    page = find('restaurant vaduz', limit=100)
    assert 'category_in_place' in found(page)
    for row in props(page):
        assert row['match_rule'] == 'category_in_place'
        assert 'Vaduz' in [p['name'] for p in row['places']]
        assert 'cat_poi_food_restaurant' in [c['id'] for c in row['categories']]


def test_the_rules_of_a_step_run_together():
    """"restaurant vaduz" runs name in place and category in place in one
    step. Stopping at the first rule with rows would lose the second."""
    page = find('restaurant vaduz', limit=100)
    assert {'name_in_place', 'category_in_place'} <= set(ran(page))


def test_a_name_in_a_place_is_only_found_in_that_place():
    page = find('Landstrasse Vaduz', limit=50)
    rows = [p for p in props(page) if p['match_rule'] == 'name_in_place']
    assert rows and all(p['name'] == 'Landstrasse' for p in rows)
    assert all('Vaduz' in [p['name'] for p in row['places']] for row in rows)


def test_a_name_in_a_place_is_also_the_name_with_the_place_on_either_side():
    """"Hauptbahnhof Kiel" is mapped as "Kiel Hauptbahnhof"; matched by
    the name alone, the station was never a candidate. Bus stops are named
    so too, and must not outrank the street of that name."""
    page = find('Rheinstrasse Balzers')
    rows = [p for p in props(page) if p['match_rule'] == 'name_in_place']
    assert rows[0]['name'] == 'Rheinstrasse'
    assert 'Balzers Rheinstrasse' in [p['name'] for p in rows]


def test_a_name_near_a_place_without_a_border():
    """Gaflei is a hamlet node: no path holds it, so its objects are the
    ones within its radius -- a step after the ones in a place."""
    page = find('Matustrasse Gaflei', limit=20)
    assert found(page) == ['name_near_place']
    assert names(page)[0] == 'Matustrasse'


def test_nothing_beyond_the_radius_of_a_place_without_a_border():
    """No Landstrasse lies near Gaflei: only the fuzzy whole-query step,
    which ignores the place, finds one; above its relevance, nothing."""
    assert found(find('Landstrasse Gaflei', limit=50)) == ['name_like_text']
    assert not find('Landstrasse Gaflei', limit=50, relevance=21)['results']['features']


def test_a_category_near_a_place_without_a_border():
    page = find('restaurant Gaflei', limit=20)
    assert found(page) == ['category_near_place']


def test_a_category_on_a_street():
    """"Bäckerei Holtenauer Straße" -- a category along a street. The
    street is no place, so a place rule finds nothing."""
    page = find('restaurant Landstrasse', limit=50)
    assert 'category_on_street' in found(page) and 'category_near_street' in ran(page)
    assert all('cat_poi_food_restaurant' in [c['id'] for c in p['categories']] for p in props(page))


def test_near_a_street_is_near_the_one_nearest_the_request():
    """Not every street of the name: on `de` that was everything
    along every Hauptstraße. Without a location there is no telling which
    one is meant, and the rule finds nothing."""
    near = find('restaurant Landstrasse', near=[9.52, 47.14], limit=100)
    assert 'category_near_street' in found(near)
    assert 'category_near_street' not in found(find('restaurant Landstrasse', limit=100))


def test_a_category_on_a_street_in_a_place():
    page = find('restaurant Landstrasse vaduz', limit=50)
    assert found(page) == ['category_on_street_in_place']
    assert names(page) == ['Pizza e Pinsa']


def test_a_category_and_a_name_fragment():
    page = find('restaurant piazza')
    assert found(page) == ['category_name_like'] and names(page) == ['La Piazza']


def test_a_category_and_a_name_fragment_in_a_place():
    page = find('restaurant salento triesen')
    assert 'category_name_like_in_place' in found(page)
    assert names(page)[0] == 'Pizzeria Il Salento'


def test_a_name_fragment_in_a_place():
    page = find('Städtl Vaduz')
    assert found(page) == ['name_like_in_place']
    assert all('Städtle' in name for name in names(page))


def test_a_strict_fragment_rule_drops_rows_far_below_its_best(monkeypatch):
    """The bus stop "Balzers Schlossweg" matches "Schlosweg Balzers" at
    0.65 of the street; a share above that drops it, which no floor can
    without dropping a lone weak hit elsewhere."""
    from dataclasses import replace

    from search import rank
    for share, stop in ((0.0, True), (0.9, False)):
        monkeypatch.setattr(rank, '_weights', replace(rank.weights(), phrase_strict_best_share=share))
        api.clear_cache()
        page = find('Schlosweg Balzers')
        assert found(page) == ['name_like_in_place']
        assert ('Balzers Schlossweg' in names(page)) == stop, share
        assert 'Schlossweg' in names(page)


def test_a_typo_falls_to_the_fuzzy_step():
    page = find('Vaduzz')
    assert found(page) == ['name_like_text']
    assert 'Vaduz' in names(page)


def test_a_disabled_step_does_not_run():
    page = find('qqzz Vaduz')
    assert 'name_like_in_place' in ran(page)
    assert 'name_nearest_place' not in ran(page)


# --- relevance, filters, the interpretation ------------------------------

def test_the_relevance_is_the_step_s():
    relevance = {rule.id: step.relevance for step in rules.steps() for rule in step.rules}
    for q in ('vaduz', 'restaurant vaduz', 'Matustrasse Gaflei', 'Landstrasse 11 Vaduz'):
        for row in props(find(q, limit=100)):
            assert row['match_relevance'] == relevance[row['match_rule']], q


def test_a_relevance_floor_skips_the_steps_below_it():
    page = find('restaurant Gaflei', relevance=70)
    assert not page['results']['features']
    assert 'category_near_place' not in ran(page)


def test_the_request_categories_filter_what_the_rules_found():
    page = find('Landstrasse Vaduz', categories=['cat_poi_food_restaurant'])
    assert all('cat_poi_food_restaurant' in [c['id'] for c in p['categories']] for p in props(page))


def test_every_result_says_which_rule_found_it():
    page = find('restaurant vaduz', limit=20)
    assert all(p['match_rule'] for p in props(page))


def test_the_interpretation_is_always_reported():
    """A phrase search that returns the wrong thing is unexplainable
    without it: the user sees a list and cannot tell whether "Vaduz" was
    read as a place, a name or neither."""
    for q in ('vaduz', 'restaurant vaduz', 'restaurant', 'qqzz'):
        assert find(q, limit=1)['interpretation']


def test_the_interpretation_names_the_parts():
    entry = next(i for i in find('restaurant vaduz')['interpretation']
                 if i['rule'] == 'category_in_place')
    assert (entry['category'], entry['term'], entry['place']) == \
        ('cat_poi_food_restaurant', 'restaurant', 'Vaduz')
    assert entry['where'] == 'category = query.category AND location IN query.place'


# --- the merge -----------------------------------------------------------

def test_a_row_found_by_two_rules_appears_once():
    page = find('Landstrasse Vaduz', limit=100)
    ids = [f['id'] for f in page['results']['features']]
    assert len(ids) == len(set(ids))


def test_the_rules_come_in_their_order():
    order = [rule.id for step in rules.steps() for rule in step.rules]
    got = rules_of(find('Landstrasse Vaduz', limit=100))
    assert got == sorted(got, key=order.index)


def test_paging_the_merged_list_does_not_repeat_or_drop():
    first = find('restaurant vaduz', limit=10, page=0)
    second = find('restaurant vaduz', limit=10, page=1)
    assert not ({f['id'] for f in first['results']['features']}
                & {f['id'] for f in second['results']['features']})
    assert first['total'] == second['total']


def test_count_on_a_phrase_is_the_merged_size():
    """There is no uncapped form: capped rules merged in Python have no
    window to count over."""
    req = parse({'mode': 'phrase', 'text': 'restaurant vaduz'})
    assert api.count(req) == api.find(req)['total']


def test_an_address_and_an_object_with_the_same_id_both_stay():
    """Two tables whose ids overlap: the merge must not take one for the
    other."""
    rule = rules.parse_rule('rule_1', 'name = query.text')
    reading = rules.Reading(text='x')
    runs = [phrase.Run(rule, reading, [{'id': 7, 'street': 'x', 'reading': 0}], 100),
            phrase.Run(rule, reading, [{'id': 7, 'name': 'x'}, {'id': 7, 'name': 'x'}], 99)]
    merged, total = phrase.merge(runs, 10, 0)
    assert total == 2
    assert [(r['id'], r['relevance']) for r in merged] == [(7, 100), (7, 99)]


# --- the address reading -------------------------------------------------

def readings(q):
    return [(a.street, a.number, a.number_part, a.postcode, a.city)
            for a in phrase.parse_address(q)]


def test_street_number_postcode_city_is_one_reading():
    assert readings('Holtenauer Str. 12, 24105 Kiel') == [
        ('holtenauer strasse', 12, None, '24105', 'kiel')]


@pytest.mark.parametrize('q', ['Holtenauer Straße 12 Kiel', 'Holtenauer Straße 12 24105',
                               'Holtenauer Straße 12 in Kiel'])
def test_a_postcode_or_a_city_is_enough(q):
    assert [r[:2] for r in readings(q)] == [('holtenauer strasse', 12)]


def test_without_postcode_or_city_there_is_no_reading():
    """Every Hauptstraße 5 there is: the address mode answers that when
    asked, the phrase mode does not guess at it."""
    assert readings('Hauptstraße 5') == []


def test_a_city_first_is_read_at_every_split():
    assert set(readings('Bad Oldesloe Hamburger Straße 12')) == {
        ('oldesloe hamburger strasse', 12, None, None, 'bad'),
        ('hamburger strasse', 12, None, None, 'bad oldesloe'),
        ('strasse', 12, None, None, 'bad oldesloe hamburger'),
    }


@pytest.mark.parametrize('q', ['Mühleweg 26b Vaduz', 'Mühleweg 26 b Vaduz'])
def test_the_suffix_is_read_attached_or_apart(q):
    assert readings(q) == [('muehleweg', 26, 'b', None, 'vaduz')]


def test_a_number_in_the_street_name_is_not_the_house_number():
    assert ('strasse des 17 juni', 5, None, None, 'berlin') in \
        readings('Straße des 17. Juni 5 Berlin')


def test_an_exact_address_is_the_answer():
    """Found in step 2, so no later step runs."""
    page = find('Landstrasse 11 Vaduz', limit=20)
    rows = props(page)
    assert (rows[0]['address_street'], rows[0]['address_housenumber'], rows[0]['address_city']) == \
        ('Landstrasse', '11', 'Vaduz')
    assert all((r['match_rule'], r['match_relevance']) == ('address', 100) for r in rows)
    assert found(page) == ['address']
    entry = next(i for i in page['interpretation'] if i['rule'] == 'address')
    assert [a['street'] for a in entry['addresses']] == ['landstrasse']


def test_the_city_first_finds_the_same_address():
    top = find('Vaduz Landstrasse 11', limit=1)['results']['features'][0]['properties']
    assert (top['address_street'], top['address_housenumber'], top['address_city']) == \
        ('Landstrasse', '11', 'Vaduz')


@pytest.mark.parametrize('q', ['Landstrasse 11', 'Landstrasse 11 Schaan', 'Lanstrasse 11 Vaduz'])
def test_an_address_that_does_not_match_exactly_adds_nothing(q):
    """Landstrasse 11 is in Vaduz and in Triesen, not in Schaan; without a
    city it is both; misspelt it is neither."""
    page = find(q, limit=100)
    assert not any(f['id'].startswith('a') for f in page['results']['features'])
    assert 'address' not in found(page)


def test_a_category_filter_leaves_the_address_out():
    page = find('Landstrasse 11 Vaduz', categories=['cat_poi'])
    assert not any(f['id'].startswith('a') for f in page['results']['features'])
