"""The address mode: street, house number, postcode, city, matched exactly.

The request carries the parts as fields (`street`, `housenumber`, and
optionally `postcode` and `city`); there is no free text to parse here. The
phrase mode reads an address out of free text and hands its readings to the
same matcher (`phrase.parse_address`), so an address is matched one way
whichever mode asked.

EXACT OR NOTHING

Every part given has to match: the street after normalisation and suffix
expansion ("Hauptstr." is "Hauptstraße"), the house number with its suffix
("12" is not "12a"), the postcode by equality, and the city against the
folded `addr:city` or any place on the address path -- an address without
`addr:city` still lies in Kiel. What matches is an address, relevance
`ranking.relevance.address`; what does not is nothing. There is no fuzzy
street match and no postcode or city bonus on purpose: with the city as a
bonus rather than a condition, "Hauptstraße 5 Kiel" gives every
Hauptstraße 5 in Schleswig-Holstein the same relevance as the one in Kiel.

Without a postcode or city a street and number can match many addresses --
every Hauptstraße 5 in the region -- and all of them are returned, the
nearest first when the request has a point.

THE STATEMENT

One per request, whatever the number of readings: each reading is an AND of
equalities, the readings are ORed, and the btree on `(search_street,
postcode, number, number_part)` answers each branch of the OR from its
leading column. The city's places are an `ARRAY(...)` subquery, which
Postgres evaluates once per statement, not per row.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib import text
from search import place as place_mode
from search import rank

#: Columns an address result needs. `osm_id` is the carrier: most addresses
#: sit on an unnamed building and so have no `id_object`, and the carrier id
#: is the only way a client reaches the outline in `osm_building`.
RESULT_COLUMNS = (
    'a.id', 'a.osm_id', 'a.street', 'a.housenumber', 'a.number', 'a.number_part',
    'a.postcode', 'a.city', 'a.id_object', 'a.id_places', 'a.category',
)

#: `a.city` in the form `lib.text.normalize` would have produced, folded in
#: SQL because `osm_search_address` stores only the raw `addr:city` -- unlike
#: `osm_search_object`, which has a `search_city` column next to its raw one.
#: Without the fold "Lübeck" lowercases to "lübeck" while the request
#: normalizes to "luebeck", and on the `de_sh` extract that is 152 472 of
#: 723 655 addresses, one in five. A `search_city` column on the address
#: table would be the cleaner place for it and is an importer decision.
#:
#: `test_address.py` pins this against `lib.text.normalize` over every
#: distinct city in the imported data, so the two cannot drift.
NORMALIZED_CITY = ("btrim(regexp_replace(replace(replace(replace(replace("
                   "lower(a.city), 'ä', 'ae'), 'ö', 'oe'), 'ü', 'ue'), 'ß', 'ss'), "
                   "'[^a-z0-9]+', ' ', 'g'))")

_ORDER_TAIL = 'city ASC NULLS LAST, street ASC NULLS LAST, number ASC NULLS LAST, ' \
              'number_part ASC NULLS LAST, id ASC'

_SORTS = {
    'address': _ORDER_TAIL,
    'name': 'street ASC NULLS LAST, number ASC NULLS LAST, id ASC',
    'distance': f'distance ASC NULLS LAST, {_ORDER_TAIL}',
    # Every row is an exact match, so the score has nothing to order by;
    # with a point the nearest of equals is the one meant.
    'score': _ORDER_TAIL,
}


@dataclass(frozen=True, slots=True)
class Address:
    """One reading of an address, normalised the way the importer stored it."""

    street: str
    number: int
    number_part: str | None = None
    postcode: str | None = None
    city: str | None = None

    def as_dict(self) -> dict:
        out = {'street': self.street, 'housenumber': f'{self.number}{self.number_part or ""}'}
        if self.postcode:
            out['postcode'] = self.postcode
        if self.city:
            out['city'] = self.city
        return out


def from_request(req) -> Address | None:
    """The request's fields as an `Address`, or None when they cannot match.

    `request.parse` has already refused a request without a street or a
    readable house number; a street of pure punctuation normalises to ''
    and so can match nothing.
    """
    street = text.expand_street(req.street)
    number, number_part = text.extract_housenumber(req.housenumber)
    if not street:
        return None
    return Address(street=street, number=number, number_part=number_part,
                   postcode=(req.postcode or '').strip() or None,
                   city=text.normalize(req.city) or None)


#: A street matched fuzzily: the names in the street dictionary similar to
#: it, by its trigram index, then each by equality as usual. The address
#: table has no trigram index of its own, and needs none.
LIKE_STREET = ('a.search_street = ANY(ARRAY(SELECT st.search_street FROM {{streets}} st'
               ' WHERE st.search_street %% %(street_{i})s))')


def _reading(i: int, address: Address, street_like: bool = False) -> tuple[str, dict]:
    """One reading as a condition on `a`, with its parameters."""
    params = {
        f'street_{i}': address.street,
        f'number_{i}': address.number,
        f'number_part_{i}': address.number_part,
    }
    conditions = [
        LIKE_STREET.format(i=i) if street_like else f'a.search_street = %(street_{i})s',
        f'a.number = %(number_{i})s',
        f'a.number_part IS NOT DISTINCT FROM %(number_part_{i})s',
    ]
    if address.postcode:
        params[f'postcode_{i}'] = address.postcode
        conditions.append(f'a.postcode = %(postcode_{i})s')
    if address.city:
        params[f'city_{i}'] = address.city
        params[f'city_place_{i}'] = text.expand_street(address.city)
        conditions.append(
            f'({NORMALIZED_CITY} = %(city_{i})s'
            f' OR a.id_places && ARRAY(SELECT o.id FROM {{objects}} o'
            f' WHERE o.search_name = %(city_place_{i})s'
            f' AND o.categories && %(place_categories)s))')
    return '(' + ' AND '.join(conditions) + ')', params


def _where(readings: list[Address], street_like: bool = False) -> tuple[str, str, dict]:
    """The OR of the readings, the CASE naming which one matched, the parameters."""
    params = {'place_categories': list(place_mode.PLACE_CATEGORIES)}
    conditions = []
    for i, address in enumerate(readings):
        condition, reading_params = _reading(i, address, street_like)
        conditions.append(condition)
        params.update(reading_params)
    which = 'CASE ' + ' '.join(f'WHEN {c} THEN {i}' for i, c in enumerate(conditions)) + ' END'
    return '(' + ' OR '.join(conditions) + ')', which, params


def spatial_clause(spatial: bool) -> str:
    """An address is a point, so `within` and `intersect` are the same test.

    On the candidates' own `geom`, not the table's: tested on the table,
    the planner cannot estimate the view box, takes it for one row and
    scans the GiST for it -- 58 000 rows in a Kiel bbox on `de_sh`, for four
    Bahnhofstraße 1.
    """
    if not spatial:
        return ''
    return f'AND ST_Within(c.geom, {rank.VIEW})'


def build_sql(readings: list[Address], req, *, count_only: bool,
              limit: int | None = None, offset: int = 0,
              street_like: bool = False) -> tuple[str, dict]:
    """The statement for one or more readings, and its parameters.

    `{addresses}`, `{objects}` and `{streets}` are left for the caller to
    fill with schema-qualified identifiers. `street_like` matches the street
    fuzzily (`LIKE_STREET`), at the pg_trgm threshold the caller has set.
    """
    from search import shape

    where, which, params = _where(readings, street_like)
    params.update(rank.area_params(req.bbox, req.area))
    ctes = f"""WITH
    cand AS MATERIALIZED (SELECT a.id, a.geom FROM {{addresses}} a WHERE {where})"""
    spatial = spatial_clause(req.spatial)

    if count_only:
        return f"""
        {ctes}
        SELECT count(*) FROM {{addresses}} a JOIN cand c ON c.id = a.id
        WHERE TRUE {spatial}
        """, params

    has_distance = req.point is not None
    distance = f', {rank.distance_expr("a.geom")} AS distance' if has_distance else ''
    if has_distance:
        params['near_lon'], params['near_lat'] = req.point
    sort = req.sort or 'score'
    if sort == 'score' and has_distance:
        sort = 'distance'
    if sort == 'distance' and not has_distance:
        sort = 'score'
    params['limit'] = req.limit if limit is None else limit
    params['offset'] = req.offset if limit is None else offset

    return f"""
    {ctes}
    SELECT {', '.join(RESULT_COLUMNS)},
           ST_AsGeoJSON(a.geom, {shape.GEOJSON_DECIMALS}) AS geojson,
           {which} AS reading{distance},
           count(*) OVER () AS total_count
    FROM {{addresses}} a JOIN cand c ON c.id = a.id
    WHERE TRUE {spatial}
    ORDER BY {_SORTS.get(sort, _SORTS['score'])}
    LIMIT %(limit)s OFFSET %(offset)s
    """, params
