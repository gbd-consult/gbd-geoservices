"""The report against the previous import: what moved, and what is left out."""

from __future__ import annotations

from importer import changes


def meta(row_counts=None, table_classes=None) -> dict:
    return {'row_counts': row_counts or {}, 'table_classes': table_classes or {}}


def moved(old: dict, new: dict, change_pct: float = 2, min_rows: int = 10) -> dict[str, tuple]:
    return {c.key: (c.old, c.new) for c in changes.compare(
        changes.counts(old), changes.counts(new), change_pct=change_pct, min_rows=min_rows)}


def test_counts_flattens_both_sets():
    flat = changes.counts(meta({'ways': {'line': 5, 'point': 1}, 'indexes': 57},
                               {'osm_line': {'cls_road_primary': 4}}))
    assert flat == {'ways.line': 5, 'ways.point': 1, 'indexes': 57,
                    'osm_line cls_road_primary': 4}


def test_a_class_that_vanished_is_reported_while_its_table_is_not():
    """Why the report is per class: a broken rule takes one class to zero,
    and its table moves by under 1 %."""
    old = meta({'ways': {'line': 10_000}}, {'osm_line': {'cls_road_primary': 60, 'cls_road_minor': 9_940}})
    new = meta({'ways': {'line': 9_940}}, {'osm_line': {'cls_road_minor': 9_940}})
    assert moved(old, new) == {'osm_line cls_road_primary': (60, 0)}


def test_a_small_class_that_moved_by_a_few_rows_is_not_reported():
    old = meta(table_classes={'osm_point': {'cls_poi_food': 3, 'cls_poi_health': 1_000}})
    new = meta(table_classes={'osm_point': {'cls_poi_food': 4, 'cls_poi_health': 1_015}})
    assert moved(old, new) == {}


def test_a_large_move_is_reported_and_a_new_class_however_small():
    old = meta(table_classes={'osm_point': {'cls_poi_health': 1_000}})
    new = meta(table_classes={'osm_point': {'cls_poi_health': 1_100, 'cls_poi_food': 1}})
    assert moved(old, new) == {'osm_point cls_poi_health': (1_000, 1_100),
                               'osm_point cls_poi_food': (0, 1)}


def test_new_counts_first_then_the_largest_relative_move():
    old = {'a': 100, 'b': 100, 'c': 100}
    new = {'a': 110, 'b': 0, 'c': 150, 'd': 5}
    order = [c.key for c in changes.compare(old, new, change_pct=2, min_rows=1)]
    assert order == ['d', 'b', 'c', 'a']


def test_report_says_when_nothing_moved():
    assert changes.report('li_20261001_000000', [], 40, 2) == [
        'against li_20261001_000000: none of 40 counts moved by more than 2 %']


def test_report_lists_each_change():
    lines = changes.report('li_x', [changes.Change('osm_line cls_road_primary', 60, 0),
                                    changes.Change('ways.line', 1_000, 1_200)], 40, 2)
    assert lines[1:] == ['  osm_line cls_road_primary: 60 -> 0 (-100.0 %)',
                         '  ways.line: 1,000 -> 1,200 (+20.0 %)']
