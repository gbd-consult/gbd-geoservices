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
