"""lib/text.py's behaviour, frozen.

The importer and the query side both normalize through this module, and a
normalizer that changed would silently stop rows written by one import
matching queries normalized by the new code -- both sides would still
return results. The expectations in data/text_expected.json cover 320 names
taken from the Schleswig-Holstein extract plus the edge cases that shaped
the module. A deliberate change updates them and needs a re-import.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import text

DATA = Path(__file__).parent / 'data'
CORPUS = DATA / 'names_sh.txt'
EXPECTED = DATA / 'text_expected.json'

#: Every public name in the module.
FUNCTIONS = ['normalize', 'expand_street', 'phonetic', 'phonetic_tokens',
             'extract_housenumber']

#: The inputs that are not names: the shapes the module's own comments say
#: it was built around.
EDGES = [None, '', '   ', '0', '12a', '12 a', '24937', 'Hauptstr. 5 Neuss',
         'Königsallee 12a', 'Müller & Söhne', 'Meyer', 'Maier', 'Schmitt',
         'Schmidt', 'Str', 'Straße', 'Pl.', 'Bad Segeberg 23795',
         'Sankt-Jürgen-Straße', 'A7', 'Æthelred', 'café', 'ÅSA']


def corpus() -> list[str]:
    return CORPUS.read_text().splitlines()


def expectations() -> dict:
    return json.loads(EXPECTED.read_text())


def jsonable(value):
    """Tuples come back from JSON as lists; compare in one shape."""
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


@pytest.mark.parametrize('name', FUNCTIONS)
def test_behaviour_over_the_corpus(name):
    expected = expectations()['corpus'][name]
    function = getattr(text, name)
    values = corpus()
    assert len(expected) == len(values), 'corpus and expectations are out of step'
    for value, want in zip(values, expected, strict=False):
        assert jsonable(function(value)) == want, f'{name}({value!r})'


@pytest.mark.parametrize('name', FUNCTIONS)
def test_behaviour_on_edges(name):
    expected = expectations()['edges'][name]
    function = getattr(text, name)
    for value, want in zip(EDGES, expected, strict=False):
        assert jsonable(function(value)) == want, f'{name}({value!r})'


def test_koelner_phonetik_over_the_corpus():
    expected = expectations()['koelner']
    for value, want in zip(corpus(), expected, strict=False):
        assert text.koelner_phonetik(text.normalize(value).replace(' ', '')) == want


def test_public_api_is_the_expected_set():
    public = {n for n in dir(text) if not n.startswith('_') and callable(getattr(text, n))}
    assert public == set(FUNCTIONS) | {'koelner_phonetik'}


def test_the_cases_the_module_exists_for():
    # Spelled out rather than left to the frozen table: these are the
    # reasons the module is not str.lower(), and they should read as
    # requirements.
    assert text.normalize('Müller') == 'mueller'          # not 'muller'
    assert text.normalize('Straße') == 'strasse'
    assert text.expand_street('Hauptstr.') == text.expand_street('Hauptstraße')
    assert text.phonetic('Meyer') == text.phonetic('Maier')
    assert text.phonetic('Schmitt') == text.phonetic('Schmidt')
    assert text.phonetic('Hauptstrasse') == text.phonetic('Haupt Strasse')
    assert text.extract_housenumber('Königsallee 12a') == (12, 'a')
    # A five-digit postcode must not be read as a house number.
    assert text.extract_housenumber('24937') is None
