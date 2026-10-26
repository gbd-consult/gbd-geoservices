"""The search request, and the validation that a bad one never reaches SQL.

The body is `mode` + `text` (DESIGN.md "Modes"), so the shape of the
request says which mode runs instead of it being inferred from which field
happens to be filled.

There is no pydantic here on purpose. `search` is called directly by
`manage.py`, the profilers and the tests as well as by HTTP, and FastAPI is
the web module's dependency, not this one's. `web/search.py` owns the body
model and translates it into this; this owns what is *valid*, which is the
half that has to hold however the call arrived.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from lib import text

#: What `mode` may be. A request names its mode rather than the engine
#: guessing from which fields are set, which would make "name wins when
#: both are given" a rule someone had to know.
MODES = ('name', 'address', 'phrase', 'point')

#: The address mode's fields.
ADDRESS_FIELDS = ('street', 'housenumber', 'postcode', 'city')

#: `sort` is a display preference, so an unknown value falls back to the
#: score order rather than raising -- a client with a typo should get results
#: in a sensible order, not an error.
SORTS = ('score', 'name', 'address', 'distance')

#: `limit` is capped because every row of a page is scored, shaped and
#: serialized; the cap is part of the API contract.
MAX_LIMIT = 100
DEFAULT_LIMIT = 50

#: 1 = very fuzzy, 10 = near-exact. Also the latency knob: it sets both
#: pg_trgm thresholds, and a higher value means fewer candidates to score.
#: 7 because, on de_sh, it found the same top ten for typos and prefixes as 4
#: at a third of the p90 latency; from 9 short prefixes ("Flens") drop out.
MIN_SIMILARITY = 1
MAX_SIMILARITY = 10
DEFAULT_SIMILARITY = 7

#: Results below this relevance (0-100, `ranking.relevance`) are dropped.
MAX_RELEVANCE = 100

#: The point mode's `radius`, metres. A client passes its click
#: tolerance; anything wider is a search, not a click.
MAX_RADIUS = 10_000

#: What the point mode refuses: a point has no text to match, no ranking
#: to tune and no pages, and its spatial filter is the radius.
NOT_POINT = ('text', 'bbox', 'area', 'within', 'sort', 'similarity', 'relevance', 'page')


class RequestError(ValueError):
    """A request that cannot be answered as asked.

    Distinct from a request that finds nothing: the web module turns this
    into a 422 and an empty result into a 200.
    """


@dataclass(frozen=True, slots=True)
class Request:
    """One search request, validated.

    Construct through `parse()` rather than directly -- the constructor
    does no checking, so that `replace()` on an already-valid request (the
    phrase mode builds one per rule) does not re-validate on every rule.
    """

    mode: str
    text: str = ''
    categories: tuple[str, ...] = ()
    #: lon1, lat1, lon2, lat2 in EPSG:4326. Mutually exclusive with `area`.
    bbox: tuple[float, float, float, float] | None = None
    #: A WKT polygon in EPSG:4326, for a drawn shape a bbox cannot express.
    area: str | None = None
    #: With a bbox or area: True means the object must lie entirely inside
    #: (ST_Within), False that touching is enough (ST_Intersects).
    #:
    #: False is the default, as DESIGN.md "Modes" states it. It is not a
    #: preference: the whole point of testing each geometry column rather
    #: than the centre is that a river or a long street crossing the view is
    #: a hit, and `ST_Within` is exactly the operator that throws those
    #: away. `rank.inside_view_bonus` is the other half of the same idea --
    #: an object merely crossing the box is a match, one centred in it a
    #: better one -- and it has nothing to do if everything returned is
    #: inside already.
    within: bool = False
    #: The point distance is measured from. Defaults to the centre of
    #: `bbox` when there is one, so `sort=distance` works without it. In the
    #: point mode, the point itself, and required.
    near: tuple[float, float] | None = None
    sort: str = 'score'
    similarity: int = DEFAULT_SIMILARITY
    page: int = 0
    limit: int = DEFAULT_LIMIT
    lang: str = 'de'
    relevance: int = 0
    #: The address mode's fields. `street` and `housenumber` are required
    #: there and refused everywhere else, as are the other two.
    street: str | None = None
    housenumber: str | None = None
    postcode: str | None = None
    city: str | None = None
    #: The point mode's: metres around `near`, replacing both configured
    #: radii, and whether the nearest address is looked up.
    radius: float | None = None
    with_address: bool = True

    @property
    def offset(self) -> int:
        return self.page * self.limit

    @property
    def point(self) -> tuple[float, float] | None:
        """What distance is measured from: `near`, else the bbox centre."""
        if self.near is not None:
            return self.near
        if self.bbox is not None:
            lon1, lat1, lon2, lat2 = self.bbox
            return ((lon1 + lon2) / 2, (lat1 + lat2) / 2)
        return None

    @property
    def spatial(self) -> bool:
        return self.bbox is not None or self.area is not None

    def for_rule(self, **changes) -> Request:
        """A copy with fields changed, unvalidated.

        The phrase mode rewrites `text` and `categories` per rule and runs
        the same machinery; nothing it writes can be invalid.
        """
        return replace(self, **changes)

    def cache_key(self, prefix: str) -> str:
        """A key covering every field that changes the result.

        Every field, not the ones that happen to matter today: a cache
        keyed on a subset silently serves the wrong answer the moment a
        field starts being used, and that failure looks like a ranking bug
        rather than a caching one. `\\x1f` separates, so no value can spell
        another key by containing the separator.
        """
        parts = (
            prefix, self.mode, self.text, ','.join(self.categories),
            repr(self.bbox), self.area or '', str(self.within),
            repr(self.near), self.sort, str(self.similarity),
            str(self.page), str(self.limit), self.lang, str(self.relevance),
            self.street or '', self.housenumber or '', self.postcode or '', self.city or '',
            repr(self.radius), str(self.with_address),
        )
        return '\x1f'.join(parts)


def parse(body: dict) -> Request:
    """Validate a request body and build a `Request`.

    Everything that can be wrong is wrong here, once, with a message that
    names the field -- rather than in the query builder, where it would
    surface as a database error the caller cannot act on.
    """
    mode = _string(body, 'mode', required=True)
    if mode not in MODES:
        raise RequestError(f'mode must be one of {", ".join(MODES)}, got {mode!r}')

    if mode == 'point':
        return _point(body)
    for name in ('radius', 'address'):
        if body.get(name) is not None:
            raise RequestError(f'{name}: only in the point mode')

    query = (_string(body, 'text') or '').strip()
    categories = _categories(body.get('categories'))
    if mode == 'address':
        if query or categories:
            # Free text is parsed into an address by the phrase mode only;
            # here the parts are fields, and an address has no category.
            raise RequestError('the address mode takes street, housenumber, postcode '
                               'and city, not text or categories')
    elif not query and not categories:
        # A request with neither is a full-table scan that ranks nothing.
        # A bare category list is legitimate: it is the category browse.
        raise RequestError('text or categories must be given')

    address = _address(body, mode)

    bbox = _bbox(body.get('bbox'))
    area = _area(_string(body, 'area'))
    if bbox is not None and area is not None:
        # Not ANDed, and not silently one-of: which of the two applied
        # would be invisible in the result, and a caller sending both means
        # something by each.
        raise RequestError('bbox and area are alternatives; send one')

    return Request(
        mode=mode,
        text=query,
        categories=categories,
        bbox=bbox,
        area=area,
        within=_bool(body.get('within'), default=False),
        near=_near(body.get('near')),
        sort=_sort(body.get('sort')),
        similarity=_bounded(body.get('similarity'), 'similarity',
                            MIN_SIMILARITY, MAX_SIMILARITY, DEFAULT_SIMILARITY),
        page=_page(body.get('page')),
        limit=_bounded(body.get('limit'), 'limit', 1, MAX_LIMIT, DEFAULT_LIMIT),
        lang=_string(body, 'lang') or 'de',
        relevance=_bounded(body.get('relevance'), 'relevance', 0, MAX_RELEVANCE, 0),
        **address,
    )


def _point(body: dict) -> Request:
    """The point mode: what is at `near`, optionally narrowed by
    `categories`."""
    given = [name for name in (*NOT_POINT, *ADDRESS_FIELDS) if body.get(name) is not None]
    if given:
        raise RequestError(f'{", ".join(given)}: not in the point mode')
    near = _near(body.get('near'))
    if near is None:
        raise RequestError('near is required in the point mode')
    return Request(
        mode='point',
        categories=_categories(body.get('categories')),
        near=near,
        limit=_bounded(body.get('limit'), 'limit', 1, MAX_LIMIT, DEFAULT_LIMIT),
        lang=_string(body, 'lang') or 'de',
        radius=_radius(body.get('radius')),
        with_address=_bool(body.get('address'), default=True),
    )


# --- field validation ----------------------------------------------------

def _string(body: dict, name: str, *, required: bool = False) -> str | None:
    value = body.get(name)
    if value is None:
        if required:
            raise RequestError(f'{name} is required')
        return None
    if not isinstance(value, str):
        raise RequestError(f'{name} must be a string, got {type(value).__name__}')
    return value


def _address(body: dict, mode: str) -> dict:
    fields = {name: (_scalar(body, name) or '').strip() or None for name in ADDRESS_FIELDS}
    if mode != 'address':
        given = [name for name, value in fields.items() if value]
        if given:
            raise RequestError(f'{", ".join(given)}: only in the address mode')
        return {}
    for name in ('street', 'housenumber'):
        if not fields[name]:
            raise RequestError(f'{name} is required in the address mode')
    if text.extract_housenumber(fields['housenumber']) is None:
        raise RequestError(f'housenumber must be a number with an optional letter, '
                           f'got {fields["housenumber"]!r}')
    return fields


def _scalar(body: dict, name: str) -> str | None:
    """A string field that a client may also send as a number: a house
    number or a postcode typed into a numeric input arrives as one."""
    value = body.get(name)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _string(body, name)


def _categories(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise RequestError('categories must be a list of ids')
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RequestError(f'categories must be non-empty ids, got {item!r}')
        out.append(item.strip())
    return tuple(out)


def _area(value: str | None) -> str | None:
    """Reject WKT the database would reject, here rather than there.

    Without this the string went straight to `ST_GeomFromText` and a typo
    came back as a psycopg error -- a 500 on what is squarely a client
    mistake, with a message about parse position rather than about the
    field. Shapely is already a dependency of the image (the importer
    builds every geometry with it), and parsing one polygon costs nothing
    next to the query it guards.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    import shapely
    try:
        geometry = shapely.from_wkt(value)
    except Exception as exc:                     # shapely raises several types
        raise RequestError(f'area is not valid WKT: {exc}') from exc
    if geometry is None or geometry.is_empty:
        raise RequestError('area is an empty geometry')
    if shapely.get_type_id(geometry) not in (3, 6):        # Polygon, MultiPolygon
        raise RequestError(f'area must be a polygon, got {geometry.geom_type}')
    return value


