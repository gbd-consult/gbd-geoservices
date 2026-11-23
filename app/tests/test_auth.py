"""The key check and the usage count.

One test per cell of the auth matrix. The failures pinned here are silent:
a prefix of a key accepted as the key, a disabled or expired key still
let through, a request counted under the wrong scope or not at all -- the
invoice is the only place that shows it.
"""

from __future__ import annotations

import datetime
import types

import pytest
from conftest import key_rows
from fastapi import HTTPException

from lib import keys as store
from web import auth

KEY = 'k-production-0123456789'
OTHER = 'k-demo-9876543210'


class FakeRequest:
    """Only what `auth` reads and writes: headers, query params, state."""

    def __init__(self, headers=None, query=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.query_params = query or {}
        self.state = types.SimpleNamespace()


def request(**kw):
    return FakeRequest(**kw)


# --- the carriers --------------------------------------------------------

def test_a_bearer_header_is_accepted(keys):
    keys([KEY])
    assert auth.check(request(headers={'Authorization': f'Bearer {KEY}'}), 'tiles').name == KEY


def test_a_query_parameter_is_accepted(keys):
    """The only carrier an <img> tag, a tile template or QGIS can send."""
    keys([KEY])
    assert auth.check(request(query={'key': KEY}), 'tiles').name == KEY


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


def test_a_key_with_no_scopes_carries_tiles_and_search(keys):
    # The shorthand form. A deployment that wants a narrow key says so.
    keys([KEY])
    for scope in ('tiles', 'search'):
        assert auth.check(request(query={'key': KEY}), scope)


def test_a_key_with_no_scopes_does_not_open_the_devtools(keys):
    """The viewer is ours: a customer's key added without --scopes must not
    reach it, so `devtools` is never implied."""
    keys([KEY, {'key': OTHER, 'scopes': ['devtools']}])
    with pytest.raises(HTTPException) as excinfo:
        auth.requires_devtools(request(query={'key': KEY}))
    assert excinfo.value.status_code == 403
    assert auth.requires_devtools(request(query={'key': OTHER})).name == OTHER


# --- the substring bug ---------------------------------------------------

def test_a_prefix_of_a_key_is_not_a_key(keys):
    """Keys from the environment were once a string, and `"a" in "abc123"`
    is True: every one-character key authenticated."""
    keys([KEY])
    assert auth.check(request(query={'key': KEY}), 'tiles').name == KEY
    for wrong in ('k', 'k-p', KEY[:-1], KEY + 'x'):
        with pytest.raises(HTTPException) as excinfo:
            auth.check(request(query={'key': wrong}), 'tiles')
        assert excinfo.value.status_code == 401


def test_the_lookup_is_by_digest_and_no_record_holds_a_key(keys):
    """A dict lookup compares with `==`, which leaks how much of the
    compared value matched -- harmless only because the value is the
    SHA-256 of the presented key, not the key."""
    import dataclasses
    import inspect
    keys([KEY])
    assert 'digest(' in inspect.getsource(auth.match)
    assert list(auth.configured()) == [store.digest(KEY)]
    assert 'key' not in {f.name for f in dataclasses.fields(auth.Key)}


# --- disabled and expired ------------------------------------------------

def test_a_disabled_key_is_403(keys):
    keys([{'key': KEY, 'disabled': True}])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'tiles')
    assert excinfo.value.status_code == 403
    assert 'disabled' in excinfo.value.detail


def test_an_expired_key_is_403(keys):
    yesterday = store.today() - datetime.timedelta(days=1)
    keys([{'key': KEY, 'expires': yesterday}])
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'tiles')
    assert excinfo.value.status_code == 403
    assert 'expired' in excinfo.value.detail


def test_a_key_is_valid_through_its_last_day(keys):
    """`expires` is the last valid day: a trial key added for 30 days works
    on the 30th."""
    keys([{'key': KEY, 'expires': store.today()}])
    assert auth.check(request(query={'key': KEY}), 'tiles')


# --- reading the records -------------------------------------------------

def test_the_records_are_reread_after_the_ttl(keys, monkeypatch):
    """A key disabled with `manage.py` is refused without a reload."""
    now = [1000.0]
    monkeypatch.setattr(auth.time, 'monotonic', lambda: now[0])
    keys([KEY])
    assert auth.check(request(query={'key': KEY}), 'tiles')
    monkeypatch.setattr(auth, '_records',
                        lambda: auth.records_of(key_rows([{'key': KEY, 'disabled': True}])))
    assert auth.check(request(query={'key': KEY}), 'tiles')       # still cached
    now[0] += auth.KEYS_TTL_S + 1
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(query={'key': KEY}), 'tiles')
    assert excinfo.value.status_code == 403


def test_a_failed_read_keeps_the_records_there_are(keys, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth.time, 'monotonic', lambda: now[0])
    keys([KEY])
    assert auth.check(request(query={'key': KEY}), 'tiles')

    def down():
        raise OSError('database down')
    monkeypatch.setattr(auth, '_records', down)
    now[0] += auth.KEYS_TTL_S + 1
    assert auth.check(request(query={'key': KEY}), 'tiles')


