"""What `web` calls, and what `manage.py` and the profilers call directly.

Three entry points -- `find`, `count`, `categories` -- and no HTTP
anywhere near them. A route translates a request body into `request.parse`
and a return value into JSON; everything between is here, so the same code
answers a query whether it arrived over HTTP, from a test, or from
`profile_search.py`.

The sequence is the same for every mode: parse (already done by the
caller), plan, execute, shape. The mode decides the plan; the relaxation
cascade runs for the phrase mode's LIKE rules and the name mode's fuzzy
fallback.
"""

from __future__ import annotations

import logging

from psycopg import sql
from psycopg.rows import dict_row

from lib import config, db, text, timing
from search import address as address_mode
from search import name as name_mode
from search import phrase as phrase_mode
from search import point as point_mode
from search import rank, shape
from search.request import Request, RequestError

log = logging.getLogger(__name__)

_cache = rank.ResultCache()


def schema() -> str:
    return db.active_schema()


def _statement(text: str) -> sql.Composed:
    """Fill the table placeholders with schema-qualified identifiers.

    The schema is an option and the one part of these statements that
    cannot be a bind parameter, so it reaches SQL as an identifier object
    rather than through an f-string. All three names are always supplied;
    `sql.SQL.format` ignores the ones a statement does not mention.
    """
    active = schema()
    return sql.SQL(text).format(
        objects=db.table(active, 'osm_search_object'),
        addresses=db.table(active, 'osm_search_address'),
        streets=db.table(active, 'osm_street'),
        terms=db.table(active, 'osm_category_term'),
    )


def _plan(req: Request) -> rank.Plan:
    if req.mode == 'name':
        return name_mode.plan(req)
    raise RequestError(f'mode {req.mode!r} has no single plan')


def check_fuzzy(req: Request) -> None:
    """Refuse what the fuzzy name search cannot take: it is the name mode's,
    and it compares letters, so it needs a text."""
    if req.mode != 'name':
        raise RequestError(f'the fuzzy search takes mode \'name\', not {req.mode!r}')
    # Normalised, as `fuzzy_plan` sees it: "!!!" is no text, and without one
    # the plan has no probes.
    if not text.expand_street(req.text):
        raise RequestError('the fuzzy search needs a text')


def find(req: Request, *, fuzzy: bool = False) -> dict:
    """A page of results for `req`; with `fuzzy`, of the fuzzy name search
    alone, without the exact name before it."""
    if fuzzy:
        check_fuzzy(req)
    call = 'fuzzy_find' if fuzzy else 'find'
    key = req.cache_key(call)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    steps = timing.Steps()
    body = _find_fuzzy(req, steps) if fuzzy else _find(req, steps)
    timing.report(log, steps, _what(call, req))
    _cache.set(key, body, _ttl(), _size())
    return body


def _find(req: Request, steps: timing.Steps) -> dict:
    if req.mode == 'point':
        return _find_point(req, steps)

    if req.mode == 'phrase':
        return _find_phrase(req, steps)

    if req.mode == 'address':
        return _find_address(req, steps)

    plan = _plan(req)
    w = rank.weights()
    if not plan.probes or req.relevance > w.relevance['name']:
        return shape.empty(req)

    statement = _statement(rank.build_sql(plan, req, count_only=False))
    params = rank.base_params(plan, req, w)

    with _connect() as conn:
        with steps.step('name'):
            rows = conn.execute(statement, {**params, 'min_score': w.min_score}).fetchall()
        steps.rows(len(rows))
        relevance = w.relevance['name']
        if not rows and _fuzzy_fallback(conn, plan, req, w):
            with steps.step('fuzzy'):
                rows = _fuzzy(conn, req, w)
            steps.rows(len(rows))
            relevance = w.relevance['name_fuzzy']
        return _name_page(conn, rows, relevance, req, steps)


def _find_fuzzy(req: Request, steps: timing.Steps) -> dict:
    w = rank.weights()
    if req.relevance > w.relevance['name_fuzzy']:
        return shape.empty(req)
    with _connect() as conn:
        with steps.step('fuzzy'):
            rows = _fuzzy(conn, req, w)
        steps.rows(len(rows))
        return _name_page(conn, rows, w.relevance['name_fuzzy'], req, steps)


def _name_page(conn, rows: list, relevance: int, req: Request, steps: timing.Steps) -> dict:
    """A page of name rows, all found at `relevance`, with their places."""
    for row in rows:
        row['relevance'] = relevance
    with steps.step('places'):
        places = _places(conn, rows, req.lang)
    features = [shape.feature(row, req.lang, places) for row in rows]
    total = int(rows[0]['total_count']) if rows else 0
    return shape.page(features, req=req, total=total)


