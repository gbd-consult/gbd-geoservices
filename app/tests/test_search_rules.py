"""The phrase rules: the grammar, the rules file, and what each rule compiles to.

A rule that compiles to a statement no index can answer still returns the
right rows -- by reading the whole table. So every rule of the file, enabled
or not, is compiled on `li` and its plan checked for a sequential scan of
the two big tables, with sequential scans priced out: what is left is a scan
the statement cannot avoid.
"""

from __future__ import annotations

import pytest

from search import api, phrase, rank, rules
from search.request import parse as parse_request
from search.rules import Atom, RuleError, parse_rule

# --- the grammar (no database) -------------------------------------------


def test_a_rule_is_clauses_of_atoms():
    rule = parse_rule('rule_1', 'name LIKE query.name'
                                ' AND (location IN query.place OR location NEAR query.place)')
    assert rule.clauses == (
        (Atom('name', 'LIKE', 'name'),),
        (Atom('location', 'IN', 'place'), Atom('location', 'NEAR', 'place')),
    )
    assert rule.parts == {'name', 'place'}
    assert rule.like == Atom('name', 'LIKE', 'name')


def test_the_order_by_names_a_part():
    rule = parse_rule('rule_1', 'name = query.name ORDER BY distance(location, query.place)')
    assert rule.order == rules.ORDER_DISTANCE_PLACE
    assert rule.parts == {'name', 'place'}


def test_keywords_are_case_blind():
    assert parse_rule('rule_1', 'category = query.category and location in query.place').parts == \
        {'category', 'place'}


def test_the_whole_query_and_the_request_location_are_no_reading_parts():
    rule = parse_rule('rule_1', 'category = query.text AND location NEAR query.location')
    assert rule.on_text and rule.parts == frozenset()


def test_an_address_rule_runs_on_the_address_table():
    rule = parse_rule('rule_1', 'address.street LIKE query.street'
                                ' AND address.housenumber = query.housenumber')
    assert rule.on_addresses and rule.street_like


@pytest.mark.parametrize('source', [
    'name ~ query.name',
    'name = query.nothing',
    'colour = query.name',
    'name = name',
    'name = query.name AND',
    'name = query.name OR category = query.category',
    '(name = query.name',
    'name = query.name ORDER BY name',
    'name = query.name extra',
])
def test_what_the_grammar_refuses(source):
    with pytest.raises(RuleError):
        parse_rule('rule_1', source)


@pytest.mark.parametrize('source', [
    'name = query.name AND address.housenumber = query.housenumber',
    'name = query.text AND location IN query.place',
    'name LIKE query.name AND category = query.category AND name LIKE query.name',
])
def test_what_no_statement_can_run_is_refused_at_load(source):
    with pytest.raises(RuleError):
        parse_rule('rule_1', source)


def test_a_rule_id_is_defined_once():
    with pytest.raises(RuleError):
        rules.load({'steps': [{'relevance': 1, 'rules': {'rule_1': 'name = query.text'}},
                              {'relevance': 1, 'rules': {'rule_1': 'name = query.text'}}]})


# --- the rules file ------------------------------------------------------

def test_the_rules_file_loads():
    steps = rules.steps()
    assert steps and all(step.rules for step in steps)


def test_step_one_needs_no_parse():
    """Most queries are a name or a category term as they stand, and
    answering them costs one probe each rather than the full parse."""
    assert all(rule.on_text for rule in rules.steps()[0].rules)


def test_every_object_rule_can_be_met_by_some_reading():
    for step in rules.steps():
        for rule in step.rules:
            if not (rule.on_text or rule.on_addresses):
                assert rule.parts <= rules.READING_PARTS and len(rule.parts) >= 2, rule.id


def test_the_emitted_sql_escapes_its_percents():
    from test_rank import percent_is_escaped
    for sql in (rules.IN_PATH, rules.IN_AREA.format(i=0), rules.NEAR_POINT.format(i=0),
                rules.NEAR_PLACE, rules.NEAR_STREET_CTE, rules.NEAR_STREET, rules.ON_STREET,
                rules.NAME_EQUALS, rules.CATEGORY_EQUALS):
        assert percent_is_escaped(sql)


# --- every rule, compiled and planned ------------------------------------

#: Queries that between them give every object rule a reading on `li`.
QUERIES = (
    'restaurant adler vaduz', 'Städtle Vaduz', 'Adler Landstrasse', 'restaurant adler',
    'restaurant vaduz', 'restaurant Landstrasse vaduz', 'restaurant Landstrasse',
    'Matustrasse Gaflei', 'restaurant Gaflei', 'restaurant',
)


def plan_text(conn, statement, params) -> str:
    conn.execute('SET LOCAL enable_seqscan = off')
    rows = conn.execute(b'explain (costs off) ' + statement.as_bytes(conn), params).fetchall()
    return '\n'.join(r['QUERY PLAN'] for r in rows)


@pytest.mark.usefixtures('small')
def test_every_rule_stays_off_a_sequential_scan():
    w = rank.weights()
    req = parse_request({'mode': 'phrase', 'text': 'x', 'near': [9.52, 47.14]})
    covered = set()
    conn = api._connect()
    try:
        for q in QUERIES:
            parsed = phrase.parse(conn, api._statement, q)
            whole = phrase.read_text(conn, api._statement, q)
            for step in rules.steps():
                for rule in step.rules:
                    if rule.on_addresses:
                        continue
                    if rule.on_text:
                        readings = [whole] if phrase._fits_text(rule, whole) else []
                    else:
                        readings = [r for r in parsed if r.parts == rule.parts]
                    for reading in readings:
                        compiled = rules.compile_rule(rule, reading, req, phrase.RULE_LIMIT, w)
                        if compiled is None:
                            continue
                        statement = api._statement(
                            rank.build_sql(compiled.plan, compiled.req, count_only=False))
                        params = {**rank.base_params(compiled.plan, compiled.req, w),
                                  'min_score': compiled.min_score}
                        plan = plan_text(conn, statement, params)
                        assert 'Seq Scan on osm_search_object' not in plan, (rule.id, q, plan)
                        assert 'Seq Scan on osm_street' not in plan, (rule.id, q, plan)
                        assert 'Seq Scan on osm_search_address' not in plan, (rule.id, q, plan)
                        covered.add(rule.id)
    finally:
        conn.close()
    object_rules = {rule.id for step in rules.steps() for rule in step.rules if not rule.on_addresses}
    assert covered == object_rules


@pytest.mark.usefixtures('small')
@pytest.mark.parametrize('street_like', [False, True])
def test_the_address_rules_stay_off_a_sequential_scan(street_like):
    from search import address
    req = parse_request({'mode': 'phrase', 'text': 'x'})
    readings = phrase.parse_address('Landstrasse 11 Vaduz')
    query, params = address.build_sql(readings, req, count_only=False, limit=10, street_like=street_like)
    conn = api._connect()
    try:
        plan = plan_text(conn, api._statement(query), params)
    finally:
        conn.close()
    assert 'Seq Scan' not in plan, plan
