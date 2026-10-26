"""The phrase mode: free-form text, any mix of name, category, place, street
and address.

The design is a refusal to parse. "restaurant Kiel" and "restaurant Maxim"
have the same shape and mean different things, and nothing in the string
says which. So the parser does not decide: it produces every reading the
dictionaries support, and the rules of model/search_rules.yaml
(search/rules.py) are matched against them. Nominatim and Photon take the
same approach for the same reason.

STEPS

The rules come in steps. A step runs every rule on every reading that has
exactly the rule's parts; the first step that returns rows is the answer,
and the steps below it are not run. Steps rather than single rules:
"restaurant Kiel" is also a name ("Restaurant ...") in a place, and
stopping at the first rule with rows would lose the restaurants in Kiel
that are not called that.

PARSING ONLY WHEN IT IS NEEDED

Step 1 reads the whole query as it stands (`query.text`): a name, or a
category term. Most queries are one of the two, and they cost one probe
each. The full parse -- the address readings, then every span of the query
offered at once to the category terms, the places and the streets, one
btree probe each -- runs only when step 1 found nothing.

WHAT `total` MEANS HERE

Each rule is capped, the results are merged in Python, and `total` is the
size of that merged set. It is not the true number of matching rows the way
the name mode's is -- there is no single statement to take a window count
over -- and a phrase query that would match ten thousand objects reports
the cap. Paging is over the merged list, so it is consistent within a
query; `/count` on a phrase is the same number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lib import text
from search import address as address_mode
from search import place as place_mode
from search import rank, rules
from search.rules import Place, Reading, Rule

#: Rows fetched per rule before the merge. Generous enough that paging a
#: few pages deep stays exact, small enough that a step of them is cheap.
RULE_LIMIT = 200

#: Dropped between the parts of a reading. Small and closed on purpose: a
#: stop-word list that grows starts eating names.
STOP_WORDS = frozenset({
    'in', 'im', 'am', 'an', 'auf', 'bei', 'beim', 'zu', 'zur', 'zum',
    'der', 'die', 'das', 'den', 'dem', 'nahe', 'near', 'at', 'the',
})

#: Among the categories a term names, the query's language first, then the
#: shallowest: it holds the others, since a row stores its categories with
#: every ancestor.
TERM_LOOKUP = """
    SELECT DISTINCT ON (term) term, category
    FROM {terms}
    WHERE term = ANY(%(spans)s)
    ORDER BY term, (lang = %(lang)s) DESC,
             length(category) - length(replace(category, '_', '')) ASC, category ASC
"""

#: Every place object named like a span, grouped by name, so "Neustadt" is
#: all of the Neustadts. `ids` are the ones with a border, which is what an
#: address path holds; `area_ids` those of them that are no administrative
#: area, which no path holds; `points` the ones without a border, except a
#: node inside a border of its own name -- Kiel's node would otherwise add
#: everything within 10 km of it.
PLACE_LOOKUP = """
    SELECT p.search_name,
           (array_agg(p.name ORDER BY p.has_polygon DESC, p.id))[1] AS name,
           (array_agg(p.lon ORDER BY p.has_polygon DESC, p.id))[1] AS lon,
           (array_agg(p.lat ORDER BY p.has_polygon DESC, p.id))[1] AS lat,
           coalesce(array_agg(p.id ORDER BY p.id) FILTER (WHERE p.has_polygon), '{{}}') AS ids,
           coalesce(array_agg(p.id ORDER BY p.id) FILTER (WHERE p.has_polygon AND NOT p.admin),
                    '{{}}') AS area_ids,
           coalesce(array_agg(json_build_array(p.lon, p.lat, p.class) ORDER BY p.id)
                    FILTER (WHERE p.loose), '{{}}') AS points
    FROM (
        SELECT o.id, o.name, o.search_name, o.class,
               ST_X(o.geom_center) AS lon, ST_Y(o.geom_center) AS lat,
               o.geom_polygon IS NOT NULL AS has_polygon,
               o.categories && %(admin_categories)s AS admin,
               o.geom_polygon IS NULL AND NOT EXISTS (
                   SELECT 1 FROM {objects} b
                   WHERE b.search_name = o.search_name
                     AND b.categories && %(place_categories)s
                     AND b.geom_polygon IS NOT NULL
                     AND ST_Covers(b.geom_polygon, o.geom_center)) AS loose
        FROM {objects} o
        WHERE o.search_name = ANY(%(spans)s)
          AND o.categories && %(place_categories)s
    ) p
    GROUP BY p.search_name
