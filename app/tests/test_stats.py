"""The request log and the daily figures.

What is pinned is what nothing else would show: IP addresses and search
terms outliving `request_log_days`, a day dropped before it was counted, a
day counted twice by two containers, a day counted before its last rows
were flushed, a cache hit rate or a distinct-IP count that adds up across
kinds.
"""

from __future__ import annotations

import datetime
import io
import time
import types

import pytest

from lib import stats
from web import stats as web_stats

SCHEMA = 'test_stats'
UTC = datetime.UTC


def retention(monkeypatch, days):
    monkeypatch.setattr(stats.config, 'opt', lambda path, default=None:
                        days if path == 'request_log_days' else default)


@pytest.fixture
def store(db, monkeypatch):
    from psycopg import sql
    drop = sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(SCHEMA))
    db.execute(drop)
    monkeypatch.setattr(stats, 'SCHEMA', SCHEMA)
    retention(monkeypatch, stats.MAX_RETENTION_DAYS)
    yield db
    db.execute(drop)


def at(day: datetime.date, hour: int = 12) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def row(ts, kind='tiles', key_id=None, status=200, ms=10.0, cache='hit', ip='192.0.2.1',
        terms=None):
    return (ts, kind, key_id, status, ms, cache, ip, terms)


# --- the database --------------------------------------------------------

def test_a_finished_day_is_counted_per_kind_and_over_all(store):
    today = datetime.date(2026, 10, 28)
    day = today - datetime.timedelta(days=1)
    stats.ensure(store, day)
    stats.write_requests([
        row(at(day), ms=10, ip='192.0.2.1'),
        row(at(day), cache='miss', ms=200, ip='192.0.2.2'),
        row(at(day), status=404, cache=None, ip='192.0.2.1'),
        row(at(day), kind='search', cache=None, ip='192.0.2.1', terms='Kiel'),
        row(at(today), ip='192.0.2.9'),                    # today: not finished
    ])
    assert stats.roll_up(store, today) == [day]
    got = {r[0]: r[1:] for r in store.execute(
        f'select kind, requests, errors, cache_hits, cache_misses, ips'
        f' from {SCHEMA}.daily_stats').fetchall()}
    assert got == {'tiles': (3, 1, 1, 1, 2), 'search': (1, 0, 0, 0, 1),
                   'all': (4, 1, 1, 1, 2)}                # 2 distinct IPs, not 3
    assert stats.roll_up(store, today) == []               # counted once


@pytest.mark.parametrize('days', [1, 3, 7])
def test_ips_and_search_terms_are_gone_after_request_log_days(store, monkeypatch, days):
    """The whole point of the table's shape: a day older than
    `request_log_days` is dropped, its partition or its rows in the default
    partition. With 1 only today is left."""
    retention(monkeypatch, days)
    today = datetime.date(2026, 10, 28)
    old = today - datetime.timedelta(days=days)            # first day too old
    kept = today - datetime.timedelta(days=days - 1)       # last day kept
    stats.ensure(store, old)                               # partitions old .. old+2
    stats.ensure(store, today)
    stats.write_requests([row(at(old), terms='alt'), row(at(kept), terms='neu')])
    stats.write_requests([row(at(old - datetime.timedelta(days=5)), terms='default')])

    counted, dropped = stats.daily(today)
    assert old in counted
    assert (kept in counted) == (kept < today)             # today is not finished
    assert f'request_log_{old:%Y%m%d}' in dropped
    assert f'request_log_{kept:%Y%m%d}' not in dropped
    left = [r[0] for r in store.execute(f'select terms from {SCHEMA}.request_log').fetchall()]
    assert left == ['neu']
    counted_days = [r[0] for r in store.execute(
        f"select day from {SCHEMA}.daily_stats where kind = 'all' order by day").fetchall()]
    assert old in counted_days                             # counted before it went


@pytest.mark.parametrize('days', [0, 8, '7', 2.5, True, None])
def test_request_log_days_outside_one_to_seven_is_refused(monkeypatch, days):
    """The privacy policy states the period; a typo must not keep IPs longer."""
    retention(monkeypatch, days)
    with pytest.raises(ValueError, match='request_log_days'):
        stats.retention_days()


def test_two_containers_running_daily_count_a_day_once(store, monkeypatch):
    """Every app container runs `daily`. The second may read the day as
    uncounted just before the first writes it; its insert must neither fail
    nor double the count."""
    today = datetime.date(2026, 10, 28)
    day = today - datetime.timedelta(days=1)
    stats.ensure(store, day)
    stats.write_requests([row(at(day))])
    stats.write_host_sample({'ts': at(day), 'cpu': 1.0, 'mem_used': 1, 'mem_total': 2,
                             'disk_used': 1, 'disk_total': 2})
    stats.daily(today)
    monkeypatch.setattr(stats, '_days', lambda conn, source, done, t: [day])
    stats.roll_up(store, today)
    assert store.execute(f"select count(*) from {SCHEMA}.daily_stats where kind = 'all'"
                         ).fetchone()[0] == 1
    assert store.execute(f'select count(*) from {SCHEMA}.daily_host').fetchone()[0] == 1


