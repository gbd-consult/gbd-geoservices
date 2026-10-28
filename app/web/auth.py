"""The one key check: carriers, scopes, referrers, expiry, rate, usage.

Each decision here closes a way keys leak or a check fails open:

- the keys live in the database (`lib/keys.py`), as SHA-256 digests only: a
  presented key is hashed and looked up, so no key is held in clear here,
  in the database or in a backup of it.
- a key is accepted in the query as well as in a header, so tiles can be
  protected too.
- keys have scopes: a key opens only what it names.
- a key can be disabled and can expire; either is a 403, at once for every
  request after the next reload of the records (`KEYS_TTL_S`).

The records are re-read every `KEYS_TTL_S`, so a key added, disabled or
re-enabled with `manage.py` takes effect without a reload. If the database
cannot be read the last records stay in use; a process that never read
them refuses every keyed request with 503, never opens.

USAGE

Every request to a `requires(scope)` route that carries a registered key is
counted per key and month once its response status is known (`count`, from
the `count_usage` middleware in `web/main.py`): a status below 400 under the
route's scope -- tiles and search apart, whatever scopes the key carries --
and 400 or above, the key's own refusals (403, 429) included, as `errors`.
A request with no key or an unknown one has no key to count it for. The
counts are kept in this process and added to `service.key_usage` every
`USAGE_FLUSH_S` and at shutdown; a flush that fails keeps them for the next.

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

NO KEYS REGISTERED

A database with no key in `service.api_key` is what a developer runs with,
and it means **open**, because refusing every request would make the dev
stack unusable and the first thing anyone did would be to invent a key and
commit it. It is not silent: startup logs a warning, and `/status` reports
`"auth": "open"`, so a deployment that forgot its keys says so in the one
place an operator looks.
"""

from __future__ import annotations

import datetime
import fnmatch
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from lib import keys as store

_log = logging.getLogger(__name__)

#: The scopes a route can require. A key names the ones it carries.
SCOPES = store.SCOPES

#: The query parameter, and the name stripped from logs and cache keys.
QUERY_PARAM = 'key'

#: Sliding window for `rate`, which is documented as requests per minute.
RATE_WINDOW_S = 60.0

#: How old the key records may get: the delay before a disabled key is refused.
KEYS_TTL_S = 30.0

#: How often the usage counts go to the database; a crash loses at most this much.
USAGE_FLUSH_S = 60.0


@dataclass(frozen=True, slots=True)
class Key:
    """One key record; the key itself is not part of it.

    `scopes` empty means every scope: a key record that names none is the
    shorthand form, and a deployment that wants a narrow key says so.
    `expires` is the last day the key is valid, in UTC.
    """

    id: int
    name: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    referrers: tuple[str, ...] = ()
    rate: int | None = None
    expires: datetime.date | None = None
    disabled: bool = False

    def expired(self, today: datetime.date) -> bool:
        return self.expires is not None and today > self.expires

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
        self._hits: dict[int, list[float]] = {}

    def allow(self, key: int, rate: int | None) -> bool:
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