"""

ADMIN_CATEGORIES = ['cat_geography_admin']

STREET_LOOKUP = 'SELECT search_street FROM {streets} WHERE search_street = ANY(%(spans)s)'


@dataclass(frozen=True, slots=True)
class Run:
    """One rule run on one reading, and what it found."""

    rule: Rule
    reading: Reading
    rows: list
    relevance: int


def tokens_of(query: str) -> list[str]:
    return [t for t in text.normalize(query).split(' ') if t]


def parse_address(query: str) -> list[address_mode.Address]:
    """Every reading of the query as a full address, for the address rules.

    Two orders, and a postcode or city is required in both: "Hauptstraße
    5" alone is every Hauptstraße 5 there is, which the address mode
    answers when asked and the phrase mode does not guess at.

    - street, number, then postcode, city or both: "Holtenauer Straße 12
      24105 Kiel". Every number in the query is tried as the house number,
      so a street with one in its name ("Straße des 17. Juni") still reads.
    - city, street, number: "Kiel Holtenauer Straße 12". Where the city
      ends and the street begins is not in the string, so every split is a
      reading; the matcher keeps the ones the data has.

    No dictionary probe here: a reading is only a candidate, and the exact
    match against the address table is what decides.
    """
    tokens = [t for t in text.normalize(query).split(' ') if t]
    readings: list[address_mode.Address] = []

    for i in range(1, len(tokens)):
        number = _housenumber(tokens, i)
        if number is None:
            continue
        value, part, end = number
        street = tokens[:i]
        if any(_is_postcode(t) for t in street):
            continue

        rest = [t for t in tokens[end:] if t not in STOP_WORDS]
        postcodes = [t for t in rest if _is_postcode(t)]
        city = [t for t in rest if not _is_postcode(t)]
        if rest and len(postcodes) <= 1 and all(t.isalpha() for t in city):
            readings.append(address_mode.Address(
                street=text.expand_street(' '.join(street)), number=value, number_part=part,
                postcode=postcodes[0] if postcodes else None, city=' '.join(city) or None))

        if end == len(tokens) and all(t.isalpha() for t in street):
            for k in range(1, len(street)):
                readings.append(address_mode.Address(
                    street=text.expand_street(' '.join(street[k:])), number=value,
                    number_part=part, city=' '.join(street[:k])))

    return list(dict.fromkeys(readings))


def _is_postcode(token: str) -> bool:
    """A German postcode, as `lib.text` reads one."""
    return re.fullmatch(r'\d{5}', token) is not None


def _housenumber(tokens: list[str], i: int) -> tuple[int, str | None, int] | None:
    """The house number at `tokens[i]` -- "12", "12a" or "12 a" -- as
    (number, letter, index after it), or None."""
    match = re.fullmatch(r'(\d{1,4})([a-z])?', tokens[i])
    if match is None:
        return None
    number, part = int(match.group(1)), match.group(2)
    end = i + 1
    if part is None and end < len(tokens) and re.fullmatch(r'[a-z]', tokens[end]):
        part, end = tokens[end], end + 1
    return number, part, end


def spans(tokens: list[str]) -> list[tuple[int, int, str]]:
    """Every contiguous run of tokens, longest first, as (start, end, text).

    A query has two to four tokens, so this is at most ten strings and one
    `= ANY(...)` probe -- which is why longest-match costs nothing.
    """
    return [(start, start + length, ' '.join(tokens[start:start + length]))
            for length in range(len(tokens), 0, -1)
            for start in range(0, len(tokens) - length + 1)]


def read_text(conn, statement, query: str, lang: str = 'de') -> Reading:
    """Step 1's reading: the whole query, and the category it is a term for."""
    whole = ' '.join(tokens_of(query))
    category = None
    if whole:
        row = conn.execute(statement(TERM_LOOKUP), {'spans': [whole], 'lang': lang}).fetchone()
        category = row['category'] if row else None
    return Reading(text=whole, category=category, term=whole if category else None)


