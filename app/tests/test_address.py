"""The address mode: street and house number, optionally postcode and city,
each matched exactly.

The request half runs anywhere; the querying half needs the `li` schema,
Liechtenstein, whose postcodes are four digits.
"""

from __future__ import annotations

import pytest

from search import address, api
from search.request import parse


def request(**fields):
    return parse({'mode': 'address', **fields})


def find(**fields):
    return api.find(request(**fields))


def rows(page):
    return [(f['properties']['address_street'], f['properties']['address_housenumber'],
             f['properties']['address_city'])
            for f in page['results']['features']]


# --- the request (no database) -------------------------------------------

def test_the_street_is_expanded_as_the_importer_expanded_it():
    found = address.from_request(request(street='Holtenauer Str.', housenumber='12'))
    assert found.street == 'holtenauer strasse'


def test_a_house_number_suffix_is_split_off():
    # Stored as two columns, so the suffix is compared on its own.
    found = address.from_request(request(street='Mühleweg', housenumber='26 A'))
    assert (found.number, found.number_part) == (26, 'a')


def test_a_street_of_punctuation_matches_nothing():
    # Rather than a statement that compares every row with ''.
    assert address.from_request(request(street='- .', housenumber='1')) is None


def test_every_part_given_is_a_condition():
    """Scoring the parts as bonuses lets "Hauptstraße 5 Kiel" return
    every Hauptstraße 5 at the same relevance as the one in Kiel."""
    found = address.from_request(request(street='Hauptstraße', housenumber='5',
                                         postcode='24105', city='Kiel'))
    query, params = address.build_sql([found], request(street='x', housenumber='1'),
                                      count_only=False)
    where = query[query.index('cand AS'):query.index('SELECT a.id, a.osm_id')]
    for condition in ('a.search_street = %(street_0)s', 'a.number = %(number_0)s',
                      'a.number_part IS NOT DISTINCT FROM %(number_part_0)s',
                      'a.postcode = %(postcode_0)s', '= %(city_0)s',
                      'a.id_places && ARRAY('):
        assert condition in where, condition
    assert (params['street_0'], params['postcode_0'], params['city_0']) == \
        ('hauptstrasse', '24105', 'kiel')


def test_there_is_no_fuzzy_matching_left():
    found = address.from_request(request(street='Hauptstraße', housenumber='5'))
    query, _ = address.build_sql([found], request(street='x', housenumber='1'), count_only=False)
    for fuzzy in ('%%', 'similarity', 'phon_street'):
        assert fuzzy not in query


def test_the_view_box_is_tested_on_the_candidates_not_the_table():
    """On the table the planner takes the box for one row and scans the
    GiST for it: 58 000 rows filtered for four Bahnhofstraße 1 in a Kiel
    bbox on `de_sh`, 23 ms against 0.5."""
    found = address.from_request(request(street='Bahnhofstraße', housenumber='1'))
    query, _ = address.build_sql([found], request(street='x', housenumber='1', bbox=[9, 54, 10, 55]),
                                 count_only=False)
    assert 'cand AS MATERIALIZED' in query
    assert 'ST_Within(c.geom' in query and 'a.geom &&' not in query


# --- against the data ----------------------------------------------------

