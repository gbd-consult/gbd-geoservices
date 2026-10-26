"""The one key check: carriers, scopes, referrers, rate.

Each decision here closes a way keys leak or a check fails open:

- the keys live in the deployment's `config/options.yaml`, which is
  git-ignored and outside the image -- only the dev password in
  `config.local/` is tracked -- and this module never sees a database
  credential at all (`lib/db.py`).
- a key list that arrives from the environment is a **string**, and `in` on
  a string is a substring test -- the key `"a"` would authenticate against a
  configured key of `"abc123"`. `_records()` below coerces to a list for
  exactly this.
- keys are compared with `secrets.compare_digest`, not `in`.
- a key is accepted in the query as well as in a header, so tiles can be
  protected too.
- keys have scopes: a key opens only what it names.

TWO CARRIERS, IN ONE ORDER

    Authorization: Bearer <key>     web clients; `fetch` sets it
    ?key=<key>                      everything that cannot set a header

The query parameter is not a concession, it is the only form an `<img>` tag,
a map library's tile template, QGIS or a WMTS client can send. It is also
the one that ends up in logs and caches, so `key` is stripped from both --
see `web/main.py`'s access log and the `Caddyfile`.

STATUS CODES

    401  no key, or a key that matches nothing
    403  a real key without the scope, or from a referrer not on its list
    429  over the key's rate

401 rather than 403 for a missing key is deliberate: 403 means "you are
identified and not allowed", which is a different thing for a client to
retry.

NO KEYS CONFIGURED

The versioned default is `keys: []`, which is what a developer runs with. An
empty list means **open**, because refusing every request would make the dev
stack unusable and the first thing anyone did would be to invent a key and
commit it. It is not silent: startup logs a warning, and `/status` reports
`"auth": "open"`, so a deployment that forgot its keys says so in the one
place an operator looks.
"""

from __future__ import annotations

import fnmatch
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from lib import config

_log = logging.getLogger(__name__)

#: The scopes a route can require. A key names the ones it carries.
SCOPES = ('tiles', 'search')

#: The query parameter, and the name stripped from logs and cache keys.
QUERY_PARAM = 'key'

#: Sliding window for `rate`, which is documented as requests per minute.
RATE_WINDOW_S = 60.0


@dataclass(frozen=True, slots=True)
class Key:
    """One configured key.

    `scopes` empty means every scope: a key record that names none is the
    shorthand form, and a deployment that wants a narrow key says so.
    """

    key: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    referrers: tuple[str, ...] = ()
    rate: int | None = None

    def allows(self, scope: str) -> bool:
        return not self.scopes or scope in self.scopes

    def allows_referrer(self, referrer: str | None) -> bool:
        """`referrers` is a list of globs checked against Origin/Referer.

        An empty list means any origin. A non-empty list and *no* referrer
        header is a refusal: the allowlist exists to bound where a key may
        be used from, and a request that declines to say is not bounded.

        The pattern is tried against the value as sent *and* against the
        value with a trailing slash, because the two headers spell the same
        site differently: `Referer` is a URL
        (`https://maps.example.de/app`), `Origin` is a bare origin with no
        path and no trailing slash (`https://maps.example.de`). The form
        one naturally writes, `https://maps.example.de/*`, matches the
        Referer and **not** the Origin -- and `referrer_of` prefers Origin,
        so without the second candidate an allowlist refuses exactly the
        browser requests it exists for.
        """
        if not self.referrers:
            return True
        if not referrer:
            return False
        candidates = (referrer, referrer + '/')
        return any(fnmatch.fnmatch(candidate, pattern)
                   for pattern in self.referrers for candidate in candidates)