def parse(conn, statement, query: str, lang: str = 'de') -> tuple[Reading, ...]:
    """Every reading of the query the dictionaries support.

    One address reading, holding every way the query reads as an address,
    if it does; then every combination of a category term, a place at
    either end and a street, the rest of the query as the name, with two
    parts at least -- no rule after step 1 takes fewer.
    """
    tokens = tokens_of(query)
    whole = ' '.join(tokens)
    out: list[Reading] = []
    addresses = tuple(parse_address(query))
    if addresses:
        out.append(Reading(text=whole, addresses=addresses))
    if len(tokens) < 2:
        return tuple(out)

    # The whole query is step 1's; a part is always less than all of it.
    indexed = [(s, e, span) for s, e, span in spans(tokens) if e - s < len(tokens)]
    categories = _categories(conn, statement, indexed, lang)
    places = _places(conn, statement, [(s, e, span) for s, e, span in indexed
                                       if s == 0 or e == len(tokens)])
    streets = _streets(conn, statement, indexed)

    seen = set()
    for category in [None, *categories]:
        for place in [None, *places]:
            for street in [None, *streets]:
                used = [part for part in (category, place, street) if part]
                covered = [i for s, e, *_ in used for i in range(s, e)]
                if len(covered) != len(set(covered)):
                    continue
                rest = [i for i in range(len(tokens))
                        if i not in covered and tokens[i] not in STOP_WORDS]
                # Not when the rest is a place: "restaurant Kiel" is not a
                # restaurant named like Kiel, and read so it would find one
                # by its fragments.
                if category and not place and any(rest == list(range(s, e)) for s, e, _ in places):
                    continue
                reading = Reading(
                    text=whole,
                    name=' '.join(tokens[i] for i in rest) or None,
                    category=category[3] if category else None,
                    term=category[2] if category else None,
                    place=place[2] if place else None,
                    street=street[2] if street else None,
                )
                key = (reading.name, reading.category, place and place[:2], reading.street)
                if len(reading.parts) >= 2 and key not in seen:
                    seen.add(key)
                    out.append(reading)
    return tuple(out)


def _categories(conn, statement, indexed, lang) -> list[tuple[int, int, str, str]]:
    """The spans that are category terms, as (start, end, term, category).

    Only the longest: "italienisches restaurant" is one term, not
    "restaurant" with "italienisches" left over as a name.
    """
    rows = conn.execute(statement(TERM_LOOKUP),
                        {'spans': [span for *_, span in indexed], 'lang': lang}).fetchall()
    found = {row['term']: row['category'] for row in rows}
    hits = [(s, e, span, found[span]) for s, e, span in indexed if span in found]
    return [hit for hit in hits
            if not any(o[0] <= hit[0] and hit[1] <= o[1] and o[:2] != hit[:2] for o in hits)]


def _places(conn, statement, indexed) -> list[tuple[int, int, Place]]:
    """The spans at either end that name a place, as (start, end, place)."""
    names = {text.expand_street(span) for *_, span in indexed}
    rows = conn.execute(statement(PLACE_LOOKUP), {
        'spans': sorted(names),
        'place_categories': list(place_mode.PLACE_CATEGORIES),
        'admin_categories': ADMIN_CATEGORIES,
    }).fetchall()
    found = {}
    for row in rows:
        found[row['search_name']] = Place(
            name=row['name'], ids=tuple(row['ids']), area_ids=tuple(row['area_ids']),
            points=tuple((lon, lat, place_mode.radius_for(cls)) for lon, lat, cls in row['points']),
            centre=(row['lon'], row['lat']))
    return [(s, e, found[text.expand_street(span)]) for s, e, span in indexed
            if text.expand_street(span) in found]


def _streets(conn, statement, indexed) -> list[tuple[int, int, str]]:
    """The spans that name a street, as (start, end, normalised street)."""
    names = {text.expand_street(span) for *_, span in indexed}
    rows = conn.execute(statement(STREET_LOOKUP), {'spans': sorted(names)}).fetchall()
    found = {row['search_street'] for row in rows}
    return [(s, e, text.expand_street(span)) for s, e, span in indexed
            if text.expand_street(span) in found]


# --- running the steps ---------------------------------------------------

