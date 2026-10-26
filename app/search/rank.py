"""The ranking engine: scoring expressions, thresholds, the relaxation cascade.

Three independent channels, combined into one score, because a user who
mistypes fails each of them differently:

1. **Letter similarity** (pg_trgm `similarity`). Transposed, doubled or
   dropped letters -- "Koenigsalle" still finds "Königsallee".
2. **Word similarity** (pg_trgm `<%`). A query that is a *fragment* of the
   stored text rather than a misspelling of the whole of it. Plain
   similarity punishes length differences badly enough that "Rathaus"
   scores ~0.25 against "rathaus marktplatz duesseldorf"; word similarity
   scores it 1.0.
3. **Phonetics** (Kölner Phonetik, precomputed at import). What the other
   two are worst at, where the user wrote what the word sounds like:
   trigram similarity of "Meyer"/"Maier" is 0.09, both reduce to the same
   code.

**The weights are bound, not interpolated.** A weight written into the SQL
text as `0.40 * similarity(...)` lets `parameters.yaml` and the running
query disagree with nothing to say so. They are `%(w_*)s` parameters
here, read from `model/parameters.yaml`, which is then the only place a
weight exists. psycopg binds client-side, so the value still reaches the
server as a literal and the plan is the same one; the gain is
configuration, not plan reuse.

**Distance goes through `geography`.** `geom_center <-> :pt` on a 4326
geometry returns *degrees*, and at 54° N a degree of longitude is 0.59 of
one of latitude, so the ordering is anisotropically wrong rather than
merely mis-scaled. The importer built a functional GiST on
`(geom_center::geography)` for exactly this, so the cast is still a KNN
index scan.

NOTE ON `%`: psycopg binds with `%(name)s`, so pg_trgm's `%` and `<%`
operators are written `%%` and `<%%` in every SQL string here. A single one
raises at execute time rather than doing something subtle, and
`test_rank.py` checks the module's own SQL for it.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class Weights:
    """`ranking` from model/parameters.yaml, as the query binds it."""

    # name mode
    similarity: float
    word_similarity: float
    phonetic: float
    exact_bonus: float
    prefix_bonus: float
    # shared
    min_score: float
    relaxed_min_score: float
    relaxed_trgm_threshold: float
    relaxed_word_threshold: float
    trgm_range: tuple[float, float]
    word_offset: float
    word_range: tuple[float, float]
    phrase_strict_min_score: float
    phrase_strict_best_share: float
    inside_view_bonus: float
    importance_weight: float
    relevance: dict

    @classmethod
    def from_dict(cls, values: dict) -> Weights:
        name = values['name']
        return cls(
            similarity=float(name['similarity']),
            word_similarity=float(name['word_similarity']),
            phonetic=float(name['phonetic']),
            exact_bonus=float(name['exact_bonus']),
            prefix_bonus=float(name['prefix_bonus']),
            min_score=float(values['min_score']),
            relaxed_min_score=float(values['relaxed_min_score']),
            relaxed_trgm_threshold=float(values['relaxed_trgm_threshold']),
            relaxed_word_threshold=float(values['relaxed_word_threshold']),
            trgm_range=tuple(float(v) for v in values['trgm_range']),
            word_offset=float(values['word_offset']),
            word_range=tuple(float(v) for v in values['word_range']),
            phrase_strict_min_score=float(values['phrase_strict_min_score']),
            phrase_strict_best_share=float(values['phrase_strict_best_share']),
            inside_view_bonus=float(values['inside_view_bonus']),
            importance_weight=float(values['importance_weight']),
            relevance={key: int(value) for key, value in values['relevance'].items()},
        )

    def params(self) -> dict:
        """The weights as bind parameters, for any query that scores."""
        return {
            'w_similarity': self.similarity,
            'w_word_similarity': self.word_similarity,
            'w_phonetic': self.phonetic,
            'w_exact': self.exact_bonus,
            'w_prefix': self.prefix_bonus,
            'w_inside': self.inside_view_bonus,
            'w_importance': self.importance_weight,
            **{f'rel_{key}': value for key, value in self.relevance.items()},
        }


_weights: Weights | None = None


def weights(model_dir: Path | None = None) -> Weights:
    """The ranking weights, read once.

    Search does not need `styles/`, so this reads `parameters.yaml`
    directly rather than going through `importer.params.Params`, which
    requires the style files to build a label-zoom table search never asks
    about.
    """
    global _weights
    if _weights is None or model_dir is not None:
        directory = model_dir or _default_model_dir()
        values = yaml.safe_load((directory / 'parameters.yaml').read_text())['ranking']
        loaded = Weights.from_dict(values)
        if model_dir is None:
            _weights = loaded
        return loaded
    return _weights


def _default_model_dir() -> Path:
    from importer.run import MODEL
    return MODEL


# --- thresholds ----------------------------------------------------------

def trgm_thresholds(similarity: int, w: Weights) -> tuple[float, float]:
    """Map `similarity` (1-10) onto (similarity_threshold, word_similarity_threshold)."""
    level = min(10, max(1, similarity))
    low, high = w.trgm_range
    span = (high - low) / 9
    trgm = low + (level - 1) * span
    word_low, word_high = w.word_range
    word = min(word_high, max(word_low, trgm + w.word_offset))
    return round(trgm, 4), round(word, 4)


def set_thresholds(conn, trgm: float, word: float) -> None:
    """Apply the pg_trgm thresholds for this request.

    SET LOCAL, so the values live exactly as long as the transaction and
    cannot leak onto the next request that borrows this connection.
    Formatted rather than bound because SET takes no parameters; the values
    are floats this module computed, never anything from the request.
    """
    conn.execute(f'SET LOCAL pg_trgm.similarity_threshold = {trgm:.4f}')
    conn.execute(f'SET LOCAL pg_trgm.word_similarity_threshold = {word:.4f}')


# --- score expressions ---------------------------------------------------

def phonetic_term(column: str, param: str, enabled: bool) -> str:
    """The phonetic channel: the best match against any of the query's codes.

    An exact code match scores 1.0 outright rather than going through
    similarity(): two equal codes are the strongest signal this channel
    has, and trigram similarity understates it badly on strings this short
    ("0678" vs "0687" scores 0.25 despite being a near miss).

    The max() over `unnest` is what lets a query name two things at once
    ("Rathaus Neuss") match a row named only one of them.
    """
    if not enabled:
        return '0.0'
    return f"""COALESCE((
            SELECT max(CASE WHEN {column} = code THEN 1.0
                            ELSE similarity({column}, code) END)
            FROM unnest(cast({param} as text[])) AS code
        ), 0.0)"""


#: The row's importance (0-100) scaled into the score. A row without a
#: category has none and adds nothing. Added by `build_sql` to every plan's
#: score, after `min_score` has been applied: the floors judge how well the
#: text matched, and importance only orders what passed. Inside the floor, at
#: a weight that orders typos usefully, a city's importance alone cleared it.
IMPORTANCE_TERM = '%(w_importance)s::real * COALESCE(o.importance, 0)'


def inside_view_term(spatial: bool) -> str:
    """The bonus for a row whose centre lies in the requested view.

    DESIGN.md "Relevance and score" asks for it separately from the spatial
    *filter*: with `within=false` an object that merely crosses the box is a
    match, and one actually centred in it is a better one.
    """
    if not spatial:
        return '0.0'
    return (f"(CASE WHEN o.geom_center && {VIEW} "
            f"AND ST_Contains({VIEW}, o.geom_center) "
            "THEN %(w_inside)s::real ELSE 0.0 END)")


def name_score(*, has_phonetic: bool, spatial: bool) -> str:
    """The name formula, weights bound.

    `search_name` for whole-name similarity and `search_text` for the word
    channel: search_text carries the row's city too, which is context worth
    scoring but would match every row in a city if it were the whole
    channel.
    """
    return f"""
          %(w_similarity)s::real * similarity(o.search_name, %(q_name)s)
        + %(w_word_similarity)s::real * GREATEST(
              word_similarity(%(q_name)s, o.search_text),
              word_similarity(o.search_name, %(q_name)s))
        + %(w_phonetic)s::real * {phonetic_term('o.phon_name', '%(q_phon_tokens)s', has_phonetic)}
        + (CASE WHEN o.search_name = %(q_name)s THEN %(w_exact)s::real ELSE 0.0 END)
        + (CASE WHEN o.search_name LIKE %(q_prefix)s THEN %(w_prefix)s::real ELSE 0.0 END)
        + {inside_view_term(spatial)}
    """


# --- spatial -------------------------------------------------------------

#: The requested view, bbox or area, as one geometry. Written out wherever it
#: is used rather than read from a CTE: the function is immutable and its
#: argument bound, so the planner folds it into a constant geometry once and
#: estimates the spatial filter from the table's statistics. Read from a CTE
#: the view is opaque and taken for one row, and a Germany-wide area was
#: scanned through the GiST indexes ahead of the name index: 94 s for
#: "berlin" on de, against 12 ms without the area.
VIEW = 'ST_GeomFromText(%(area_wkt)s, 4326)'


def spatial_clause(spatial: bool, within: bool) -> str:
    """The optional spatial restriction, written so each column's own GiST
    index can be used.

    One OR branch per column rather than a filter on
    `COALESCE(polygon, line, point)`: the coalesce would be opaque to all
    three indexes and force a sequential scan, while the OR lets the
    planner combine them with a BitmapOr. The `&&` bounding-box test in
    front of each exact predicate is the part the index answers;
    ST_Within/ST_Intersects then rechecks only what the box let through.
    """
    if not spatial:
        return ''
    op = 'ST_Within' if within else 'ST_Intersects'
    branches = ' OR '.join(
        f'(o.{column} && {VIEW} AND {op}(o.{column}, {VIEW}))'
        for column in ('geom_point', 'geom_line', 'geom_polygon')
    )
    return f'AND ({branches})'


def area_params(bbox, area: str | None) -> dict:
    """`area_wkt` for `VIEW`: the area, or the bbox as a polygon."""
    if area is not None:
        return {'area_wkt': area}
    if bbox is not None:
        lon1, lat1, lon2, lat2 = bbox
        return {'area_wkt': f'POLYGON(({lon1} {lat1},{lon2} {lat1},{lon2} {lat2},'
                            f'{lon1} {lat2},{lon1} {lat1}))'}
    return {}


def distance_expr(column: str = 'o.geom_center') -> str:
    """Metres from the request's point, on the spheroid.

    Cast to geography so the result is metres rather than degrees, which
    are not comparable across latitudes -- and against the functional GiST
    the importer built on `(geom_center::geography)`, so ordering by it is
    still a KNN index scan rather than a sort of everything.
    """
    return (f'ST_Distance({column}::geography, '
            'ST_SetSRID(ST_MakePoint(%(near_lon)s, %(near_lat)s), 4326)::geography)')


#: What `scored` carries besides the score: every column an ORDER BY below
#: names, and nothing heavier.
ORDER_COLUMNS = ('o.id', 'o.name', 'o.addr_city', 'o.addr_street', 'o.addr_housenumber')

#: Every column named here has to be in `ORDER_COLUMNS`, because these
#: order the `scored` CTE and nothing else is in scope. `address`
#: sorted on `number` -- the integer part of a house number -- which is a
#: column of `osm_search_address` and not of `osm_search_object`, so
#: `sort=address` on a name query failed with `column "number" does not
#: exist`. The object table has only the text form, so the numeric ordering
#: that makes a street read 1, 2, 2a, 3 lives in `address._SORTS`, where the
#: column does exist; here the house number is a tie-break of last resort
#: and sorts as text.
_SORTS = {
    'score': 'score DESC, name ASC NULLS LAST, id ASC',
    'name': 'name ASC NULLS LAST, score DESC, id ASC',
    'address': ('addr_city ASC NULLS LAST, addr_street ASC NULLS LAST, '
                'addr_housenumber ASC NULLS LAST, id ASC'),
    'distance': 'distance ASC NULLS LAST, score DESC, id ASC',
}


def order_by(sort: str | None, *, has_distance: bool) -> str:
    """The ORDER BY for `sort`, defaulting to score.

    `distance` falls back when the request gave nothing to measure from:
    without a `near` or a bbox there is no point, and ordering by a column
    that is not in the select list would be an error rather than a
    sensible default.
    """
    if sort == 'distance' and not has_distance:
        sort = 'score'
    if (sort or 'score') == 'score' and has_distance:
        # Exact names tie by the dozen -- 395 Hauptstraßen on de_sh -- and the
        # nearest of equals is the one meant.
        return 'score DESC, distance ASC NULLS LAST, name ASC NULLS LAST, id ASC'
    return _SORTS.get(sort or 'score', _SORTS['score'])


# --- execution -----------------------------------------------------------

def execute_with_relaxation(conn, sql: str, params: dict, w: Weights,
                            trgm: float, word: float, *, page: int):
    """Run the strict pass, and only if it found nothing, one relaxed retry.

    The retry is skipped for pages past the first: an empty page 3 means
    the result set ran out, not that the thresholds were too strict, and
    re-running the whole query at a lower threshold there would return a
    page of rows that do not follow from page 2.
    """
    params = {**params, 'min_score': w.min_score}
    set_thresholds(conn, trgm, word)
    rows = conn.execute(sql, params).fetchall()
    if rows or page != 0:
        return rows

    set_thresholds(conn, w.relaxed_trgm_threshold, w.relaxed_word_threshold)
    params['min_score'] = w.relaxed_min_score
    return conn.execute(sql, params).fetchall()


# --- the response cache --------------------------------------------------

class ResultCache:
    """A TTL + LRU cache in front of the whole engine.

    Worth its complexity because of how search is used: a user types, and
    every keystroke re-sends a request differing from the last by one
    character -- but paging, re-sorting and a client re-issuing a query it
    already has on screen all repeat a request *exactly*. Those cost
    nothing here.

    TTL rather than explicit invalidation because the tables change only on
    a full re-import (there is no incremental path), so a stale entry can
    never be more than the TTL out of date and nothing has to notice the
    re-import happened.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value, ttl_seconds: int, max_size: int) -> None:
        if ttl_seconds <= 0 or max_size <= 0:
            return
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > max_size:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


