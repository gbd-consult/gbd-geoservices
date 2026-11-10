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


def test_key_requests_stop_at_the_limit_and_go_when_done(store):
    """The limit is what a bot past the honeypot can fill; done deletes the
    address at once rather than after the seven days."""
    first = keys.request_add('a@example.org', 'A GmbH', limit=2)
    keys.request_add('b@example.org', None, limit=2)
    assert keys.request_add('c@example.org', None, limit=2) is None
    assert [r[2] for r in keys.requests()] == ['a@example.org', 'b@example.org']
    assert keys.request_done(first)
    assert not keys.request_done(first)
    assert [r[2] for r in keys.requests()] == ['b@example.org']
