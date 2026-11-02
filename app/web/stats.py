"""The request log's rows and the host's figures, collected and written.

Every API request -- a route behind `auth.requires(scope)` -- becomes one
row of `service.request_log` (`lib/stats.py`) when its response is done:
the `record_request` middleware in `web/main.py` calls `record`. Rows are
buffered and written with COPY every `FLUSH_S`, together with one sample of
the host's CPU, RAM and disk -- `/proc` in the container is the host's.

The log is not the invoice (that is `auth`'s usage count, kept until it is
written): a flush that fails drops its rows, and the buffer never holds more
than `MAX_BUFFERED`, so a database that is down costs log rows and never
the server's memory.

Search terms are the request's own text fields, cut to `TERMS_MAX`; the
route puts them on `request.state.search_terms`. Like the IP they live
only in `request_log`, which `store.daily` empties after `request_log_days`.

The same thread runs `store.daily` at start and then once a day, at
`DAILY_AFTER_S` past midnight UTC: by then every process has flushed the
rows of the day before, so the day is counted whole.
"""

from __future__ import annotations

import datetime
import logging
import shutil
import threading
from collections import deque
from collections.abc import Callable

from fastapi import Request

from lib import config
from lib import stats as store

_log = logging.getLogger(__name__)

#: How often the rows and a host sample are written.
FLUSH_S = 60.0

#: Rows held at most while the database cannot take them; the oldest go first.
MAX_BUFFERED = 200_000

#: Search terms are cut to this many characters.
TERMS_MAX = 200

#: How long after midnight UTC the day before is counted: past the last
#: flush of every process, so no row of that day arrives after its count.
DAILY_AFTER_S = 5 * FLUSH_S

_lock = threading.Lock()
_rows: deque[tuple] = deque(maxlen=MAX_BUFFERED)
_dropped = 0


def kind_of(request: Request) -> str | None:
    """`tiles`, `wms` or `search` for an API request, else None (not logged)."""
    scope = getattr(request.state, 'key_scope', None)
    if scope is None:
        return None
    return 'wms' if request.url.path.startswith('/wms') else scope


def record(request: Request, status: int, ms: float) -> None:
    global _dropped
    kind = kind_of(request)
    if kind is None:
        return
    key = getattr(request.state, 'key', None)
    row = (datetime.datetime.now(datetime.UTC), kind, key.id if key else None, status,
           round(ms, 1), getattr(request.state, 'cache', None),
           request.client.host if request.client else None,
           getattr(request.state, 'search_terms', None))
    with _lock:
        if len(_rows) == MAX_BUFFERED:
            _dropped += 1                         # append pushes out the oldest
        _rows.append(row)


def terms_of(body: dict) -> str | None:
    """A search body's text fields, as one string."""
    fields = ('text', 'street', 'housenumber', 'postcode', 'city')
    terms = ' | '.join(str(body[f]) for f in fields if body.get(f))
    return terms[:TERMS_MAX] or None


class HostSampler:
    """CPU busy share since the previous sample, RAM and disk in use."""

    def __init__(self) -> None:
        self._previous: tuple[int, int] | None = None

    def sample(self) -> dict:
        busy, total = _cpu_times()
        cpu = None
        if self._previous and total > self._previous[1]:
            cpu = round(100 * (busy - self._previous[0]) / (total - self._previous[1]), 1)
        self._previous = (busy, total)
        mem_total, mem_available = _meminfo()
        disk = shutil.disk_usage(config.opt('data_dir', '/data'))
        return {'ts': datetime.datetime.now(datetime.UTC), 'cpu': cpu,
                'mem_used': mem_total - mem_available, 'mem_total': mem_total,
                'disk_used': disk.used, 'disk_total': disk.total}


def _cpu_times() -> tuple[int, int]:
    """(busy, total) jiffies over all CPUs: idle and iowait are not busy."""
    with open('/proc/stat') as f:
        values = [int(v) for v in f.readline().split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values[:8])
    return total - idle, total


def _meminfo() -> tuple[int, int]:
    """(MemTotal, MemAvailable) in bytes."""
    found = {}
    with open('/proc/meminfo') as f:
        for line in f:
            name, value = line.split(':', 1)
            if name in ('MemTotal', 'MemAvailable'):
                found[name] = int(value.split()[0]) * 1024
    return found['MemTotal'], found['MemAvailable']


def flush(sampler: HostSampler | None = None) -> None:
    """Write the buffered rows and, given a sampler, one host sample."""
    global _dropped
    with _lock:
        rows = list(_rows)
        _rows.clear()
        dropped, _dropped = _dropped, 0
    if dropped:
        _log.warning('request log: %d rows dropped, the buffer was full', dropped)
    try:
        if rows:
            store.write_requests(rows)
        if sampler is not None:
            store.write_host_sample(sampler.sample())
    except Exception as exc:                      # noqa: BLE001 - a log, not the invoice
        _log.warning('request log: %d rows not written: %s', len(rows), exc)


def daily_day(now: datetime.datetime) -> datetime.date:
    """The day `store.daily` treats as today: the UTC date `DAILY_AFTER_S` ago."""
    return (now - datetime.timedelta(seconds=DAILY_AFTER_S)).date()


def run_daily(day: datetime.date) -> bool:
    """`store.daily` for `day`; False if it failed, so the next flush retries."""
    try:
        counted, dropped = store.daily(day)
    except Exception as exc:                      # noqa: BLE001 - retried at the next flush
        _log.warning('request log: daily run failed: %s', exc)
        return False
    if counted or dropped:
        _log.info('request log: counted %s, dropped %s',
                  ', '.join(map(str, counted)) or 'nothing', ', '.join(dropped) or 'nothing')
    return True


def start() -> Callable[[], None]:
    """Flush every `FLUSH_S` in a thread, and run `store.daily` at start and
    once a day; returns the stop, which flushes once more.

    Off with the `request_log` option (the test suite turns it off, so a
    test run writes nothing into the dev database). A `request_log_days`
    out of range stops the start: it is what the privacy policy promises.
    """
    if not config.opt('request_log', True):
        return lambda: None
    store.retention_days()
    stop = threading.Event()
    sampler = HostSampler()

    def loop() -> None:
        done: datetime.date | None = None
        while True:
            day = daily_day(datetime.datetime.now(datetime.UTC))
            if day != done and run_daily(day):
                done = day
            if stop.wait(FLUSH_S):
                return
            flush(sampler)

    thread = threading.Thread(target=loop, name='request-log', daemon=True)
    thread.start()

    def stopper() -> None:
        stop.set()
        thread.join()
        flush()

    return stopper
