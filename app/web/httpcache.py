"""`Cache-Control` and conditional requests: the browser tier in front of
the two server-side ones in `renderer/cache.py`.

A tile's bytes are fixed for a given key until the theme's style is
recompiled, so the only question is how a client learns that a recompile
happened. That splits requests in two:

- **versioned** (`?v=N`) -- the URL names one compiled-style generation, so
  its bytes can never change. A recompile bumps `v`, which makes the old
  URLs unreachable rather than stale, and `immutable` additionally stops
  browsers revalidating them on a plain reload.
- **unversioned** -- a URL typed into a tab, or a non-GUI client. A
  recompile cannot reach the client, so these get a short lifetime that
  bounds the staleness window.

Only 2xx tile responses get these headers. An error is left uncached, so a
tile that starts working after a fix is not shadowed by a cached failure.

With the `nocache` option on there is no browser tier either: tiles and
icons are `no-store`, with no ETag to revalidate. The style generation in
`?v=` is per process, so after a restart it repeats a number an
`immutable` response was already cached under -- a stale tile the browser
never asks for again.
"""

from __future__ import annotations

import hashlib

from lib import config

#: The conventional "forever" for a content-addressed URL: 365 days.
IMMUTABLE_MAX_AGE = 31_536_000

#: Unversioned URLs. Long enough that panning back over an area within a
#: session costs nothing, short enough that a recompile shows up without a
#: hard reload.
DEFAULT_MAX_AGE = 300


def enabled() -> bool:
    return not config.opt('nocache')


NO_STORE = {'Cache-Control': 'no-store'}


def max_age() -> int:
    """`max-age` for unversioned tile URLs.

    Read per call rather than at import so `/internal/reload` can change it
    without restarting the process.
    """
    value = config.opt('tile_max_age_s', DEFAULT_MAX_AGE)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_MAX_AGE


def tile_etag(data: bytes) -> str:
    """A strong ETag for one tile's bytes.

    Over the bytes, not over the address plus a generation counter: the
    generation is per *process*, so two containers behind a proxy restart
    at different times and would hand out different tags for identical
    tiles, making every client revalidation miss. Hashing costs a few
    microseconds on 10 KB and makes the tag the same everywhere.
    """
    return f'"{hashlib.sha256(data).hexdigest()[:32]}"'


def is_not_modified(if_none_match: str | None, etag: str) -> bool:
    """Whether to answer 304 rather than send the body again.

    `If-None-Match` uses *weak* comparison (RFC 9110 8.2.2), so `W/"x"` and
    `"x"` are the same representation here and the prefix is stripped from
    both sides. `*` matches whatever exists.

    Comma splitting is naive and deliberately so: an entity-tag may contain
    a comma, but every tag emitted here is a hex digest that cannot. A
    client tag containing one can only fail to match -- a 200 where a 304
    would have done, never a 304 where the body differs.
    """
    if not if_none_match:
        return False
    candidates = if_none_match.split(',')
    if any(candidate.strip() == '*' for candidate in candidates):
        return True
    wanted = _strip_weak(etag)
    return any(_strip_weak(candidate.strip()) == wanted for candidate in candidates)


def _strip_weak(value: str) -> str:
    value = value.strip()
    return value[2:] if value.startswith('W/') else value


def headers(etag: str, *, versioned: bool) -> dict[str, str]:
    """Cache headers for a 2xx tile response."""
    if not enabled():
        return dict(NO_STORE)
    if versioned:
        control = f'public, max-age={IMMUTABLE_MAX_AGE}, immutable'
    else:
        control = f'public, max-age={max_age()}'
    return {
        'Cache-Control': control,
        'ETag': etag,
        # Tiles are public and cross-origin by design; the CORS middleware
        # sets the allow-origin header, this tells a shared cache that the
        # answer does not vary by it.
        'Vary': 'Accept-Encoding',
    }
