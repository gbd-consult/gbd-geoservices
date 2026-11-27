"""The key store, against the dev database in a scratch schema.

What is pinned is what no request would show: a key written in clear, a
usage flush that overwrites instead of adding, an export that leaves out a
customer with no requests.
"""

from __future__ import annotations

import datetime
import io

import pytest

from lib import keys

SCHEMA = 'test_keys'
KEY = 'k-0123456789abcdefghijklmnopqrstuvwxyzABCDE'


@pytest.fixture
def store(db, monkeypatch):
    from psycopg import sql
    drop = sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(SCHEMA))
    db.execute(drop)
    monkeypatch.setattr(keys, 'SCHEMA', SCHEMA)
    monkeypatch.setenv('KEY_REQUEST_SECRET', 'test-secret')
    yield db
    db.execute(drop)


def test_no_table_is_no_keys(store):
    """The app reads a database no key was ever added to as open."""
    assert keys.load() == []


def test_a_key_is_stored_only_as_its_digest(store):
    keys.add('kiel', KEY, customer='Stadt Kiel', scopes=['tiles'])
    dump = str(store.execute(f'select * from {SCHEMA}.api_key').fetchall())
    assert KEY not in dump
    assert keys.digest(KEY) in dump
    assert KEY not in str(keys.listing())


def test_an_empty_key_is_refused(store):
    with pytest.raises(ValueError, match='no key'):
        keys.add('x', '')


def test_an_unknown_scope_is_refused(store):
    with pytest.raises(ValueError, match='unknown scope'):
        keys.add('x', KEY, scopes=['tile'])


def test_a_trial_key_expires_after_the_trial(store):
    keys.add('demo', KEY, trial=True)
    assert keys.load()[0]['expires'] == keys.today() + datetime.timedelta(days=keys.TRIAL_DAYS)


def test_disable_and_enable(store):
    keys.add('kiel', KEY)
    assert keys.set_disabled('kiel', True)
    assert keys.load()[0]['disabled'] is True
    assert keys.set_disabled('kiel', False)
    assert keys.load()[0]['disabled'] is False
    assert not keys.set_disabled('nobody', True)


def test_usage_adds_up_and_exports_every_key(store):
    """Two flushes of the same month add; a key with no requests is in the
    export with zeros, so the invoice run sees it."""
    keys.add('kiel', KEY, customer='Stadt Kiel')
    keys.add('idle', KEY + 'x')
    kiel = next(row['id'] for row in keys.load() if row['name'] == 'kiel')
    october = datetime.date(2026, 10, 1)
    keys.add_usage({(kiel, october): {'tiles': 100, 'search': 3, 'errors': 4}})
    keys.add_usage({(kiel, october): {'tiles': 20, 'errors': 1}})
    keys.add_usage({(kiel, datetime.date(2026, 11, 1)): {'tiles': 7}})

    out = io.StringIO()
    assert keys.export_usage(datetime.date(2026, 10, 1), out) == 2
    assert out.getvalue().splitlines() == [
        'key;customer;month;tiles;search;errors',
        'idle;;2026-10;0;0;0',
        'kiel;Stadt Kiel;2026-10;120;3;5',
    ]


def clear(store) -> list[tuple]:
    return store.execute(f'select email, organisation from {SCHEMA}.key_request'
                         ' order by id').fetchall()


def test_key_requests_stop_at_the_limit_and_go_when_done(store):
    """The limit is what a bot past the honeypot can fill; done frees the
    place and, without consent, deletes the address at once rather than
    after the seven days."""
    first = keys.request_add('a@example.org', 'A GmbH', False, limit=2)
    keys.request_add('b@example.org', None, False, limit=2)
    assert keys.request_add('c@example.org', None, False, limit=2) is None
    assert [r[2] for r in keys.requests()] == ['a@example.org', 'b@example.org']
    assert keys.request_done(first)
    assert not keys.request_done(first)
    assert [r[2] for r in keys.requests()] == ['b@example.org']
    assert clear(store)[0] == (None, None)
    assert keys.request_add('c@example.org', None, False, limit=2) is not None


def test_an_address_already_waiting_takes_no_second_place(store):
    first = keys.request_add('a@example.org', 'A GmbH', False, limit=2)
    assert keys.request_add('A@Example.org', None, False, limit=2) == first
    assert keys.request_add('b@example.org', None, False, limit=2) is not None
    assert len(keys.requests()) == 2


def test_a_repeat_is_recognised_after_the_clear_address_is_gone(store):
    """Without consent nothing in clear is left once the first request is
    done, so the repeat can only have been found by the HMACs."""
    keys.request_done(keys.request_add('a@example.org', 'A GmbH', False, limit=9))
    keys.request_add('A@EXAMPLE.org ', None, False, limit=9)
    keys.request_add('b@example.org', 'a  gmbh', False, limit=9)
    keys.request_add('c@example.org', 'C AG', False, limit=9)
    assert [(r[2], r[5]) for r in keys.requests()] == [
        ('A@EXAMPLE.org ', True), ('b@example.org', True), ('c@example.org', False)]


def test_repeats_are_found_by_the_hmacs_alone():
    """The requirement: a repeat is looked up by the hashes, never by the
    address or name in clear."""
    assert 'email ' not in keys.REPEAT.replace('email_hash', '')
    assert 'organisation' not in keys.REPEAT


def test_consent_keeps_the_contact_until_withdrawn(store):
    keys.request_done(keys.request_add('a@example.org', 'A GmbH', True, limit=9))
    keys.request_done(keys.request_add('b@example.org', 'B AG', False, limit=9))
    assert [c[1:] for c in keys.contacts()] == [('a@example.org', 'A GmbH')]
    assert keys.contact_withdraw('A@example.org ') == 1
    assert keys.contacts() == []
    assert clear(store) == [(None, None), (None, None)]
    assert keys.contact_withdraw('a@example.org') == 1   # the hashes stay
    assert keys.requests() == []


def test_the_periods_without_consent_with_it_and_of_the_hashes(store):
    today = datetime.date(2026, 11, 25)
    keys.ensure(store)
    for days, email, consent in ((7, 'open@x.de', False), (6, 'kept@x.de', False),
                                 (7, 'offer@x.de', True), (90, 'late@x.de', True),
                                 (365, 'gone@x.de', False)):
        store.execute(f'insert into {SCHEMA}.key_request (ts, email, email_hash, consented)'
                      ' values (%s, %s, %s, case when %s then now() end)',
                      (today - datetime.timedelta(days=days), email, keys._hmac(email), consent))
    keys.purge_requests(store, today, 7)
    assert [r[0] for r in clear(store)] == [None, 'kept@x.de', 'offer@x.de', None]
    assert [r[2] for r in keys.requests()] == ['kept@x.de']


def test_no_secret_no_hmac(monkeypatch):
    """An unkeyed hash of an address is undone with a list of addresses."""
    monkeypatch.delenv('KEY_REQUEST_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='KEY_REQUEST_SECRET'):
        keys._hmac('a@example.org')
