"""Street merging.

Merging street segments by *proximity* -- a spatial hash and a distance
threshold, with no name test on the join -- makes Bahnhofstraße in one
village one search result with Bahnhofstraße in the next. The last test here
is the regression test for it: same name, not touching, must stay two
objects.

Only ways that share an end node *and* a normalized name are joined, with no
distance fallback anywhere (`parameters.yaml`: merge_by: [end_node, name]).
"""

from __future__ import annotations

import pytest

pytest.importorskip('psycopg', reason='psycopg is installed in the container')

from importer.postprocess import UnionFind, components  # noqa: E402


def groups(rows):
    """Component assignment as a set of frozensets, ignoring the ids."""
    assignment = components(rows)
    out: dict[int, set] = {}
    for osm_id, component in assignment.items():
        out.setdefault(component, set()).add(osm_id)
    return {frozenset(v) for v in out.values()}


def test_ways_sharing_an_end_node_and_a_name_merge():
    rows = [(1, 'hauptstrasse', 100, 200),
            (2, 'hauptstrasse', 200, 300)]
    assert groups(rows) == {frozenset({1, 2})}


def test_a_chain_is_one_component():
    rows = [(i, 'hauptstrasse', i * 10, (i + 1) * 10) for i in range(1, 6)]
    assert groups(rows) == {frozenset({1, 2, 3, 4, 5})}


def test_a_chain_joined_from_both_ends():
    # The middle way arrives last, so the two halves have to be united then.
    rows = [(1, 'x', 10, 20), (3, 'x', 30, 40), (2, 'x', 20, 30)]
    assert groups(rows) == {frozenset({1, 2, 3})}


def test_different_names_at_the_same_junction_stay_apart():
    # Two real streets meeting at a corner share a node and are not one road.
    rows = [(1, 'hauptstrasse', 100, 200),
            (2, 'bahnhofstrasse', 200, 300)]
    assert groups(rows) == {frozenset({1}), frozenset({2})}


def test_same_name_without_a_shared_node_stays_apart():
    """The proximity-merge regression test.

    Bahnhofstraße in two neighbouring villages: identical name, close
    together, no shared node. A proximity merge makes these one object.
    """
    rows = [(1, 'bahnhofstrasse', 100, 200),
            (2, 'bahnhofstrasse', 300, 400)]
    assert groups(rows) == {frozenset({1}), frozenset({2})}


def test_a_ring_is_one_component():
    rows = [(1, 'ring', 10, 20), (2, 'ring', 20, 30), (3, 'ring', 30, 10)]
    assert groups(rows) == {frozenset({1, 2, 3})}


def test_a_single_way_is_its_own_component():
    assert groups([(7, 'x', 1, 2)]) == {frozenset({7})}


def test_a_way_whose_ends_coincide():
    # A closed loop mapped as one way: both ends are the same node.
    assert groups([(7, 'x', 1, 1)]) == {frozenset({7})}


def test_no_rows():
    assert components([]) == {}


def test_three_streets_of_the_same_name_in_one_town():
    # Two connected pieces and one detached: two objects, not one and not
    # three.
    rows = [(1, 'muehlenweg', 10, 20), (2, 'muehlenweg', 20, 30),
            (3, 'muehlenweg', 90, 91)]
    assert groups(rows) == {frozenset({1, 2}), frozenset({3})}


def test_union_find_is_transitive():
    union = UnionFind()
    union.union(1, 2)
    union.union(2, 3)
    union.union(4, 5)
    assert union.find(1) == union.find(3)
    assert union.find(1) != union.find(4)


def test_union_find_handles_repeated_unions():
    union = UnionFind()
    for _ in range(3):
        union.union(1, 2)
    assert union.find(1) == union.find(2)


# --- the merged row ------------------------------------------------------

@pytest.fixture
def merge_schema(db, temp_schema):
    from importer import tables as t
    for table in (t.OSM_LINE, t.STREET_ENDS, t.OSM_SEARCH_OBJECT):
        db.execute(t.ddl(temp_schema, table))
    return temp_schema


def add_way(db, schema, params, osm_id, cls, category, n1, n2, name='Kölner Straße'):
    from lib import text
    search_name = text.expand_street(name)
    x = osm_id * 10
    db.execute(f'insert into {schema}.osm_line (osm_id, class, name, z_order, minzoom, geom) '
               f"values (%s, %s, %s, 0, 0, st_geomfromtext('LINESTRING({x} 0, {x + 10} 0)', 3857))",
               (osm_id, cls, name))
    db.execute(f'insert into {schema}._street_ends values (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
               (osm_id, name, search_name, text.phonetic(search_name), cls, category,
                params.rank(cls), n1, n2))


def merge(schema, classifier) -> int:
    # The import's connection: merge_streets reads through a named cursor, which needs a
    # transaction, and the db fixture's connection is autocommit.
    from importer import postprocess
    from lib import db as db_module
    with db_module.connection() as conn:
        return postprocess.merge_streets(conn, schema, classifier)


def merged(db, schema):
    return db.execute(
        f'select category, class, cardinality(osm_ids) from {schema}.osm_search_object').fetchall()


def test_a_street_with_a_named_crossing_and_sidepath_keeps_its_road_class(
        db, merge_schema, classifier, params):
    """Kölner Straße in Düsseldorf-Oberbilk: the carriageways share end nodes
    with a crossing way and a cycleway that carry the street's name. Taken by
    min(), the crossing's category (importance 0) dropped the whole street
    from search, and without it the cycleway's made it a path."""
    add_way(db, merge_schema, params, 1, 'cls_road_secondary', 'cat_built_roads_secondary', 10, 20)
    add_way(db, merge_schema, params, 2, 'cls_road_path',
            'cat_built_roads_crossing_pathcrossing_bicyclefoot', 20, 30)
    add_way(db, merge_schema, params, 3, 'cls_road_path', 'cat_built_roads_cycleway', 30, 40)
    assert merge(merge_schema, classifier) == 1
    assert merged(db, merge_schema) == [('cat_built_roads_secondary', 'cls_road_secondary', 3)]


def test_equal_importance_takes_the_higher_road_class(db, merge_schema, classifier, params):
    # Both are roads of importance 80; "minor" sorts first, the secondary road ranks higher.
    add_way(db, merge_schema, params, 1, 'cls_road_minor', 'cat_built_roads_minor', 10, 20)
    add_way(db, merge_schema, params, 2, 'cls_road_secondary', 'cat_built_roads_secondary', 20, 30)
    assert merge(merge_schema, classifier) == 1
    assert merged(db, merge_schema) == [('cat_built_roads_secondary', 'cls_road_secondary', 2)]


def test_a_bridge_does_not_give_the_street_its_class(db, merge_schema, classifier, params):
    """A bridge ranks with its road; the street is the road, not the bridge."""
    add_way(db, merge_schema, params, 1, 'cls_road_primary_bridge', 'cat_built_roads_primary', 10, 20)
    add_way(db, merge_schema, params, 2, 'cls_road_primary', 'cat_built_roads_primary', 20, 30)
    assert merge(merge_schema, classifier) == 1
    assert merged(db, merge_schema) == [('cat_built_roads_primary', 'cls_road_primary', 2)]
