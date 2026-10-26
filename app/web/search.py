"""The search routes.

    POST /search              the four modes, one body
    POST /search/count        the same body, {"total": n}
    POST /search/fuzzy        the fuzzy name search alone, a name-mode body
    POST /search/fuzzy/count  its total

The category tree a client filters by is part of `/metadata` (`web/meta.py`).

Every one of these is a translation and nothing else: a body becomes a
`search.request.Request`, a `Request` becomes a call on `search.api`, and the
result is already the response shape. The validation lives in
`search/request.py` rather than here, because `manage.py`, the profilers and
the tests reach the same functions without going through HTTP and have to be
refused for the same reasons.

That split is also why there are no pydantic models for the body. FastAPI
would give one route a generated schema and leave every non-HTTP caller
unvalidated, which is precisely the drift `search/request.py` exists to
prevent. `/docs` gets the shape from the docstrings and the examples below.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from search import api as search_api
from search.request import RequestError, parse
from web import auth
from web import icons as icon_routes

router = APIRouter(prefix='/search', tags=['search'],
                   dependencies=[Depends(auth.requires('search'))])

#: Shown in `/docs`. The four modes, so the shape is discoverable without
#: reading `DESIGN.md`.
EXAMPLES = {
    'name': {'summary': 'a name, optionally narrowed by category',
             'value': {'mode': 'name', 'text': 'Rathaus',
                       'categories': ['cat_poi_public'], 'bbox': [9.5, 54.2, 10.3, 54.5]}},
    'address': {'summary': 'street and house number, optionally postcode and city; exact',
                'value': {'mode': 'address', 'street': 'Holtenauer Straße',
                          'housenumber': '12', 'postcode': '24105', 'city': 'Kiel'}},
    'phrase': {'summary': 'free form; the response carries an interpretation',
               'value': {'mode': 'phrase', 'text': 'Restaurant Kiel'}},
    'phrase_address': {'summary': 'a full address as free text, first at relevance 100',
                       'value': {'mode': 'phrase', 'text': 'Holtenauer Straße 12, 24105 Kiel'}},
    'point': {'summary': 'what is at a point: near first, then the containing areas',
                'value': {'mode': 'point', 'near': [10.1335, 54.3269], 'radius': 25}},
}


def request_from(body: dict, *, fuzzy: bool = False):
    """A validated `Request`, or 422 naming the field.

    422 rather than 400: the body parsed as JSON and was the wrong
    *content*, which is the distinction a client acts on.
    """
    try:
        req = parse(body)
        if fuzzy:
            search_api.check_fuzzy(req)
        return req
    except RequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def with_icons(body: dict, base: str) -> dict:
    """The body with each feature's icon URL, for its own `category`.

    Added here because it is the one part of a result that depends on the
    request -- the host and path it reached the API under. The search module
    caches bodies, so this copies what it changes rather than writing the
    URL of whichever caller came first into the shared entry.
    """
    def feature(item: dict) -> dict:
        category = item['properties'].get('category')
        if not category:
            return item
        return {**item, 'properties': {**item['properties'],
                                       'icon': icon_routes.url(base, category)}}

    return {**body, 'results': {**body['results'],
                                'features': [feature(item) for item in body['results']['features']]}}


@router.post('')
def find(body: Annotated[dict, Body(openapi_examples=EXAMPLES)], request: Request) -> dict:
    """Search by name, address, free-form phrase, or point.

    Returns `page`, `limit`, `count`, `total` and `has_more`, an
    `interpretation` in phrase mode, and `results`, a GeoJSON
    FeatureCollection. The name mode is the normalised name, exactly. The
    address mode takes `street` and `housenumber`, optionally `postcode`
    and `city`, instead of `text`, and matches every part exactly. Every
    feature has the same flat properties: `name` ('' when unnamed),
    `category`, `category_name`, `categories` ({id, name}, root
    first), `icon` (the URL of the category's icon), `center`, `places`,
    `match_relevance` (0-100: 100 = an exactly matched address or the
    point mode's nearest address, 99 = an exact name or anything else at a
    point), `match_score`, `match_rule` (the phrase rule that found it,
    e.g. `category_in_place`), `match_distance`,
    `address_street`, `address_housenumber`, `address_postcode`,
    `address_city`, `osm_ids`, `osm_tags` -- null where they do not apply.
    `relevance` in the body drops results below it.

    The point mode takes `near` ([lon, lat]), optionally `radius`
    (metres, replacing both configured radii -- a client passes its click
    tolerance), `categories`, `address` (default true) and `limit`: the
    nearest address first, then what is near the point by distance, then
    the containing areas smallest first, unpaged and unscored.
    """
    return with_icons(search_api.find(request_from(body)), str(request.base_url))


@router.post('/count')
def count(body: Annotated[dict, Body(openapi_examples=EXAMPLES)]) -> dict:
    """The total for the same body, without the rows.

    A separate call because it is the uncapped one: `/search` stops at a
    page. In phrase mode it is the merged candidate count, the same number
    `/search` reports, because capped rules have no window to count
    over.
    """
    return {'total': search_api.count(request_from(body))}


@router.post('/fuzzy')
def find_fuzzy(body: Annotated[dict, Body(openapi_examples={'name': EXAMPLES['name']})],
               request: Request) -> dict:
    """The fuzzy name search alone: letter similarity, word fragments and
    sound, without the exact name `/search` tries first.

    The body is a name-mode body with `text`; `similarity` sets how fuzzy.
    Every result is at `ranking.relevance.name_fuzzy`; the response is
    `/search`'s.
    """
    return with_icons(search_api.find(request_from(body, fuzzy=True), fuzzy=True),
                      str(request.base_url))


@router.post('/fuzzy/count')
def count_fuzzy(body: Annotated[dict, Body(openapi_examples={'name': EXAMPLES['name']})]) -> dict:
    """The total for the same body as `/search/fuzzy`."""
    return {'total': search_api.count(request_from(body, fuzzy=True), fuzzy=True)}