class Usage:
    """Requests per (key id, month) and scope, since the last flush."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[int, datetime.date], dict[str, int]] = \
            defaultdict(lambda: defaultdict(int))

    def count(self, key: Key, column: str) -> None:
        month = store.month_of(store.today())
        with self._lock:
            self._counts[(key.id, month)][column] += 1

    def flush(self) -> None:
        """Add the counts to the database; on failure keep them for the next."""
        with self._lock:
            counts, self._counts = self._counts, defaultdict(lambda: defaultdict(int))
        if not counts:
            return
        try:
            store.add_usage(counts)
        except Exception as exc:                  # noqa: BLE001 - the counts are the invoice
            _log.error('could not write the key usage, kept for the next flush: %s', exc)
            with self._lock:
                for slot, scopes in counts.items():
                    for scope, n in scopes.items():
                        self._counts[slot][scope] += n

    def clear(self) -> None:
        with self._lock:
            self._counts.clear()


_limiter = RateLimiter()
_usage = Usage()
_keys: dict[str, Key] | None = None
_loaded_at = 0.0
_load_lock = threading.Lock()


def _records() -> dict[str, Key]:
    """The key records by digest, from the database."""
    return records_of(store.load())


def records_of(rows) -> dict[str, Key]:
    """`service.api_key` rows as key records by digest."""
    return {row['hash']: Key(
        id=row['id'],
        name=row['name'],
        scopes=frozenset(row['scopes'] or ()),
        referrers=tuple(row['referrers'] or ()),
        rate=row['rate'],
        expires=row['expires'],
        disabled=row['disabled'],
    ) for row in rows}


def configured(*, refresh: bool = False) -> dict[str, Key]:
    """The key records by digest, re-read every `KEYS_TTL_S`.

    Not called `keys()`: `auth.keys()` reads as a mapping's method at every
    call site. A failed read keeps the records there are; with none read
    yet it raises 503 rather than answer "no keys", which would be "open".
    """
    global _keys, _loaded_at
    with _load_lock:
        if _keys is not None and not refresh and time.monotonic() - _loaded_at < KEYS_TTL_S:
            return _keys
        try:
            _keys = _records()
        except Exception as exc:                  # noqa: BLE001 - any failure: keep what there is
            _log.error('could not read the API keys: %s', exc)
            if _keys is None:
                raise HTTPException(status_code=503, detail='API keys unavailable') from exc
        _loaded_at = time.monotonic()
        return _keys


def open_access() -> bool:
    """True when no keys are registered, so every route is unauthenticated."""
    return not configured()


def reset() -> None:
    """Drop the cached keys and rate windows. Tests and `/internal/reload`."""
    global _keys
    _keys = None
    _limiter.clear()


def count(request: Request, status: int) -> None:
    """Count a finished request for its key: under its scope, or as an error."""
    record = getattr(request.state, 'key', None)
    scope = getattr(request.state, 'key_scope', None)
    if record is not None and scope is not None:
        _usage.count(record, scope if status < 400 else 'errors')


def flush_usage() -> None:
    _usage.flush()


def start_usage_flush() -> Callable[[], None]:
    """Flush every `USAGE_FLUSH_S` in a thread; returns the stop, which flushes once more."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(USAGE_FLUSH_S):
            _usage.flush()

    thread = threading.Thread(target=loop, name='key-usage', daemon=True)
    thread.start()

    def stopper() -> None:
        stop.set()
        thread.join()
        _usage.flush()

    return stopper


def presented(request: Request) -> str | None:
    """The key the client sent, by the first carrier that has one."""
    header = request.headers.get('authorization')
    if header and header.lower().startswith('bearer '):
        return header[7:].strip() or None
    # Exactly `key`, not `KEY` or `Key`: the Caddyfile's log filter deletes
    # only this spelling, so any other one accepted would be logged in clear.
    return request.query_params.get(QUERY_PARAM) or None


def match(presented_key: str) -> Key | None:
    """The record of this key, by its digest.

    A dict lookup is safe here although it compares with `==`: what it
    compares is the SHA-256 of the presented key, and how much of a digest
    matches says nothing about how much of the key does. The digest is over
    UTF-8, so a non-ASCII key is an ordinary mismatch, not an exception.
    """
    return configured().get(store.digest(presented_key))


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
    if record is not None:
        request.state.key = record                # for `count`, even if refused below
    if record is None:
        # Never echo what was sent: an error body is a place a key ends up
        # in someone's log or screenshot.
        raise HTTPException(status_code=401, detail='invalid API key')

    if record.disabled:
        raise HTTPException(status_code=403, detail='this key is disabled')

    if record.expired(store.today()):
        raise HTTPException(status_code=403, detail='this key has expired')

    if scope is not None and not record.allows(scope):
        raise HTTPException(status_code=403, detail=f'this key has no {scope} scope')

    if not record.allows_referrer(referrer_of(request)):
        raise HTTPException(status_code=403, detail='this key is not allowed from this origin')

    if not _limiter.allow(record.id, record.rate):
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
        request.state.key_scope = scope
        return check(request, scope)

    return dependency


def requires_key(request: Request) -> Key | None:
    """A FastAPI dependency for any valid key, whatever its scopes; not counted."""
    return check(request, None)


def warn_if_open() -> None:
    """Said once at startup, so an unprotected deployment is not silent."""
    try:
        is_open = open_access()
    except HTTPException:
        return                                    # configured() logged why
    if is_open:
        _log.warning(
            'No API keys registered: every route is open. Add one with '
            '`manage.sh key-add` for a deployment. /status reports this.')