def test_the_export_has_a_line_per_day_and_the_cost_per_1000(store, monkeypatch):
    today = datetime.date(2026, 11, 2)
    day = datetime.date(2026, 10, 30)
    stats.ensure(store, day)
    stats.write_requests([row(at(day)) for _ in range(3)] + [row(at(day), cache='miss')])
    stats.write_host_sample({'ts': at(day), 'cpu': 40.0, 'mem_used': 2 * 1024 ** 3,
                             'mem_total': 8 * 1024 ** 3, 'disk_used': 1, 'disk_total': 2})
    stats.roll_up(store, today)
    monkeypatch.setattr(stats.config, 'opt', lambda path, default=None:
                        40 if path == 'monthly_cost_eur' else default)
    out = io.StringIO()
    totals = stats.export(datetime.date(2026, 10, 1), out)
    lines = out.getvalue().splitlines()
    assert lines[0].startswith('day;tiles;wms;search;errors;cache_hit_rate')
    assert lines[1].startswith('2026-10-30;4;0;0;0;0.750;')
    assert ';40.00;40.00;2.00;8.00;' in lines[1]
    assert totals['requests'] == 4
    assert totals['eur_per_1000'] == 10000.0


# --- the app's side ------------------------------------------------------

class FakeRequest:
    def __init__(self, path='/xyz/std/1/0/0.png', host='192.0.2.7', **state):
        self.url = types.SimpleNamespace(path=path)
        self.client = types.SimpleNamespace(host=host)
        self.state = types.SimpleNamespace(**state)


@pytest.fixture
def rows():
    web_stats._rows.clear()
    yield web_stats._rows
    web_stats._rows.clear()


def test_the_day_before_is_counted_only_after_every_process_flushed_it():
    """Rows of 23:59:30 are flushed up to `FLUSH_S` later; counting at
    00:00 would miss them for good."""
    midnight = datetime.datetime(2026, 10, 28, tzinfo=UTC)
    early = midnight + datetime.timedelta(seconds=web_stats.FLUSH_S)
    late = midnight + datetime.timedelta(seconds=web_stats.DAILY_AFTER_S)
    assert web_stats.DAILY_AFTER_S > web_stats.FLUSH_S
    assert web_stats.daily_day(early) == datetime.date(2026, 10, 27)
    assert web_stats.daily_day(late) == datetime.date(2026, 10, 28)


def test_a_failed_daily_run_is_retried(monkeypatch):
    def fail(day):
        raise RuntimeError('database down')
    monkeypatch.setattr(web_stats.store, 'daily', fail)
    assert web_stats.run_daily(datetime.date(2026, 10, 28)) is False


def test_only_api_requests_are_logged(rows):
    web_stats.record(FakeRequest(path='/health'), 200, 1.0)
    web_stats.record(FakeRequest(key_scope='tiles', cache='hit'), 200, 1.0)
    web_stats.record(FakeRequest(path='/wms', key_scope='tiles'), 200, 1.0)
    web_stats.record(FakeRequest(path='/search', key_scope='search', search_terms='Kiel'), 422, 1.0)
    assert [(r[1], r[3], r[5], r[6], r[7]) for r in rows] == [
        ('tiles', 200, 'hit', '192.0.2.7', None),
        ('wms', 200, None, '192.0.2.7', None),
        ('search', 422, None, '192.0.2.7', 'Kiel'),
    ]


def test_search_terms_are_the_text_fields_cut_short():
    assert web_stats.terms_of({'mode': 'phrase', 'text': 'Restaurant Kiel'}) == 'Restaurant Kiel'
    assert web_stats.terms_of({'mode': 'address', 'street': 'Holtenauer Straße',
                               'housenumber': '12', 'city': 'Kiel'}) == \
        'Holtenauer Straße | 12 | Kiel'
    assert web_stats.terms_of({'mode': 'point', 'near': [10, 54]}) is None
    assert len(web_stats.terms_of({'text': 'x' * 1000})) == web_stats.TERMS_MAX


def test_a_failed_flush_drops_its_rows_and_never_grows_the_buffer(rows, monkeypatch):
    """The log is not the invoice: with the database down it costs rows,
    never the server's memory."""
    def down(_rows):
        raise OSError('database down')
    monkeypatch.setattr(web_stats.store, 'write_requests', down)
    web_stats.record(FakeRequest(key_scope='tiles'), 200, 1.0)
    web_stats.flush()
    assert not rows
    for _ in range(web_stats.MAX_BUFFERED + 5):
        web_stats.record(FakeRequest(key_scope='tiles'), 200, 1.0)
    assert len(rows) == web_stats.MAX_BUFFERED


def test_the_host_sample_reads_proc():
    sampler = web_stats.HostSampler()
    first = sampler.sample()
    assert first['cpu'] is None                            # no interval yet
    assert 0 < first['mem_used'] < first['mem_total']
    assert 0 <= first['disk_used'] <= first['disk_total'] and first['disk_total'] > 0
    time.sleep(0.1)                                        # let the jiffies move
    assert 0 <= sampler.sample()['cpu'] <= 100
