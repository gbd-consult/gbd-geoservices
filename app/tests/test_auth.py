"""The key check.

One test per cell of the auth matrix. The failures pinned here are silent:
keys compared with `in` rather than `compare_digest`, and -- because the
value can arrive from the environment as a *string* -- that `in` turned
into a substring test, so the key "a" authenticated against a configured
key of "abc123".
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from web import auth

KEY = 'k-production-0123456789'
OTHER = 'k-demo-9876543210'


@pytest.fixture
def keys(monkeypatch):
    """Install a set of key records and clear the caches around the test."""
    def install(records):
        monkeypatch.setattr(auth.config, 'opt',
                            lambda path, default=None: records
                            if path == 'keys' else default)
        auth.reset()
        return records
    yield install
    auth.reset()


class FakeRequest:
    """Only what `auth` reads: headers, query params, client."""

    def __init__(self, headers=None, query=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.query_params = query or {}


def request(**kw):
    return FakeRequest(**kw)


# --- the carriers --------------------------------------------------------

def test_a_bearer_header_is_accepted(keys):
    keys([KEY])
    assert auth.check(request(headers={'Authorization': f'Bearer {KEY}'}), 'tiles').key == KEY


def test_a_query_parameter_is_accepted(keys):
    """The only carrier an <img> tag, a tile template or QGIS can send."""
    keys([KEY])
    assert auth.check(request(query={'key': KEY}), 'tiles').key == KEY


def test_the_query_parameter_is_only_lowercase_key(keys):
    """`?KEY=` was accepted while Caddy's log filter deletes only `key`, so
    that spelling put the key into caddy.log in clear."""
    keys([KEY])
    for name in ('KEY', 'Key'):
        with pytest.raises(HTTPException) as excinfo:
            auth.check(request(query={name: KEY}), 'tiles')
        assert excinfo.value.status_code == 401


def test_the_carriers_are_tried_in_order(keys):
    keys([KEY, OTHER])
    seen = auth.presented(request(headers={'Authorization': f'Bearer {KEY}'},
                                  query={'key': OTHER}))
    assert seen == KEY


def test_an_empty_bearer_is_not_a_key(keys):
    keys([KEY])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(headers={'Authorization': 'Bearer   '}), 'tiles')
    assert excinfo.value.status_code == 401


# --- refusals ------------------------------------------------------------

def test_no_key_is_401(keys):
    """401, not 403: 403 means "identified and not allowed", which is a
    different thing for a client to retry."""
    keys([KEY])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(), 'tiles')
    assert excinfo.value.status_code == 401


def test_a_wrong_key_is_401(keys):
    keys([KEY])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': 'nope'}), 'tiles')
    assert excinfo.value.status_code == 401


def test_a_refusal_never_echoes_what_was_sent(keys):
    """An error body is a place a key ends up in a log or a screenshot."""
    keys([KEY])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': 'secret-typo-abc'}), 'tiles')
    assert 'secret-typo-abc' not in str(excinfo.value.detail)


def test_a_real_key_without_the_scope_is_403(keys):
    keys([{'key': KEY, 'scopes': ['tiles']}])
    assert auth.check(request(query={'key': KEY}), 'tiles')
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'search')
    assert excinfo.value.status_code == 403


def test_a_key_with_no_scopes_carries_every_scope(keys):
    # The shorthand form. A deployment that wants a narrow key says so.
    keys([KEY])
    for scope in auth.SCOPES:
        assert auth.check(request(query={'key': KEY}), scope)


# --- the substring bug ---------------------------------------------------

def test_a_prefix_of_a_key_is_not_a_key(keys):
    """The reason `_records` coerces to a list.

    `GEOSERVICES_KEYS=abc123` reaches config as the *string* `abc123`, and
    `"a" in "abc123"` is True. Every one-character key authenticated.
    """
    keys(KEY)                                  # a bare string, as from the environment
    assert auth.check(request(query={'key': KEY}), 'tiles').key == KEY
    for wrong in ('k', 'k-p', KEY[:-1], KEY + 'x'):
        with pytest.raises(HTTPException) as excinfo:
            auth.check(request(query={'key': wrong}), 'tiles')
        assert excinfo.value.status_code == 401


def test_a_single_mapping_is_also_coerced(keys):
    keys({'key': KEY, 'scopes': ['tiles']})
    assert auth.check(request(query={'key': KEY}), 'tiles').key == KEY


def test_the_comparison_is_constant_time():
    """Checked by reading the code.

    A dict lookup would compare with `==`, which returns as soon as two
    bytes differ and so leaks the length of the shared prefix.
    """
    import inspect
    source = inspect.getsource(auth.match)
    assert 'compare_digest' in source
    assert 'return' not in source.split('for record')[1].split('found = record')[0]


# --- referrers -----------------------------------------------------------

def test_a_referrer_allowlist_admits_a_match(keys):
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    got = auth.check(request(query={'key': KEY},
                             headers={'Referer': 'https://maps.example.de/karte'}), 'tiles')
    assert got.key == KEY


def test_a_referrer_not_on_the_list_is_403(keys):
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY},
                           headers={'Referer': 'https://elsewhere.example/'}), 'tiles')
    assert excinfo.value.status_code == 403


def test_origin_is_preferred_over_referer(keys):
    """A browser sets Origin on the request that matters, and page content
    cannot forge it."""
    keys([{'key': KEY, 'referrers': ['https://maps.example.de*']}])
    assert auth.check(request(query={'key': KEY},
                              headers={'Origin': 'https://maps.example.de',
                                       'Referer': 'https://elsewhere.example/'}), 'tiles')


def test_an_allowlisted_key_with_no_referrer_at_all_is_refused(keys):
    """The allowlist bounds where a key may be used from, and a request
    that declines to say is not bounded."""
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'tiles')
    assert excinfo.value.status_code == 403


def test_no_allowlist_means_any_origin(keys):
    keys([KEY])
    assert auth.check(request(query={'key': KEY},
                              headers={'Origin': 'https://anywhere.example'}), 'tiles')


# --- rate ----------------------------------------------------------------

def test_over_the_rate_is_429(keys):
    keys([{'key': KEY, 'rate': 3}])
    for _ in range(3):
        assert auth.check(request(query={'key': KEY}), 'tiles')
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'tiles')
    assert excinfo.value.status_code == 429
    assert excinfo.value.headers['Retry-After']


def test_a_key_without_a_rate_is_unlimited(keys):
    keys([KEY])
    for _ in range(50):
        assert auth.check(request(query={'key': KEY}), 'tiles')


def test_one_key_s_rate_does_not_bound_another(keys):
    keys([{'key': KEY, 'rate': 1}, {'key': OTHER, 'rate': 1}])
    assert auth.check(request(query={'key': KEY}), 'tiles')
    assert auth.check(request(query={'key': OTHER}), 'tiles')


def test_the_window_slides(monkeypatch):
    limiter = auth.RateLimiter()
    now = [1000.0]
    monkeypatch.setattr(auth.time, 'monotonic', lambda: now[0])
    assert limiter.allow('k', 2) and limiter.allow('k', 2)
    assert not limiter.allow('k', 2)
    now[0] += auth.RATE_WINDOW_S + 1
    assert limiter.allow('k', 2)


# --- no keys at all ------------------------------------------------------

def test_no_keys_configured_is_open(keys):
    """The versioned default, and what a developer runs with.

    Refusing every request would make the dev stack unusable and the first
    thing anyone did would be to invent a key and commit it.
    """
    keys([])
    assert auth.open_access()
    assert auth.check(request(), 'tiles') is None


def test_an_open_server_is_not_silent(keys, caplog):
    keys([])
    with caplog.at_level('WARNING'):
        auth.warn_if_open()
    assert any('open' in record.message for record in caplog.records)


def test_a_configured_server_does_not_warn(keys, caplog):
    keys([KEY])
    with caplog.at_level('WARNING'):
        auth.warn_if_open()
    assert not caplog.records


def test_a_record_without_a_key_is_ignored_not_fatal(keys, caplog):
    with caplog.at_level('WARNING'):
        keys([{'scopes': ['tiles']}, KEY])
        assert [record.key for record in auth.configured()] == [KEY]
    assert caplog.records


# --- the dependency ------------------------------------------------------

def test_requires_refuses_an_unknown_scope():
    with pytest.raises(ValueError, match='unknown scope'):
        auth.requires('everything')


def test_requires_builds_a_dependency_for_each_scope():
    for scope in auth.SCOPES:
        assert callable(auth.requires(scope))


# --- a presented key that is not ASCII -----------------------------------

def test_a_non_ascii_key_is_refused_not_a_500(keys):
    """`secrets.compare_digest` on `str` raises TypeError the moment either
    side is not ASCII.

    The presented key is whatever a client sent, so `?key=Ünicode` was an
    unhandled exception -- a 500, from an unauthenticated request, on the
    one code path whose whole job is to refuse them. Both sides are encoded
    to UTF-8 now, which makes it an ordinary mismatch.
    """
    keys([KEY])
    assert auth.match('Ünicode') is None
    with pytest.raises(HTTPException) as caught:
        auth.check(request(query={'key': 'Ünicode'}), 'tiles')
    assert caught.value.status_code == 401


def test_a_non_ascii_configured_key_still_matches_itself(keys):
    """The other direction: a deployment that used a non-ASCII key would
    otherwise 500 on the request that should succeed."""
    keys(['schlüssel-0123456789'])
    assert auth.match('schlüssel-0123456789') is not None
    assert auth.match('schlussel-0123456789') is None


# --- the referrer allowlist against a real browser header ----------------

def test_the_documented_pattern_matches_an_origin_header(keys):
    """`Origin` is a bare origin -- no path, no trailing slash -- and
    `referrer_of` prefers it over `Referer`.

    The natural pattern, `https://maps.example.de/*`, matches a Referer and
    not an Origin, so a key's allowlist refused exactly the browser
    requests it exists for.
    """
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    assert auth.check(
        request(headers={'Origin': 'https://maps.example.de'},
                query={'key': KEY}), 'tiles') is not None


@pytest.mark.parametrize('referrer', [
    'https://maps.example.de',            # Origin
    'https://maps.example.de/',           # Origin with a slash
    'https://maps.example.de/app/',       # Referer
    'https://maps.example.de/app/i.html',
])
def test_every_spelling_of_the_allowed_site_passes(keys, referrer):
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    assert auth.Key(key=KEY, referrers=('https://maps.example.de/*',)) \
        .allows_referrer(referrer)


@pytest.mark.parametrize('referrer', [
    'https://maps.example.de.evil.com',
    'https://maps.example.de.evil.com/app',
    'http://maps.example.de',             # wrong scheme
    'https://other.example.de',
])
def test_a_lookalike_origin_is_still_refused(referrer):
    """The trailing-slash candidate must not widen the pattern: appending
    `/` to `https://maps.example.de.evil.com` must not make it match."""
    assert not auth.Key(key=KEY, referrers=('https://maps.example.de/*',)) \
        .allows_referrer(referrer)