def count(req: Request, *, fuzzy: bool = False) -> int:
    """The true total for a query, which a page's `total` already is.

    A separate call because it is the uncapped one: `find` stops at a page,
    this scores every candidate. It exists for a client that wants the
    number without the rows.

    Phrase mode has no uncapped form -- capped rules merged in Python
    have no window to count over -- so there it is the merged size, the
    same number `find` reports. With `fuzzy`, the fuzzy name search's
    total, as `find(fuzzy=True)` pages it.
    """
    if fuzzy:
        check_fuzzy(req)
    call = 'fuzzy_count' if fuzzy else 'count'
    key = req.cache_key(call)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    steps = timing.Steps()
    total = _count_fuzzy(req, steps) if fuzzy else _count(req, steps)
    timing.report(log, steps, _what(call, req))
    _cache.set(key, total, _ttl(), _size())
    return total


def _count(req: Request, steps: timing.Steps) -> int:
    if req.mode == 'point':
        return _find_point(req, steps)['total']

    if req.mode == 'phrase':
        return _find_phrase(req, steps)['total']

    if req.mode == 'address':
        found = address_mode.from_request(req)
        if found is None:
            return 0
        query, params = address_mode.build_sql([found], req, count_only=True)
        with _connect() as conn, steps.step('address'):
            return int(conn.execute(_statement(query), params).fetchone()['count'])

    plan = _plan(req)
    w = rank.weights()
    if not plan.probes or req.relevance > w.relevance['name']:
        return 0

    with _connect() as conn:
        with steps.step('name'):
            total = _exact_count(conn, plan, req, w)
        if total or not _fuzzy_fallback(conn, plan, req, w, exact_total=0):
            return total
        with steps.step('fuzzy'):
            return _fuzzy_count(conn, req, w)


def _count_fuzzy(req: Request, steps: timing.Steps) -> int:
    w = rank.weights()
    if req.relevance > w.relevance['name_fuzzy']:
        return 0
    with _connect() as conn, steps.step('fuzzy'):
        return _fuzzy_count(conn, req, w)


def _find_address(req: Request, steps: timing.Steps) -> dict:
    """The address mode: the request's parts, matched exactly."""
    found = address_mode.from_request(req)
    if found is None:
        return shape.empty(req)
    query, params = address_mode.build_sql([found], req, count_only=False)
    relevance = rank.weights().relevance['address']
    with _connect() as conn:
        with steps.step('address'):
            rows = conn.execute(_statement(query), params).fetchall()
        steps.rows(len(rows))
        for row in rows:
            row['relevance'] = relevance
        with steps.step('places'):
            places = _places(conn, rows, req.lang)
            objects = _objects(conn, rows)
    features = [shape.address_feature(row, req.lang, places, objects) for row in rows]
    total = int(rows[0]['total_count']) if rows else 0
    return shape.page(features, req=req, total=total)


def _find_phrase(req: Request, steps: timing.Steps) -> dict:
    """The phrase mode (search/phrase.py), on one connection: the parse, the
    rules and the page's places, rather than a connection each."""
    with _connect() as conn:
        merged, total, interpretation = phrase_mode.find(conn, _statement, req, steps)
        with steps.step('places'):
            places = _places(conn, merged, req.lang)
            objects = _objects(conn, [row for row in merged if 'reading' in row])

    features = [shape.address_feature(row, req.lang, places, objects) if 'reading' in row
                else shape.feature(row, req.lang, places)
                for row in merged]
    return shape.page(features, req=req, total=total, interpretation=interpretation)


def _find_point(req: Request, steps: timing.Steps) -> dict:
    """Everything at `near`: the nearest address, then what is near it,
    then the containing areas.

    Not paged and not scored. A click has no relevance ordering -- the
    order *is* the answer (the address that names the click, then nearest
    first, then the smallest containing area first), and a client shows all
    of it. `match_relevance` only tells the address apart: an address is
    `relevance.address`, everything else `relevance.point`.
    """
    lon, lat = req.near
    statement_params = point_mode.params(lon, lat, req.radius, req.categories, req.limit)
    with _connect() as conn:
        with steps.step('point'):
            rows = conn.execute(_statement(point_mode.sql(bool(req.categories))),
                                statement_params).fetchall()
        steps.rows(len(rows))
        address = None
        if req.with_address:
            with steps.step('address'):
                address = conn.execute(_statement(point_mode.ADDRESS_SQL),
                                       statement_params).fetchone()
        with steps.step('places'):
            places = _places(conn, [*rows, *([address] if address else [])], req.lang)
            objects = _objects(conn, [address] if address else [])

    total = int(rows[0]['total_count']) if rows else 0
    # The address stands for its object, so the object is not listed twice.
    if address is not None and address['id_object']:
        kept = [row for row in rows if row['id'] != address['id_object']]
        total -= len(rows) - len(kept)
        rows = kept
    w = rank.weights()
    for row in rows:
        row['relevance'] = w.relevance['point']
    features = [shape.feature(row, req.lang, places) for row in rows]
    if address is not None:
        address['relevance'] = w.relevance['address']
        feature = shape.address_feature(address, req.lang, places, objects)
        # `categories` narrows the address like everything else: it is what
        # its object or carrier is.
        ids = {c['id'] for c in feature['properties']['categories']}
        if not req.categories or ids & set(req.categories):
            features.insert(0, feature)
            total += 1
    return shape.page(features[:req.limit], req=req, total=total)