def test_no_records_read_yet_is_503_not_open(keys, monkeypatch):
    """No records would be "no keys registered", which is open access: a
    database that is down must not open the server."""
    keys([KEY])

    def down():
        raise OSError('database down')
    monkeypatch.setattr(auth, '_records', down)
    auth.reset()
    with pytest.raises(HTTPException) as excinfo:
        auth.check(request(), 'tiles')
    assert excinfo.value.status_code == 503


# --- usage ---------------------------------------------------------------

def counted(monkeypatch):
    written = {}
    monkeypatch.setattr(auth.store, 'add_usage', lambda counts: written.update(
        {slot: dict(scopes) for slot, scopes in counts.items()}))
    auth.flush_usage()
    return written


def served(scope, status=200, **kw):
    """A request through the route's key check, counted with its status."""
    req = request(**kw)
    try:
        auth.requires(scope)(req)
    except HTTPException as exc:
        status = exc.status_code
    auth.count(req, status)
    return status


def test_a_key_with_both_scopes_counts_tiles_and_search_apart(keys, monkeypatch):
    keys([{'key': KEY, 'scopes': ['tiles', 'search']}])
    for scope, n in (('tiles', 3), ('search', 2)):
        for _ in range(n):
            served(scope, query={'key': KEY})
    month = store.month_of(store.today())
    assert counted(monkeypatch) == {(1, month): {'tiles': 3, 'search': 2}}


def test_a_failed_request_is_an_error_not_a_tile_or_search(keys, monkeypatch):
    """A malformed search (422) or a tile outside the pyramid (404) is the
    key's error, not a request to invoice."""
    keys([KEY])
    served('search', 422, query={'key': KEY})
    served('tiles', 404, query={'key': KEY})
    served('tiles', query={'key': KEY})
    month = store.month_of(store.today())
    assert counted(monkeypatch) == {(1, month): {'errors': 2, 'tiles': 1}}


def test_a_key_s_refusal_is_its_error(keys, monkeypatch):
    """A registered key refused for its scope, referrer, rate, expiry or
    because it is disabled: the request is the key's, so is the error."""
    keys([{'key': KEY, 'scopes': ['tiles']}, {'key': OTHER, 'disabled': True}])
    assert served('search', query={'key': KEY}) == 403
    assert served('tiles', query={'key': OTHER}) == 403
    month = store.month_of(store.today())
    assert counted(monkeypatch) == {(1, month): {'errors': 1}, (2, month): {'errors': 1}}


def test_no_key_or_an_unknown_one_is_counted_for_nobody(keys, monkeypatch):
    keys([KEY])
    assert served('tiles') == 401
    assert served('tiles', query={'key': 'nope'}) == 401
    assert counted(monkeypatch) == {}


def test_status_is_not_counted(keys, monkeypatch):
    keys([KEY])
    req = request(query={'key': KEY})
    auth.requires_key(req)
    auth.count(req, 200)
    assert counted(monkeypatch) == {}


def test_a_failed_flush_keeps_its_counts(keys, monkeypatch):
    """The counts are the invoice: a database blip must not lose them."""
    keys([KEY])
    served('tiles', query={'key': KEY})

    def down(counts):
        raise OSError('database down')
    monkeypatch.setattr(auth.store, 'add_usage', down)
    auth.flush_usage()
    served('tiles', query={'key': KEY})
    month = store.month_of(store.today())
    assert counted(monkeypatch) == {(1, month): {'tiles': 2}}


# --- referrers -----------------------------------------------------------

def test_a_referrer_allowlist_admits_a_match(keys):
    keys([{'key': KEY, 'referrers': ['https://maps.example.de/*']}])
    got = auth.check(request(query={'key': KEY},
                             headers={'Referer': 'https://maps.example.de/karte'}), 'tiles')
    assert got.name == KEY


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


# --- the dependency ------------------------------------------------------

def test_requires_refuses_an_unknown_scope():
    with pytest.raises(ValueError, match='unknown scope'):
        auth.requires('everything')


def test_requires_builds_a_dependency_for_each_scope():
    for scope in auth.SCOPES:
        assert callable(auth.requires(scope))


# --- a presented key that is not ASCII -----------------------------------

def test_a_non_ascii_key_is_refused_not_a_500(keys):
    """The presented key is whatever a client sent, so a comparison that
    raised on non-ASCII made `?key=Ünicode` an unhandled exception -- a 500,
    from an unauthenticated request, on the one code path whose whole job
    is to refuse them. The digest is over UTF-8, an ordinary mismatch.
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
    assert auth.Key(id=1, name=KEY, referrers=('https://maps.example.de/*',)) \
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
    assert not auth.Key(id=1, name=KEY, referrers=('https://maps.example.de/*',)) \
        .allows_referrer(referrer)