class RateLimiter:
    """Per-key sliding window, in this process.

    In-process because the app is one worker per container (see the
    Dockerfile): a second worker would give each its own window and double
    the effective rate. Running several containers behind a proxy has the
    same problem, which is why *where* rate limiting belongs is undecided
    (`TODO.md`) -- this is the app's half, and if Caddy grows one too, one
    of them has to go.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, rate: int | None) -> bool:
        if not rate:
            return True
        now = time.monotonic()
        cutoff = now - RATE_WINDOW_S
        with self._lock:
            hits = [t for t in self._hits.get(key, ()) if t > cutoff]
            if len(hits) >= rate:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = RateLimiter()
_keys: tuple[Key, ...] | None = None


def _records() -> tuple[Key, ...]:
    """The configured keys.

    A record may be a mapping or a bare string; a bare string is the
    shorthand for "every scope, any origin, no rate". The whole value being
    a string rather than a list is the environment case (`_coerce`
    YAML-parses `GEOSERVICES_KEYS=abc` to the string `abc`), and wrapping it
    is what stops `in` from becoming a substring test.
    """
    raw = config.opt('keys') or []
    if isinstance(raw, (str, bytes, dict)):
        raw = [raw]
    out = []
    for entry in raw:
        if isinstance(entry, str):
            out.append(Key(key=entry))
            continue
        if not isinstance(entry, dict) or not entry.get('key'):
            _log.warning('ignoring a key record with no `key`: %r', entry)
            continue
        referrers = entry.get('referrers') or ()
        if isinstance(referrers, str):
            referrers = [referrers]
        scopes = entry.get('scopes') or ()
        if isinstance(scopes, str):
            scopes = [scopes]
        out.append(Key(
            key=str(entry['key']),
            scopes=frozenset(scopes),
            referrers=tuple(referrers),
            rate=int(entry['rate']) if entry.get('rate') else None,
        ))
    return tuple(out)


def configured(*, refresh: bool = False) -> tuple[Key, ...]:
    """The key records, read once.

    Not called `keys()`: `auth.keys()` reads as a mapping's method at every
    call site, which is what it is not.
    """
    global _keys
    if _keys is None or refresh:
        _keys = _records()
    return _keys


def open_access() -> bool:
    """True when no keys are configured, so every route is unauthenticated."""
    return not configured()


def reset() -> None:
    """Drop the cached keys and rate windows. Tests and `/internal/reload`."""
    global _keys
    _keys = None
    _limiter.clear()


def presented(request: Request) -> str | None:
    """The key the client sent, by the first carrier that has one."""
    header = request.headers.get('authorization')
    if header and header.lower().startswith('bearer '):
        return header[7:].strip() or None
    # Exactly `key`, not `KEY` or `Key`: the Caddyfile's log filter deletes
    # only this spelling, so any other one accepted would be logged in clear.
    return request.query_params.get(QUERY_PARAM) or None


def match(presented_key: str) -> Key | None:
    """The configured key equal to this one, in constant time.

    `compare_digest` against every record rather than a dict lookup: a dict
    would compare with `==`, which returns as soon as two bytes differ and
    so leaks the length of the shared prefix. The loop does not stop early
    for the same reason -- there are a handful of keys, and the cost of
    checking them all is nothing next to a tile render.

    Compared as **bytes**. `compare_digest` on `str` raises `TypeError` the
    moment either side is not ASCII, and the presented key is whatever a
    client sent -- so `?key=Ünicode` was an unhandled exception and a 500,
    from an unauthenticated request, on the one code path that exists to
    refuse them. UTF-8 encoding both sides makes a non-ASCII key an
    ordinary mismatch.
    """
    presented_bytes = presented_key.encode('utf-8')
    found = None
    for record in configured():
        if secrets.compare_digest(record.key.encode('utf-8'), presented_bytes):
            found = record
    return found


def referrer_of(request: Request) -> str | None:
    """Origin first, then Referer.

    Origin is the one a browser sets on the request that matters (it is
    sent on CORS requests and cannot be forged by page content); Referer is
    the fallback for a plain navigation or an `<img>`.
    """
    return request.headers.get('origin') or request.headers.get('referer')


def check(request: Request, scope: str | None) -> Key | None:
    """Authenticate and authorise, or raise.

    `scope` None accepts a key of any scope. Returns the key, or None when
    no keys are configured at all.
    """
    if open_access():
        return None

    presented_key = presented(request)
    if not presented_key:
        raise HTTPException(status_code=401, detail='an API key is required')

    record = match(presented_key)
    if record is None:
        # Never echo what was sent: an error body is a place a key ends up
        # in someone's log or screenshot.
        raise HTTPException(status_code=401, detail='invalid API key')

    if scope is not None and not record.allows(scope):
        raise HTTPException(status_code=403, detail=f'this key has no {scope} scope')

    if not record.allows_referrer(referrer_of(request)):
        raise HTTPException(status_code=403, detail='this key is not allowed from this origin')

    if not _limiter.allow(record.key, record.rate):
        raise HTTPException(status_code=429, detail='rate limit exceeded',
                            headers={'Retry-After': str(int(RATE_WINDOW_S))})
    return record


def requires(scope: str) -> Callable:
    """A FastAPI dependency for one scope.

    Declared once per router rather than per route, so a route added later
    is guarded by construction instead of by someone remembering.
    """
    if scope not in SCOPES:
        raise ValueError(f'unknown scope {scope!r}')

    def dependency(request: Request) -> Key | None:
        return check(request, scope)

    return dependency


def requires_key(request: Request) -> Key | None:
    """A FastAPI dependency for any valid key, whatever its scopes."""
    return check(request, None)


def warn_if_open() -> None:
    """Said once at startup, so an unprotected deployment is not silent."""
    if open_access():
        _log.warning(
            'No API keys configured: every route is open. Set `keys` in '
            'config/options.yaml for a deployment. /status reports this.')
