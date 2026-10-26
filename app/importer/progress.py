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
        self._log(time.monotonic(), ', done')

    def _log(self, now: float, suffix: str = '') -> None:
        log.info('  %s: %s read, %s kept, %.0f s%s', self.name, f'{self.read:,}',
                 f'{self.kept:,}', now - self._started, suffix)


class Formatter(logging.Formatter):
    """Prefixes a record's first line with elapsed seconds and available memory.

    The pass workers are forked, so they inherit this formatter and its
    start time along with the handler.
    """

    def __init__(self, started: float):
        super().__init__()
        self.started = started

    def format(self, record: logging.LogRecord) -> str:
        elapsed = int(time.monotonic() - self.started)
        return f'{elapsed:5d}s {available_gb():6.2f}g :: {super().format(record)}'


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
    """`MemAvailable`: what can be allocated without swapping, page cache included.

    Not `MemFree`, which the page cache drives towards zero during the
    passes. NaN where there is no /proc/meminfo.
    """
    try:
        with open('/proc/meminfo') as meminfo:
            for line in meminfo:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return math.nan


def duration(seconds: float) -> str:
    """`2hr 5min 33sec`, leaving out the parts that are zero."""
    total = int(seconds)
    parts = [(total // 3600, 'hr'), (total // 60 % 60, 'min'), (total % 60, 'sec')]
    return ' '.join(f'{value}{unit}' for value, unit in parts if value) or '0sec'
