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


@pytest.fixture
def trials(store, monkeypatch):
    monkeypatch.setenv('TRIAL_EMAIL_SECRET', 'test-secret')
    return store


def test_a_trial_key_opens_the_api_and_the_viewer_through_tomorrow(trials):
    key = keys.issue_trial('a@example.org', per_day=5)
    [record] = keys.load()
    assert record['hash'] == keys.digest(key)
    assert record['scopes'] == ['tiles', 'search', 'devtools']
    assert record['expires'] == keys.today() + datetime.timedelta(days=1)


def test_an_address_gets_one_trial_key_however_it_is_written(trials):
    assert keys.issue_trial('a@example.org', per_day=5) not in ('used', 'full')
    assert keys.issue_trial(' A@Example.ORG ', per_day=5) == 'used'
    assert len(keys.load()) == 1


def test_the_daily_cap_does_not_use_up_the_address(trials):
    """Refused for the day, the address must still get its key later."""
    keys.issue_trial('a@example.org', per_day=1)
    assert keys.issue_trial('b@example.org', per_day=1) == 'full'
    assert keys.issue_trial('b@example.org', per_day=2) not in ('used', 'full')


def test_the_address_is_stored_only_as_a_keyed_hash(trials, monkeypatch):
    """A plain SHA-256 of an address is found again by hashing a guess."""
    keys.issue_trial('a@example.org', per_day=5)
    dump = str(trials.execute(f'select * from {SCHEMA}.trial_email').fetchall()) + str(keys.load())
    assert 'example.org' not in dump
    assert keys.digest('a@example.org') not in dump
    monkeypatch.setenv('TRIAL_EMAIL_SECRET', 'another')
    assert keys.email_hash('a@example.org') not in dump


def test_no_secret_issues_no_key(store, monkeypatch):
    monkeypatch.delenv('TRIAL_EMAIL_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='TRIAL_EMAIL_SECRET'):
        keys.issue_trial('a@example.org', per_day=5)
