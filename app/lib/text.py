"""Text normalization and phonetics, shared by the importer and the query side.

Everything the matching engine compares is compared in *normalized* form:
the importer writes normalized columns into the search tables, and the
search module pushes the user's query through the very same functions
before binding it. That sharing is the point of this module -- a normalizer that
ran on only one of the two sides would silently stop matching (a query
folded to "muenchen" never finds a row still stored as "München").

Two normalizations are produced, for two different failure modes:

* **Letter form** (`normalize`) feeds trigram similarity, which is what
  catches ordinary typos -- transpositions, doubled or dropped letters.
* **Phonetic form** (`phonetic`) feeds a second, independent comparison
  that catches misspellings trigrams are bad at, where the user wrote what
  the word *sounds* like: "Schmitt"/"Schmidt", "Maier"/"Meyer",
  "Kaufhaus"/"Caufhaus". Trigram similarity of "Meyer"/"Maier" is 0.09 --
  effectively a non-match -- while both reduce to the same Kölner
  Phonetik code.

German-specific, because the data is: umlauts fold the way German
speakers actually type them when they lack the key (ä -> ae, not a), and
Kölner Phonetik is used rather than Soundex/Metaphone, which encode
English orthography and mangle German consonant clusters (sch, tz, pf).
"""

from __future__ import annotations

import re
import unicodedata

#: Folded the way a German keyboard-less user types them. Deliberately not
#: left to the NFKD pass below, which would strip the diaeresis and give
#: "a" -- so "Müller" would normalize to "muller" while a user typing
#: "mueller" got "mueller", and the two would not match.
_UMLAUTS = str.maketrans(
    {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
        'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue', 'ẞ': 'ss',
    }
)

_NON_ALNUM = re.compile(r'[^a-z0-9]+')
_WS = re.compile(r'\s+')

#: Street-type suffixes, in the spellings people actually type. German
#: street names are compounds ("Hauptstraße"), and the near-universal
#: abbreviation is to cut the compound short ("Hauptstr.", "Hauptstr"),
#: which leaves a trigram comparison against the full stored form weak.
#: Expanding both sides to one spelling makes them comparable again.
#: Applied as a *suffix* rule, since that is where these appear.
_SUFFIX_EXPANSIONS = (
    ('strasse', 'strasse'),
    ('strase', 'strasse'),
    ('stras', 'strasse'),
    ('str', 'strasse'),
    ('platz', 'platz'),
    ('pl', 'platz'),
    ('gasse', 'gasse'),
    ('weg', 'weg'),
    ('allee', 'allee'),
    ('al', 'allee'),
)

#: A suffix is only expanded when what precedes it is long enough to be a
#: real name stem. Without this, the bare word "str" (or a short name that
#: merely ends in those letters) would be rewritten into something the
#: user never typed.
_MIN_STEM = 3

#: A house number: up to four digits, optionally followed by a single
#: letter ("12a", "12 a"). Capped at four digits and bounded by a
#: non-digit on both sides so it cannot read a five-digit postcode as one.
#:
#: The trailing `(?![a-z\d])` is what stops the letter group from eating
#: the first letter of the *next word*: without it, "hauptstr 5 neuss"
#: parses as house number "5 n" and leaves "euss" behind to be matched
#: against street names. The letter only counts when nothing alphanumeric
#: follows it.
_HOUSENUMBER_RE = re.compile(r'(?<!\d)(\d{1,4})\s?([a-z])?(?![a-z\d])')


def normalize(value: str | None) -> str:
    """Fold `value` to the comparable letter form: lowercase, umlaut-folded,
    accent-stripped, punctuation reduced to single spaces.

    Returns '' for None/blank, so callers can store the result in a NOT
    NULL-ish column and compare without a null guard.
    """
    if not value:
        return ''

    folded = value.translate(_UMLAUTS).lower()

    # Anything still carrying a diacritic after the umlaut pass (é, ç, å --
    # real in OSM data even in a German extract) loses it here.
    decomposed = unicodedata.normalize('NFKD', folded)
    stripped = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))

    return _WS.sub(' ', _NON_ALNUM.sub(' ', stripped)).strip()


def expand_street(value: str | None) -> str:
    """`normalize`, plus street-suffix expansion on every token.

    Used for street names on both sides, so "Hauptstr." (typed) and
    "Hauptstraße" (stored) both become "hauptstrasse".
    """
    normalized = normalize(value)
    if not normalized:
        return ''

    return ' '.join(_expand_token(token) for token in normalized.split(' '))


