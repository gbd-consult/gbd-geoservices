"""Progress lines for the long parts of the import.

A pass over a `.pbf` gives no total up front, so there is no percentage:
a line says how many objects were read and kept so far, every
`import.progress_s` seconds. By time, not by count, because the same count
is a line a minute on one area and a hundred on the next.

Every line of the import log starts with the seconds since the import
started and the memory still available, `  123s   3.55g :: message`: an
import runs overnight, and a pass that is slow because the machine is
swapping looks the same as one that is slow because the area is large.
"""

from __future__ import annotations

import datetime
import fcntl
import logging
import math
import os
import time
from contextlib import contextmanager
from pathlib import Path

from lib import config

log = logging.getLogger('importer')

#: How many ticks between two looks at the clock. A pass reads millions of
#: objects; the clock is read once per this many of them.
_CHECK_EVERY = 1024


class Progress:
    def __init__(self, name: str, interval_s: float):
        self.name = name
        self.interval_s = interval_s
        self.read = 0
        self.kept = 0
        self._started = self._last = time.monotonic()

    def tick(self) -> None:
        """One object read."""
        self.read += 1
        if self.read % _CHECK_EVERY == 0:
            now = time.monotonic()
            if now - self._last >= self.interval_s:
                self._last = now
                self._log(now)

    def keep(self) -> None:
        """The object just read produced rows."""
        self.kept += 1

    def done(self) -> None:
        self._log(time.monotonic(), f', done, peak {peak_rss_gb():.2f}g')

    def _log(self, now: float, suffix: str = '') -> None:
        log.info('  %s: %s read, %s kept, %.0f s%s', self.name, f'{self.read:,}',
                 f'{self.kept:,}', now - self._started, suffix)


class Formatter(logging.Formatter):
    """Prefixes a record's first line with elapsed seconds and available memory.

    The pass workers are spawned and build their own from `log_target()`;
    `time.monotonic()` is the system's clock, so their seconds count from
    the same start.
    """

    def __init__(self, started: float):
        super().__init__()
        self.started = started

    def format(self, record: logging.LogRecord) -> str:
        elapsed = int(time.monotonic() - self.started)
        return f'{elapsed:5d}s {available_gb():6.2f}g :: {super().format(record)}'


def log_target() -> tuple[str, float] | None:
    """The import log's file and start time, for a pass worker to log there too.

    The passes run in spawned processes, which inherit no handler: they get
    these as their initializer's arguments. None outside an import.
    """
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler) and isinstance(handler.formatter, Formatter):
            return handler.baseFilename, handler.formatter.started
    return None


def log_to(target: tuple[str, float] | None) -> None:
    """In a pass worker: log to the import log, as the import process does."""
    logging.getLogger('importer').setLevel(logging.INFO)
    if target is not None:
        path, started = target
        handler = logging.FileHandler(path)
        handler.setFormatter(Formatter(started))
        logging.getLogger().handlers = [handler]


class ImportRunning(RuntimeError):
    pass


@contextmanager
def import_run(area: str, started: float):
    """`/data/import.status` held, and every log record appended to `/data/import.log`.

    The status file names the running import. It is locked, not only
    present: the kernel drops the lock when the process dies, so the file an
    import killed by the OOM killer or a container recreate leaves behind
    blocks nothing.

    The import writes its own log rather than leaving it to whoever reads its
    stderr: under `docker compose exec` that is the docker client, and when
    the client dies the import runs on with its log going nowhere.
    """
    data_dir = Path(config.opt('data_dir', '/data'))
    status_path = data_dir / 'import.status'
    status = open(status_path, 'a+')  # noqa: SIM115 -- held until the import ends
    try:
        fcntl.flock(status, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        status.seek(0)
        running = status.read().strip()
        status.close()
        raise ImportRunning(f'an import is running: {running}') from None
    now = f'{datetime.datetime.now():%Y-%m-%d %H:%M:%S}'
    status.truncate(0)
    status.write(f'pid {os.getpid()}, area {area}, started {now}\n')
    status.flush()

    log_path = data_dir / 'import.log'
    # A line's prefix is the seconds since its import started, so this is
    # what tells one run from the one before it.
    with open(log_path, 'a') as log_file:
        log_file.write(f'==> {now} import {area}\n')
    handler = logging.FileHandler(log_path)
    handler.setFormatter(Formatter(started))
    root = logging.getLogger()
    handlers = root.handlers
    root.handlers = [handler]
    try:
        yield
    finally:
        root.handlers = handlers
        handler.close()
        status_path.unlink(missing_ok=True)
        status.close()


def available_gb() -> float:
    """What can be allocated without swapping, page cache included.

    The host's `MemAvailable`, not `MemFree`, which the page cache drives
    towards zero during the passes; and under a container memory limit
    (cgroup v2) the less of that and the limit's headroom, since /proc/meminfo
    is the host's and the limit is what the OOM killer goes by. NaN where
    there is no /proc/meminfo.
    """
    available = _field('/proc/meminfo', 'MemAvailable:') * 1024
    limit = _cgroup('memory.max')
    if limit is not None:
        # Usage includes page cache; its inactive part is reclaimed before the limit bites.
        used = (_cgroup('memory.current') or 0) - _field(f'{CGROUP}/memory.stat', 'inactive_file')
        available = min(available, limit - used)
    return available / 1024 ** 3


def peak_rss_gb() -> float:
    """This process's peak resident memory, `VmHWM`.

    Each pass runs in a process of its own (`passes.run`), so for a pass
    this is that pass's peak. NaN where there is no /proc.
    """
    return _field('/proc/self/status', 'VmHWM:') * 1024 / 1024 ** 3


CGROUP = '/sys/fs/cgroup'


def _cgroup(name: str) -> int | None:
    """A cgroup v2 memory file as bytes; None without one, or for `max`, no limit."""
    try:
        with open(f'{CGROUP}/{name}') as f:
            value = f.read().strip()
    except OSError:
        return None
    return None if value == 'max' else int(value)


def _field(path: str, name: str) -> float:
    """The number after `name` in a `name value` file, NaN without it."""
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(name):
                    return int(line.split()[1])
    except OSError:
        pass
    return math.nan


def duration(seconds: float) -> str:
    """`2hr 5min 33sec`, leaving out the parts that are zero."""
    total = int(seconds)
    parts = [(total // 3600, 'hr'), (total // 60 % 60, 'min'), (total % 60, 'sec')]
    return ' '.join(f'{value}{unit}' for value, unit in parts if value) or '0sec'
