"""The language of the texts a person reads, and the texts themselves.

A request picks its language with `?lang=`, one of the `languages` option;
without one, or with one not served, it gets the first of them. The language
is in the URL rather than taken from `Accept-Language` so that a page in each
language is its own URL: a link keeps its language, and a cache in front
needs no `Vary` to keep them apart.

The texts are in `messages.yaml` next to this module, one entry per message
id with a text per language.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from lib import config

MESSAGES_PATH = Path(__file__).resolve().parent / 'messages.yaml'


def languages() -> list[str]:
    """The `languages` option, less any the catalogue does not cover.

    A deployment may add a language for the category names before anyone
    has translated the texts; that language is then not offered here,
    rather than a page in it failing.
    """
    covered = set.intersection(*(set(texts) for texts in messages().values()))
    return [lang for lang in config.opt('languages') or ['de'] if lang in covered]


def pick(requested: str | None) -> str:
    """`requested` if it is served, else the default, the first served one."""
    served = languages()
    return requested if requested in served else served[0]


def switch_to(lang: str) -> dict[str, str]:
    """The languages a page in `lang` offers to switch to, each named in
    itself: a page's language switch shows only where it leads."""
    return {other: t('language.name', other) for other in languages() if other != lang}


@cache
def messages() -> dict[str, dict[str, str]]:
    return yaml.safe_load(MESSAGES_PATH.read_text(encoding='utf-8'))


def texts(prefix: str, lang: str) -> dict[str, str]:
    """Every text whose id starts with `prefix`, in `lang`, keyed by the rest
    of the id, placeholders unfilled: for a page's scripts to fill."""
    return {message_id.removeprefix(prefix): by_lang[lang]
            for message_id, by_lang in messages().items() if message_id.startswith(prefix)}


def t(message_id: str, lang: str, **values) -> str:
    """The text of `message_id` in `lang`, placeholders filled.

    A missing id or language is a KeyError, not a fallback: `test_i18n.py`
    checks the catalogue against `languages`, and a gap that slipped past it
    should show, not quietly turn the page half English.
    """
    text = messages()[message_id][lang]
    return text.format(**values) if values else text