def categories(languages=None, icon=None) -> list:
    """The category tree, with names in every served language.

    Straight from `model/generated/categories.yaml` -- it is the same file the
    importer classified with, so what a client can filter by and what the
    rows actually carry cannot drift apart. `icon` maps a category id to its
    icon URL (`web/icons.py`), which only the web layer knows how to build.
    """
    if languages is None:
        languages = config.opt('languages') or ['de']
    return shape.tree(languages, icon)


def clear_cache() -> None:
    """Drop the response cache, for a caller that switches the schema
    (the tests)."""
    _cache.clear()


# --- plumbing ------------------------------------------------------------

def _what(call: str, req: Request) -> str:
    """How a timing line names a request: enough to run it again."""
    where = (f' area={req.area}' if req.area else f' bbox={req.bbox}' if req.bbox
             else f' near={req.near}' if req.mode == 'point' else '')
    return f'search {call} {req.mode} {req.text!r}{where}'


def _fuzzy_fallback(conn, plan: rank.Plan, req: Request, w: rank.Weights,
                    exact_total: int | None = None) -> bool:
    """Whether an empty exact name page falls back to the fuzzy name search.

    Only when the exact name has no rows at all: an empty page 3 of an
    exact name means its rows ran out, not that it was misspelled.
    """
    if not req.text or req.relevance > w.relevance['name_fuzzy']:
        return False
    if exact_total is None:
        exact_total = 0 if req.page == 0 else _exact_count(conn, plan, req, w)
    return exact_total == 0


def _fuzzy(conn, req: Request, w: rank.Weights) -> list:
    """The fuzzy name search's page, strict or, if strict finds nothing, relaxed.

    A later page is relaxed only if the strict pass has no rows at all, as
    page 0 was; `execute_with_relaxation` alone would run it strict.
    """
    plan = name_mode.fuzzy_plan(req)
    statement = _statement(rank.build_sql(plan, req, count_only=False))
    params = rank.base_params(plan, req, w)
    trgm, word = rank.trgm_thresholds(req.similarity, w)
    rows = rank.execute_with_relaxation(conn, statement, params, w, trgm, word, page=req.page)
    if rows or req.page == 0 or _fuzzy_count(conn, req, w, relax=False):
        return rows
    rank.set_thresholds(conn, w.relaxed_trgm_threshold, w.relaxed_word_threshold)
    return conn.execute(statement, {**params, 'min_score': w.relaxed_min_score}).fetchall()


def _fuzzy_count(conn, req: Request, w: rank.Weights, *, relax: bool = True) -> int:
    """`_fuzzy`'s total: the strict pass, and if it is empty the relaxed one."""
    plan = name_mode.fuzzy_plan(req)
    statement = _statement(rank.build_sql(plan, req, count_only=True))
    params = rank.base_params(plan, req, w)
    rank.set_thresholds(conn, *rank.trgm_thresholds(req.similarity, w))
    total = int(conn.execute(statement, {**params, 'min_score': w.min_score}).fetchone()['count'])
    if total or not relax:
        return total
    rank.set_thresholds(conn, w.relaxed_trgm_threshold, w.relaxed_word_threshold)
    return int(conn.execute(statement, {**params, 'min_score': w.relaxed_min_score})
               .fetchone()['count'])


def _exact_count(conn, plan: rank.Plan, req: Request, w: rank.Weights) -> int:
    statement = _statement(rank.build_sql(plan, req, count_only=True))
    params = {**rank.base_params(plan, req, w), 'min_score': w.min_score}
    return int(conn.execute(statement, params).fetchone()['count'])


def _places(conn, rows, lang: str) -> dict[int, dict]:
    ids = shape.place_ids(rows)
    if not ids:
        return {}
    return shape.place_table(
        conn.execute(_statement(shape.PLACES_SQL), {'ids': ids}).fetchall(), lang)


def _objects(conn, rows) -> dict[int, dict]:
    ids = shape.object_ids(rows)
    if not ids:
        return {}
    return {row['id']: row
            for row in conn.execute(_statement(shape.OBJECTS_SQL), {'ids': ids}).fetchall()}


def _connect():
    """A connection with a transaction, because `SET LOCAL` needs one.

    Not autocommit: the pg_trgm thresholds are set per statement with SET
    LOCAL, which outside a transaction applies to nothing and warns. The
    transaction is read-only in effect and is rolled back on close.
    """
    conn = db.connect()
    conn.row_factory = dict_row
    return conn


def _ttl() -> int:
    return int(config.opt('search.cache_ttl_s', 60))


def _size() -> int:
    return int(config.opt('search.cache_size', 512))
