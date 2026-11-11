"""What the pbf passes decide per object, without a pbf."""

from __future__ import annotations

import pytest

pytest.importorskip('osmium', reason='pyosmium is installed in the container')

from importer import passes  # noqa: E402


def area_result(classifier, tags):
    bits = classifier.tag_bits(tags)
    return bits, classifier.classify(bits, 'polygon')


@pytest.mark.parametrize('tags', [
    {'highway': 'residential', 'name': 'name_1'},
    {'highway': 'living_street', 'name': 'name_1'},
])
def test_a_closed_road_is_not_also_an_area(classifier, tags):
    """The ways pass drew it as a line; as an area it would be a second
    search object, filed as "other road"."""
    bits, result = area_result(classifier, tags)
    assert passes.drawn_as_line(classifier, bits, tags, result)


@pytest.mark.parametrize('tags', [
    # A pedestrian square is an area because it says so.
    {'highway': 'pedestrian', 'area': 'yes', 'name': 'name_1'},
    # An area with a class of its own.
    {'landuse': 'forest'},
    {'amenity': 'school', 'name': 'name_1'},
])
def test_a_real_area_stays(classifier, tags):
    bits, result = area_result(classifier, tags)
    assert not passes.drawn_as_line(classifier, bits, tags, result)


@pytest.mark.parametrize('option, ways', [
    ('flex_mem', 'flex_mem'),
    # Two passes may run at once; one file would be written by both.
    ('sparse_file_array,/data/tmp/nodes', 'sparse_file_array,/data/tmp/nodes.ways'),
])
def test_a_file_node_cache_is_a_file_per_pass(monkeypatch, option, ways):
    monkeypatch.setattr(passes.config, 'opt', lambda path, default=None: option)
    assert passes.location_store('ways') == ways
    assert passes.location_store('areas') == ways.replace('.ways', '.areas')