def _expand_token(token: str) -> str:
    for suffix, expansion in _SUFFIX_EXPANSIONS:
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        # A token that is *only* the suffix ("strasse") is already the
        # expanded form; one with too short a stem is left alone.
        if not stem:
            return expansion
        if len(stem) >= _MIN_STEM:
            return stem + expansion
        return token
    return token


def phonetic(value: str | None) -> str:
    """The Kölner Phonetik code of `value`, computed over the whole string
    with spaces removed.

    Dropping the spaces is deliberate and does real work: German compounds
    are written closed ("Hauptstrasse") but typed open often enough
    ("Haupt Strasse"), and coding the joined string makes those two
    identical rather than merely similar. It also means the code of a
    multi-word name is one comparable token instead of a word list whose
    order would have to match.
    """
    return koelner_phonetik(normalize(value).replace(' ', ''))


def phonetic_tokens(value: str | None) -> list[str]:
    """Phonetic codes to compare a query against: one per word, plus the
    code of the whole string joined.

    A single code for a multi-word query is too blunt. "Rathaus Neuss"
    codes as one string that matches neither a row named "Rathaus" nor one
    named "Neuss", even though it names both. Scoring against the *best*
    of the per-word codes finds either, while the joined code still
    handles the compound the user split ("Haupt Strasse").

    Deduplicated and empty-code-free, so the array can go straight into an
    `= ANY(...)` probe.
    """
    normalized = normalize(value)
    if not normalized:
        return []

    words = normalized.split(' ')
    codes = [koelner_phonetik(word) for word in words]
    if len(words) > 1:
        codes.append(koelner_phonetik(normalized.replace(' ', '')))

    seen: list[str] = []
    for code in codes:
        if code and code not in seen:
            seen.append(code)
    return seen


def koelner_phonetik(word: str) -> str:
    """Kölner Phonetik (Postel 1969) of an already-normalized ASCII word.

    Maps each letter to a digit by its sound, then collapses repeats and
    drops the vowel code except in leading position. Two spellings that
    sound alike in German share a code.

    Expects `normalize`d input (lowercase ASCII); anything else is ignored
    character by character rather than raising, because this runs over
    every row of an OSM import and one odd character must not stop it.
    """
    letters = [ch for ch in word.upper() if 'A' <= ch <= 'Z']
    if not letters:
        return ''

    codes: list[str] = []
    length = len(letters)

    for i, ch in enumerate(letters):
        # A sentinel rather than '' -- an empty string is `in` every
        # string, so `nxt in 'CSZ'` would be true at the end of the word
        # and silently code the last D/T as 8 instead of 2.
        nxt = letters[i + 1] if i + 1 < length else '#'
        prv = letters[i - 1] if i > 0 else '#'

        if ch in 'AEIJOUY':
            codes.append('0')
        elif ch == 'H':
            # The one letter with no code at all: it only ever modifies
            # the letter before it, which that letter's own rule handles.
            continue
        elif ch == 'B':
            codes.append('1')
        elif ch == 'P':
            codes.append('3' if nxt == 'H' else '1')
        elif ch in 'DT':
            codes.append('8' if nxt in 'CSZ' else '2')
        elif ch in 'FVW':
            codes.append('3')
        elif ch in 'GKQ':
            codes.append('4')
        elif ch == 'C':
            if i == 0:
                codes.append('4' if nxt in 'AHKLOQRUX' else '8')
            elif prv in 'SZ':
                codes.append('8')
            else:
                codes.append('4' if nxt in 'AHKOQUX' else '8')
        elif ch == 'X':
            # "x" is /ks/: two codes, unless the k-sound is already
            # spelled out by the letter before it.
            if prv not in 'CKQ':
                codes.append('4')
            codes.append('8')
        elif ch == 'L':
            codes.append('5')
        elif ch in 'MN':
            codes.append('6')
        elif ch == 'R':
            codes.append('7')
        elif ch in 'SZ':
            codes.append('8')

    collapsed: list[str] = []
    for code in codes:
        if not collapsed or collapsed[-1] != code:
            collapsed.append(code)

    # '0' survives only in first position: interior vowels carry no
    # distinguishing information in this scheme.
    return ''.join(collapsed[:1] + [c for c in collapsed[1:] if c != '0'])


def extract_housenumber(value: str | None) -> tuple[int, str | None] | None:
    """The first house number in `value` as `(number, letter)`, or None.

    Skips a five-digit postcode: `_HOUSENUMBER_RE` caps the digit run at
    four, so "40210" cannot be read as house number 4021.
    """
    if not value:
        return None
    match = _HOUSENUMBER_RE.search(normalize(value))
    if not match:
        return None
    return int(match.group(1)), match.group(2)