def _bbox(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise RequestError('bbox must be lon1,lat1,lon2,lat2')
    try:
        lon1, lat1, lon2, lat2 = (float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise RequestError(f'bbox must be four numbers: {exc}') from exc
    # Normalised rather than rejected: the corner order is a client
    # convention (some send top-left first), and the box means the same
    # either way.
    lon1, lon2 = min(lon1, lon2), max(lon1, lon2)
    lat1, lat2 = min(lat1, lat2), max(lat1, lat2)
    _in_range(lon1, lat1)
    _in_range(lon2, lat2)
    if lon1 == lon2 or lat1 == lat2:
        raise RequestError('bbox has zero width or height')
    return (lon1, lat1, lon2, lat2)


def _near(value) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise RequestError('near must be lon,lat')
    try:
        lon, lat = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise RequestError(f'near must be two numbers: {exc}') from exc
    _in_range(lon, lat)
    return (lon, lat)


def _in_range(lon: float, lat: float) -> None:
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise RequestError(f'coordinates out of range: {lon}, {lat} (EPSG:4326 is lon, lat)')


def _radius(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RequestError(f'radius must be a number, got {value!r}')
    try:
        radius = float(value)
    except (TypeError, ValueError) as exc:
        raise RequestError(f'radius must be a number, got {value!r}') from exc
    if not (0 < radius <= MAX_RADIUS):
        raise RequestError(f'radius must be above 0 and at most {MAX_RADIUS}, got {radius}')
    return radius


def _bool(value, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false', '1', '0'):
        return value.lower() in ('true', '1')
    raise RequestError(f'expected a boolean, got {value!r}')


def _sort(value) -> str:
    if value is None:
        return 'score'
    if not isinstance(value, str) or value not in SORTS:
        return 'score'
    return value


def _page(value) -> int:
    if value is None:
        return 0
    try:
        page = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestError(f'page must be a whole number, got {value!r}') from exc
    if page < 0:
        raise RequestError('page must not be negative')
    return page


def _bounded(value, name: str, low: int, high: int, default: int) -> int:
    """A bounded integer.

    Out of range is an error rather than a clamp: `limit: 5000` means the
    caller expects 5000 rows, and quietly returning 100 of them looks to
    them like the data ran out.
    """
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestError(f'{name} must be a whole number, got {value!r}') from exc
    if not (low <= number <= high):
        raise RequestError(f'{name} must be between {low} and {high}, got {number}')
    return number
