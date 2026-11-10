"""The request log and the daily figures, in the schema `service`.

    service.request_log   one row per API request: time, kind (tiles,
                          search, wms), key, status, duration, tile cache
                          hit or miss, client IP, search terms. Kept for
                          `request_log_days` days (1-7), then dropped whole.
    service.host_sample   CPU, RAM and disk of the host, once a minute.
                          Kept as long as the request log.
    service.daily_stats   per day and kind, and over all kinds as `all`:
                          requests (errors included), errors, cache hits and
                          misses, duration percentiles, distinct IPs and keys.
                          No IP and no search term; kept for good.
    service.daily_host    per day: CPU and RAM average and peak, disk used.

The IP addresses and search terms exist only in `request_log`, so deleting
it after `request_log_days` leaves no personal data behind; what lasts is
`daily_stats`, counted from it before it goes. `daily` does both and
creates the coming days' partitions; the app runs it at start and once a
day (`web/stats.py`).

`request_log` is partitioned by day: a day expires by dropping its table,
not by deleting millions of rows from the one the server is writing to. A
row for a day with no partition yet -- the app was down for days -- lands
in the default partition, which `daily` empties of expired rows too.

Every app container runs `daily`, so it is idempotent: a day counted by
another container is skipped (`on conflict do nothing`), a partition it
dropped is not dropped again.

`report_month`, run after `daily`, writes the month before as
`<data_dir>/stats/load-YYYY-MM.csv` once it is over -- the same CSV as
`stats-export` -- so the monthly figures lie ready without anyone running
the export. Written once, atomically, so two containers cannot leave half
a file.
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from psycopg import sql

from lib import config, db, keys
from lib.keys import SCHEMA

_log = logging.getLogger(__name__)

#: `request_log_days` may not exceed this: the privacy policy promises it.
#: Also how long a trial key request, with its e-mail address, is kept.
MAX_RETENTION_DAYS = 7

#: The request log's columns, in the order `write_requests` takes them.
REQUEST_COLUMNS = ('ts', 'kind', 'key_id', 'status', 'ms', 'cache', 'ip', 'terms')


def _t(name: str) -> sql.Identifier:
    return sql.Identifier(SCHEMA, name)


def retention_days() -> int:
    """The `request_log_days` option, refused outside 1..`MAX_RETENTION_DAYS`."""
    days = config.opt('request_log_days')
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_RETENTION_DAYS:
        raise ValueError(f'request_log_days must be a whole number from 1 to '
                         f'{MAX_RETENTION_DAYS}, got {days!r}')
    return days


def _partition(day: datetime.date) -> sql.Identifier:
    return _t(f'request_log_{day:%Y%m%d}')


def ensure(conn, today: datetime.date) -> None:
    """The tables, and the partitions of today and the two days after."""
    conn.execute(sql.SQL('create schema if not exists {}').format(sql.Identifier(SCHEMA)))
    conn.execute(sql.SQL("""
        create table if not exists {log} (
            ts      timestamptz not null,
            kind    text not null,
            key_id  integer,
            status  smallint not null,
            ms      real not null,
            cache   text,
            ip      inet,
            terms   text
        ) partition by range (ts)""").format(log=_t('request_log')))
    conn.execute(sql.SQL('create table if not exists {} partition of {} default').format(
        _t('request_log_default'), _t('request_log')))
    for offset in range(3):
        day = today + datetime.timedelta(days=offset)
        # Literals, not parameters: DDL takes no bind parameters.
        conn.execute(sql.SQL(
            'create table if not exists {} partition of {} for values from ({}) to ({})').format(
            _partition(day), _t('request_log'), sql.Literal(day.isoformat()),
            sql.Literal((day + datetime.timedelta(days=1)).isoformat())))
    conn.execute(sql.SQL("""
        create table if not exists {} (
            ts         timestamptz not null,
            cpu        real,
            mem_used   bigint,
            mem_total  bigint,
            disk_used  bigint,
            disk_total bigint
        )""").format(_t('host_sample')))
    conn.execute(sql.SQL("""
        create table if not exists {} (
            day           date not null,
            kind          text not null,
            requests      bigint not null,
            errors        bigint not null,
            cache_hits    bigint not null,
            cache_misses  bigint not null,
            ms_p50        real,
            ms_p95        real,
            ips           bigint not null,
            keys          bigint not null,
            primary key (day, kind)
        )""").format(_t('daily_stats')))
    conn.execute(sql.SQL("""
        create table if not exists {} (
            day         date primary key,
            cpu_avg     real,
            cpu_max     real,
            mem_avg     bigint,
            mem_max     bigint,
            mem_total   bigint,
            disk_used   bigint,
            disk_total  bigint
        )""").format(_t('daily_host')))
    conn.commit()


def write_requests(rows: Iterable[tuple]) -> None:
    """Append request rows, `REQUEST_COLUMNS` each, with COPY."""
    with db.connection() as conn:
        with conn.cursor().copy(sql.SQL('copy {} ({}) from stdin').format(
                _t('request_log'),
                sql.SQL(', ').join(map(sql.Identifier, REQUEST_COLUMNS)))) as copy:
            for row in rows:
                copy.write_row(row)
        conn.commit()


def write_host_sample(sample: dict) -> None:
    with db.connection() as conn:
        conn.execute(sql.SQL(
            'insert into {} (ts, cpu, mem_used, mem_total, disk_used, disk_total)'
            ' values (%(ts)s, %(cpu)s, %(mem_used)s, %(mem_total)s, %(disk_used)s,'
            ' %(disk_total)s)').format(_t('host_sample')), sample)
        conn.commit()


def _days(conn, source: str, done: str, today: datetime.date) -> list[datetime.date]:
    """The days before today with rows in `source` and none in `done`."""
    return [row[0] for row in conn.execute(sql.SQL("""
        select distinct (ts at time zone 'UTC')::date from {source} where ts < %s
        except select day from {done} order by 1""").format(
        source=_t(source), done=_t(done)), (today.isoformat(),)).fetchall()]


def roll_up(conn, today: datetime.date) -> list[datetime.date]:
    """Count every finished day not counted yet; return the request log's days.

    Per kind and once more over all kinds as `all`, because distinct IPs
    and keys do not add up across kinds.
    """
    days = _days(conn, 'request_log', 'daily_stats', today)
    for day in days:
        conn.execute(sql.SQL("""
            insert into {stats}
            select %(from)s::date, coalesce(kind, 'all'), count(*),
                   count(*) filter (where status >= 400),
                   count(*) filter (where cache = 'hit'),
                   count(*) filter (where cache = 'miss'),
                   percentile_cont(0.5) within group (order by ms),
                   percentile_cont(0.95) within group (order by ms),
                   count(distinct ip), count(distinct key_id)
            from {log} where ts >= %(from)s and ts < %(to)s
            group by grouping sets ((kind), ())
            on conflict do nothing""").format(
            stats=_t('daily_stats'), log=_t('request_log')), _span(day))
    for day in _days(conn, 'host_sample', 'daily_host', today):
        conn.execute(sql.SQL("""
            insert into {host}
            select %(from)s::date, avg(cpu), max(cpu), avg(mem_used)::bigint, max(mem_used),
                   max(mem_total), max(disk_used), max(disk_total)
            from {sample} where ts >= %(from)s and ts < %(to)s
            on conflict do nothing""").format(
            host=_t('daily_host'), sample=_t('host_sample')), _span(day))
    conn.commit()
    return days


def _span(day: datetime.date) -> dict:
    return {'from': day.isoformat(), 'to': (day + datetime.timedelta(days=1)).isoformat()}


def purge(conn, today: datetime.date) -> list[str]:
    """Drop the request log's partitions, and delete the rows, older than
    `request_log_days` days, today included; the same for the host samples.
    The key requests go after `MAX_RETENTION_DAYS`, whatever `request_log_days`."""
    cutoff = today - datetime.timedelta(days=retention_days() - 1)
    dropped = []
    names = [row[0] for row in conn.execute(
        "select c.relname from pg_inherits i join pg_class c on c.oid = i.inhrelid"
        " join pg_class p on p.oid = i.inhparent join pg_namespace n on n.oid = p.relnamespace"
        " where n.nspname = %s and p.relname = 'request_log'", (SCHEMA,)).fetchall()]
    for name in names:
        stamp = name.removeprefix('request_log_')
        if stamp.isdigit() and datetime.datetime.strptime(stamp, '%Y%m%d').date() < cutoff:
            conn.execute(sql.SQL('drop table if exists {}').format(_t(name)))
            dropped.append(name)
    conn.execute(sql.SQL('delete from {} where ts < %s').format(_t('request_log_default')),
                 (cutoff.isoformat(),))
    conn.execute(sql.SQL('delete from {} where ts < %s').format(_t('host_sample')),
                 (cutoff.isoformat(),))
    keys.purge_requests(conn, today - datetime.timedelta(days=MAX_RETENTION_DAYS - 1))
    conn.commit()
    return dropped


def daily(today: datetime.date | None = None) -> tuple[list[datetime.date], list[str]]:
    """Partitions ahead, count the finished days, drop the old ones.

    Counted before dropped, so a day is never gone before it is counted.
    """
    today = today or datetime.datetime.now(datetime.UTC).date()
    with db.connection() as conn:
        ensure(conn, today)
        counted = roll_up(conn, today)
        dropped = purge(conn, today)
    return counted, dropped


def export(month: datetime.date, out: TextIO) -> dict:
    """The month as CSV, one line per day; returns the month's totals.

    `monthly_cost_eur` is the operator's figure from the hosting invoice:
    the totals divide it by the requests, which is the number the package
    prices are made from.
    """
    start = month.replace(day=1)
    end = (start + datetime.timedelta(days=32)).replace(day=1)
    with db.connection() as conn:
        ensure(conn, datetime.datetime.now(datetime.UTC).date())
        rows = conn.execute(sql.SQL("""
            select d.day,
                   coalesce(max(s.requests) filter (where s.kind = 'tiles'), 0),
                   coalesce(max(s.requests) filter (where s.kind = 'wms'), 0),
                   coalesce(max(s.requests) filter (where s.kind = 'search'), 0),
                   coalesce(max(s.errors) filter (where s.kind = 'all'), 0),
                   coalesce(max(s.cache_hits) filter (where s.kind = 'all'), 0),
                   coalesce(max(s.cache_misses) filter (where s.kind = 'all'), 0),
                   max(s.ms_p95) filter (where s.kind = 'tiles'),
                   max(s.ms_p95) filter (where s.kind = 'search'),
                   coalesce(max(s.ips) filter (where s.kind = 'all'), 0),
                   max(h.cpu_avg), max(h.cpu_max), max(h.mem_max), max(h.mem_total),
                   max(h.disk_used), max(h.disk_total)
            from (select day from {stats} union select day from {host}) d
            left join {stats} s on s.day = d.day
            left join {host} h on h.day = d.day
            where d.day >= %s and d.day < %s
            group by d.day order by d.day""").format(
            stats=_t('daily_stats'), host=_t('daily_host')),
            (start.isoformat(), end.isoformat())).fetchall()

    writer = csv.writer(out, delimiter=';', lineterminator='\n')
    writer.writerow(['day', 'tiles', 'wms', 'search', 'errors', 'cache_hit_rate',
                     'tiles_p95_ms', 'search_p95_ms', 'ips', 'cpu_avg_pct', 'cpu_max_pct',
                     'mem_max_gb', 'mem_total_gb', 'disk_used_gb', 'disk_total_gb'])
    gb = 1024 ** 3
    totals = {'requests': 0, 'errors': 0, 'hits': 0, 'misses': 0}
    for (day, tiles, wms, search, errors, hits, misses, tiles_p95, search_p95, ips,
         cpu_avg, cpu_max, mem_max, mem_total, disk_used, disk_total) in rows:
        totals['requests'] += tiles + wms + search
        totals['errors'] += errors
        totals['hits'] += hits
        totals['misses'] += misses
        writer.writerow([
            day.isoformat(), tiles, wms, search, errors, _rate(hits, misses),
            _num(tiles_p95), _num(search_p95), ips, _num(cpu_avg), _num(cpu_max),
            _num(mem_max, gb), _num(mem_total, gb), _num(disk_used, gb), _num(disk_total, gb)])
    cost = config.opt('monthly_cost_eur')
    totals['cache_hit_rate'] = _rate(totals['hits'], totals['misses'])
    totals['cost_eur'] = cost
    totals['eur_per_1000'] = (round(float(cost) / totals['requests'] * 1000, 4)
                              if cost is not None and totals['requests'] else None)
    return totals


def report_month(today: datetime.date) -> Path | None:
    """Write the month before `today` to `stats/load-YYYY-MM.csv` under
    `data_dir`, unless it is there already or had no requests; return the
    path written, or None.

    No requests means the log was not running yet (the month before the
    first deploy): an empty file would read as a month without traffic.
    """
    month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    directory = Path(config.opt('data_dir', '/data')) / 'stats'
    path = directory / f'load-{month:%Y-%m}.csv'
    if path.exists():
        return None
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', newline='') as out:
            totals = export(month, out)
        if not totals['requests']:
            Path(temporary).unlink()
            return None
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    _log.info('request log: %s written, %d requests, cache hit rate %s, %s EUR per 1000',
              path, totals['requests'], totals['cache_hit_rate'] or '-',
              totals['eur_per_1000'] if totals['eur_per_1000'] is not None else '-')
    return path


def _rate(hits: int, misses: int) -> str:
    return f'{hits / (hits + misses):.3f}' if hits + misses else ''


def _num(value, divisor: float = 1) -> str:
    return '' if value is None else f'{value / divisor:.2f}'