def find(conn, statement, req, steps) -> tuple[list, int, list]:
    """The phrase search: the steps in order until one finds something.

    Returns the page of rows, the merged total and the interpretation.
    """
    w = rank.weights()
    whole: Reading | None = None
    parsed: tuple[Reading, ...] | None = None
    runs: list[Run] = []

    for step in rules.steps():
        if not step.enabled or step.relevance < req.relevance:
            continue
        found = False
        for rule in step.rules:
            # An address has no category, so a category filter would drop it.
            if rule.on_addresses and req.categories:
                continue
            if rule.on_text:
                if whole is None:
                    with steps.step('text'):
                        whole = read_text(conn, statement, req.text, req.lang)
                readings = [whole] if _fits_text(rule, whole) else []
            else:
                if parsed is None:
                    with steps.step('parse'):
                        parsed = parse(conn, statement, req.text, req.lang)
                readings = [r for r in parsed
                            if (bool(r.addresses) if rule.on_addresses else rule.parts == r.parts)]
            for reading in readings:
                with steps.step(rule.id):
                    rows = _run(conn, statement, rule, reading, req, w)
                steps.rows(len(rows))
                if req.categories and not rule.on_addresses:
                    # The rules read categories of their own; the request's
                    # filter applies to what they found.
                    rows = [row for row in rows
                            if set(req.categories) & set(row['categories'] or ())]
                runs.append(Run(rule, reading, rows, step.relevance))
                found = found or bool(rows)
        if found:
            break

    merged, total = merge(runs, req.limit, req.offset)
    return merged, total, interpretations(runs)


def _fits_text(rule: Rule, whole: Reading) -> bool:
    if not whole.text:
        return False
    return whole.category is not None or not any(a.prop == 'category' for a in rule.atoms)


def _run(conn, statement, rule: Rule, reading: Reading, req, w: rank.Weights) -> list:
    trgm, word = rank.trgm_thresholds(req.similarity, w)
    if rule.on_addresses:
        if rule.street_like:
            rank.set_thresholds(conn, trgm, word)
        query, params = address_mode.build_sql(list(reading.addresses), req, count_only=False,
                                               limit=RULE_LIMIT, street_like=rule.street_like)
        return conn.execute(statement(query), params).fetchall()

    compiled = rules.compile_rule(rule, reading, req, RULE_LIMIT, w)
    if compiled is None:
        return []
    sql = statement(rank.build_sql(compiled.plan, compiled.req, count_only=False))
    params = rank.base_params(compiled.plan, compiled.req, w)
    if compiled.relax:
        return rank.execute_with_relaxation(conn, sql, params, w, trgm, word, page=0)
    if rule.like:
        rank.set_thresholds(conn, trgm, word)
    rows = conn.execute(sql, {**params, 'min_score': compiled.min_score}).fetchall()
    if rule.like and rows:
        # Strict, so cut relative to the best row as well (parameters.yaml).
        floor = w.phrase_strict_best_share * max(row['match'] for row in rows)
        rows = [row for row in rows if row['match'] >= floor]
    return rows


def merge(runs: list[Run], limit: int, offset: int) -> tuple[list, int]:
    """One list, in the order the rules ran, each rule's own order kept.

    A row found by more than one rule appears once, under the first.
    Address rows and object rows come from two tables whose ids overlap,
    so they are told apart by table as well as id.
    """
    seen = set()
    out = []
    for run in runs:
        for row in run.rows:
            key = ('address' if 'reading' in row else 'object', row['id'])
            if key in seen:
                continue
            seen.add(key)
            out.append({**row, 'rule': run.rule.id, 'relevance': run.relevance})
    return out[offset:offset + limit], len(out)


def interpretations(runs: list[Run]) -> list[dict]:
    """Every rule that ran, on which reading, and how many rows it found.

    A phrase search that returns the wrong thing is unexplainable without
    it: the user sees a list and cannot tell whether "Kiel" was read as a
    place, a name, or neither.
    """
    out = []
    for run in runs:
        entry = {'rule': run.rule.id, 'where': run.rule.source, 'rows': len(run.rows)}
        if run.rule.on_addresses:
            matched = dict.fromkeys(run.reading.addresses[row['reading']] for row in run.rows)
            entry['addresses'] = [a.as_dict() for a in matched]
        elif run.rule.on_text:
            entry['text'] = run.reading.text
            if run.reading.category is not None:
                entry['category'] = run.reading.category
        else:
            entry.update(run.reading.bindings())
        out.append(entry)
    return out