# --- one mode's query ----------------------------------------------------

@dataclass(frozen=True, slots=True)
class Plan:
    """One search mode reduced to what the statement builder needs.

    `probes` are the candidate lookups, unioned: one per matching channel,
    so a row the letter channel misses entirely -- the phonetic
    misspellings -- can still be found by another. Scoring then re-weighs
    every channel over the union, which is why a row that entered on one
    probe can still outrank one that entered on all of them.

    An empty `probes` is a request nothing can answer (a name of pure
    punctuation, say). It means "return nothing" rather than "scan the
    table to return nothing", and the caller checks for it.
    """

    probes: tuple[str, ...]
    score: str
    params: dict
    #: Extra CTEs the probes reference, emitted ahead of `cand`.
    ctes: tuple[str, ...] = ()
    #: The row source, aliased `o`, and the column joining it to `cand`.
    table: str = 'osm_search_object'
    key: str = 'id'


def build_sql(plan: Plan, req, *, count_only: bool) -> str:
    """Assemble the single statement a request runs.

    One statement, not one per channel: the probes are CTE branches, the
    scoring joins back to the table once, and `count(*) OVER ()` yields the
    total in the same pass as the page. A query per channel would multiply
    the round trips by three for no gain, since the union has to be
    materialised before anything can be scored anyway.

    `{objects}` is left for the caller to fill with a schema-qualified
    identifier; it is the one part of this that cannot be a bind
    parameter, and it comes from configuration rather than from a request.
    """
    leading = [cte for cte in plan.ctes if cte]
    prefix = ''.join(f'{cte},\n' for cte in leading)
    spatial = spatial_clause(req.spatial, req.within)

    # No per-branch ORDER BY or LIMIT: every row a probe matches is scored,
    # so there is nothing for an ordering to protect and the sort would be
    # thrown away by the UNION anyway.
    branches = '\n        UNION\n'.join(
        f'        (SELECT o.{plan.key} FROM {{objects}} o WHERE {probe} {spatial})'
        for probe in plan.probes
    )

    if count_only:
        return f"""
        WITH {prefix}
        cand AS MATERIALIZED (
{branches}
        ),
        scored AS MATERIALIZED (
            SELECT ({plan.score}) AS match
            FROM {{objects}} o JOIN cand c ON c.{plan.key} = o.{plan.key}
        )
        SELECT count(*) FROM scored WHERE match >= %(min_score)s
        """

    from search import shape

    has_distance = req.point is not None
    distance = f', {distance_expr()} AS distance' if has_distance else ''
    order = order_by(req.sort, has_distance=has_distance)

    # Scored and cut to the page on the few columns an ORDER BY can name,
    # and only then joined back for the rest: the GeoJSON of every
    # candidate was built before the LIMIT threw most of it away -- all
    # 100 000 restaurants of de for a page of 200, 1 s.
    return f"""
    WITH {prefix}
    cand AS MATERIALIZED (
{branches}
    ),
    scored AS MATERIALIZED (
        SELECT {', '.join(ORDER_COLUMNS)},
               ({plan.score}) AS match,
               ({plan.score}) + {IMPORTANCE_TERM} AS score{distance}
        FROM {{objects}} o JOIN cand c ON c.{plan.key} = o.{plan.key}
    ),
    page AS MATERIALIZED (
        SELECT id, match, score{', distance' if has_distance else ''},
               count(*) OVER () AS total_count,
               row_number() OVER (ORDER BY {order}) AS position
        FROM scored
        WHERE match >= %(min_score)s
        ORDER BY {order}
        LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT {', '.join(shape.RESULT_COLUMNS)},
           {shape.GEOJSON_EXPR} AS geojson,
           {shape.CENTER_EXPR} AS center,
           p.match, p.score{', p.distance' if has_distance else ''}, p.total_count
    FROM page p JOIN {{objects}} o ON o.id = p.id
    ORDER BY p.position
    """


def base_params(plan: Plan, req, w: Weights) -> dict:
    """Everything the statement binds, except `min_score`.

    `min_score` is left out because the relaxation cascade sets it twice,
    and a caller that built it in here once would silently run the strict
    value on the relaxed pass.
    """
    params = {**w.params(), **plan.params, **area_params(req.bbox, req.area)}
    params['limit'] = req.limit
    params['offset'] = req.offset
    params['min_relevance'] = req.relevance
    point = req.point
    if point is not None:
        params['near_lon'], params['near_lat'] = point
    return params
