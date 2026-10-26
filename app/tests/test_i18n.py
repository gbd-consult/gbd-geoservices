"""The catalogue of texts a person reads, and how a request picks a language."""

from __future__ import annotations

import re

import yaml

from lib import config, i18n


def test_every_text_has_every_default_language():
    """A gap shows as a KeyError on the page that uses it, not here, unless
    this checks it. Against the versioned defaults: a deployment may serve
    fewer languages, and one it adds without texts is not offered at all."""
    defaults = yaml.safe_load(config.DEFAULTS_PATH.read_text())['languages']
    for message_id, texts in i18n.messages().items():
        missing = [lang for lang in defaults if not texts.get(lang)]
        assert not missing, f'{message_id}: no text in {", ".join(missing)}'


def test_a_text_has_the_same_placeholders_in_every_language():
    """`t()` fills by name; a placeholder renamed in one language only raises
    for that language alone."""
    for message_id, texts in i18n.messages().items():
        names = {lang: set(re.findall(r'\{(\w+)\}', text)) for lang, text in texts.items()}
        assert len({frozenset(n) for n in names.values()}) == 1, f'{message_id}: {names}'


def test_without_lang_the_first_served_language_is_used(monkeypatch):
    monkeypatch.setitem(config.load(), 'languages', ['de', 'en'])
    assert i18n.pick(None) == 'de'
    assert i18n.pick('en') == 'en'


def test_an_unserved_language_falls_back_to_the_default(monkeypatch):
    monkeypatch.setitem(config.load(), 'languages', ['en', 'de'])
    assert i18n.pick('fr') == 'en'


def test_a_language_without_texts_is_not_offered(monkeypatch):
    """`languages` also names the category languages; adding one there must
    not make `?lang=` serve a page that fails on its first text."""
    monkeypatch.setitem(config.load(), 'languages', ['de', 'xx', 'en'])
    assert i18n.languages() == ['de', 'en']
    assert i18n.pick('xx') == 'de'
