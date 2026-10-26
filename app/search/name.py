"""The name mode: a name, optionally narrowed to a list of categories.

`plan` is the name mode itself: the query, normalised the way the importer
normalised `search_name` (case, umlauts, "Str."), compared by equality --
one btree probe. No similarity, no fragments, no phonetic codes.

`fuzzy_plan` is the fuzzy name search -- letter similarity, the query as a
fragment, phonetic codes -- for the name mode's fallback when the exact
name finds nothing (`api._fuzzy`) and the phrase rules that use it (`name
LIKE`). There `categories && ARRAY[...]` narrows the *candidates* rather
than filtering the scored set: it is a GIN index lookup, so combining it
with the trigram probe lets Postgres BitmapAnd the two and read far fewer
rows than either alone.

A request with categories and no text is the category browse, in both.
"""

from __future__ import annotations

from lib import text
from search import rank

#: The category narrowing, as a candidate probe. `&&` (overlap) rather than
#: `@>` (contains): the caller sends a list meaning "any of these", and
#: parents work without a tree walk because the importer stored every
#: ancestor on the row.
CATEGORY_PROBE = 'o.categories && %(q_categories)s'


#: The name mode's one text probe.
EXACT_PROBE = 'o.search_name = %(q_name)s'


def plan(req) -> rank.Plan:
    """Plan the name mode: the normalised name, exactly."""
    q_name = text.expand_street(req.text)
    categories = list(req.categories)
    probes = [EXACT_PROBE] if q_name else []
    if categories and probes:
        probes = [f'{EXACT_PROBE} AND {CATEGORY_PROBE}']
    elif categories:
        probes = [CATEGORY_PROBE]
    return rank.Plan(
        probes=tuple(probes),
        score=f'1.0 + {rank.inside_view_term(req.spatial)}',
        params={'q_name': q_name, 'q_categories': categories},
    )


def fuzzy_plan(req, *, narrowed: bool = False) -> rank.Plan:
    """Plan a fuzzy name search, for the phrase LIKE rules.

    `narrowed` says the caller ANDs a selective condition of its own into
    every probe (the place of `name_like_in_place`); a category does the same.

    The text probes go against `search_name`, not `search_text`.
    search_text carries each row's city, so probing it for a bare city name
    matches every row in that city -- measured at 440 ms of a 550 ms
    query. search_text is still *scored* below: ranking wants the city
    context, finding candidates does not.
    """
    q_name = text.expand_street(req.text)
    # Coded from the expanded query, to match how the importer codes the
    # expanded stored value (importer.features.search_row).
    q_phon = text.phonetic(q_name)
    q_phon_tokens = text.phonetic_tokens(q_name)
    categories = list(req.categories)

    params = {
        'q_name': q_name,
        'q_phon': q_phon,
        'q_phon_tokens': q_phon_tokens,
        'q_prefix': q_name + '%',
        'q_categories': categories,
    }

    probes: list[str] = []
    if q_name:
        probes += [
            # Whole-name letter similarity: the typo channel.
            'o.search_name %% %(q_name)s',
            # The query as a *fragment* of a name -- what makes a
            # half-typed "Hauptbahn" (or a two-letter prefix, below any
            # whole-string similarity threshold) find "Hauptbahnhof".
            '%(q_name)s <%% o.search_name',
        ]
        if q_phon_tokens:
            # Exact phonetic hits: a btree `= ANY(...)` lookup, the
            # cheapest probe here, and the one that answers "Maier" for
            # "Meyer" outright rather than by degrees.
            probes.append('o.phon_name = ANY(%(q_phon_tokens)s)')
        if q_phon and (narrowed or categories):
            # Near-miss codes -- a typo bad enough to change the code.
            # Only where something else narrows the probe: codes are digit
            # strings, whose trigrams hardly discriminate, so on de
            # `phon_name %% code` returned 90 k to 844 k index candidates
            # for codes of 2 to 7 digits, each a heap page to recheck --
            # 16 s of the 23 s "kita dormagen"'s whole-country step took
            # from a cold cache.
            probes.append('o.phon_name %% %(q_phon)s')

    if categories and probes:
        # ANDed into every text probe rather than added as a branch of its
        # own: as a branch it would *widen* the candidate set to every
        # object in the category, which for `amenity` is most of the table.
        probes = [f'({probe}) AND {CATEGORY_PROBE}' for probe in probes]
    elif categories:
        # The category browse: no text to probe with, so the category is
        # the probe.
        probes = [CATEGORY_PROBE]

    return rank.Plan(
        probes=tuple(probes),
        score=score(has_phonetic=bool(q_phon_tokens), req=req, has_text=bool(q_name)),
        params=params,
    )


def score(*, has_phonetic: bool, req, has_text: bool) -> str:
    """The row's relevance.

    A browse has nothing to compare text against, so the three text
    channels would all be 0 and every row would fall below `min_score`.
    There the ranking is importance and, if the request gave a point,
    distance -- which is what "show me the restaurants here" means.
    """
    if not has_text:
        return f'1.0 + {rank.inside_view_term(req.spatial)}'
    return rank.name_score(has_phonetic=has_phonetic, spatial=req.spatial)