class TestAgainstSmall:
    pytestmark = pytest.mark.usefixtures('small')

    def test_without_postcode_or_city_every_match_comes_back(self, small):
        assert sorted(rows(find(street='Landstrasse', housenumber='11'))) == [
            ('Landstrasse', '11', 'Triesen'), ('Landstrasse', '11', 'Vaduz')]

    def test_a_city_narrows_it_to_that_city(self, small):
        assert rows(find(street='Landstrasse', housenumber='11', city='Vaduz')) == [
            ('Landstrasse', '11', 'Vaduz')]

    def test_a_postcode_narrows_it_to_that_postcode(self, small):
        assert rows(find(street='Landstrasse', housenumber='11', postcode='9495')) == [
            ('Landstrasse', '11', 'Triesen')]

    def test_a_city_or_postcode_that_does_not_match_returns_nothing(self, small):
        assert find(street='Landstrasse', housenumber='11', city='Schaan')['total'] == 0
        assert find(street='Landstrasse', housenumber='11', postcode='9494')['total'] == 0

    def test_the_city_is_found_on_the_address_path_too(self, small):
        """111 of Liechtenstein's addresses carry no `addr:city`; they
        still lie in a place, and the address path says which."""
        page = find(street='Doktor Grass-Strasse', housenumber='3', city='Vaduz')
        assert ('Doktor Grass-Strasse', '3', None) in rows(page)

    def test_the_street_is_not_fuzzy(self, small):
        assert find(street='Lanstrasse', housenumber='11')['total'] == 0

    def test_a_number_that_does_not_exist_returns_nothing(self, small):
        """Scoring the parts as bonuses returns the street's other houses instead."""
        assert find(street='Landstrasse', housenumber='9999')['total'] == 0

    def test_the_suffix_is_part_of_the_number(self, small):
        assert [r[1] for r in rows(find(street='Mühleweg', housenumber='26'))] == ['26']
        assert [r[1] for r in rows(find(street='Mühleweg', housenumber='26b'))] == ['26b']

    def test_an_umlaut_typed_as_ae_finds_the_umlaut(self, small):
        # The importer normalised Ä to ae; the request goes through the same
        # function, so this is equality, not fuzziness.
        assert rows(find(street='Aeulestrasse', housenumber='5', city='vaduz')) == [
            ('Äulestrasse', '5', 'Vaduz')]

    def test_every_result_has_the_address_relevance(self, small):
        page = find(street='Landstrasse', housenumber='11')
        assert {f['properties']['match_relevance'] for f in page['results']['features']} == {100}

    def test_with_a_point_the_nearest_comes_first(self, small):
        vaduz, triesen = (9.518, 47.143), (9.524, 47.122)
        assert rows(find(street='Landstrasse', housenumber='11', near=vaduz))[0][2] == 'Vaduz'
        assert rows(find(street='Landstrasse', housenumber='11', near=triesen))[0][2] == 'Triesen'

    def test_an_address_result_carries_an_osm_id_and_its_places(self, small):
        """The carrier's for a pure address -- most sit on an unnamed
        building, and osm_id against osm_building is the only route to the
        outline -- the object's otherwise."""
        properties = find(street='Landstrasse', housenumber='11')['results']['features'][0]['properties']
        assert properties['osm_ids'] and properties['places']

    def test_the_highlight_is_the_address_point(self, small):
        geometry = find(street='Landstrasse', housenumber='11')['results']['features'][0]['geometry']
        assert geometry['type'] == 'Point'

    def test_count_agrees_with_paging(self, small):
        body = {'street': 'Landstrasse', 'housenumber': '11'}
        total = api.count(request(**body))
        seen = []
        for page_number in range(10):
            page = find(**body, limit=1, page=page_number)
            seen += [f['id'] for f in page['results']['features']]
            if not page['has_more']:
                break
        assert total == len(seen) == len(set(seen)) == 2

    def test_a_bbox_narrows_the_result(self, small):
        inside = find(street='Landstrasse', housenumber='11', bbox=[9.50, 47.13, 9.53, 47.15])
        assert rows(inside) == [('Landstrasse', '11', 'Vaduz')]


# --- the city fold ------------------------------------------------------

def test_the_sql_city_fold_matches_lib_text_normalize(db, small):
    """`osm_search_address` stores the raw `addr:city`, so the city match has
    to fold it in SQL to compare it with a normalized request.

    Reading `lower(a.city)` against a query that has been through
    `lib.text.normalize` fails: "Lübeck" ("luebeck" to the query, "lübeck"
    to `lower`) can never match. On `de_sh` that is 152 472 of 723 655
    addresses. This walks every distinct
    city in the imported data and asserts the two agree, so the two
    normalizers cannot drift.
    """
    from psycopg import sql

    from lib import text

    statement = sql.SQL('select distinct city, {fold} as folded from {table}'
                        ' where city is not null').format(
        fold=sql.SQL(address.NORMALIZED_CITY.replace('a.city', 'city')),
        table=sql.Identifier(small, 'osm_search_address'))
    rows = db.execute(statement).fetchall()
    assert rows, 'no cities to compare'
    wrong = [(city, folded) for city, folded in rows if folded != text.normalize(city)]
    assert not wrong, wrong[:5]


def test_a_city_with_an_umlaut_folds_the_way_the_query_does(db):
    """The `li` extract has no umlaut city at all, which is why this was
    invisible there and is the whole reason for the case below."""
    from psycopg import sql

    from lib import text

    for city in ('Lübeck', 'Büdelsdorf', 'Süderbrarup', 'Groß Rönnau'):
        folded = db.execute(
            sql.SQL('select {fold}').format(
                fold=sql.SQL(address.NORMALIZED_CITY.replace('a.city', '%s')),
            ), (city,)).fetchone()[0]
        assert folded == text.normalize(city), city
