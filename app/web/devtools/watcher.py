"""Recompile the styles when a file under `styles/` changes.

Runs while the `devtools` and `devtools_watch` options are on, as a thread of the server process:
a change to any file under `styles/` -- the YAML and the icon SVGs alike --
runs what `manage.py compile-styles` runs (icons, `osm_point.icon`, the XML, the
tile cache) and then what `/internal/reload` does, without the HTTP round
trip. The page polls `state()` and redraws when `compiles` moves.

Changes are grouped: an editor saving several files, or one file in several
writes, is one recompile. A change that arrives while a recompile runs is
held by `watchfiles` and becomes the next one, so the last save always wins.

uvicorn's own `--reload` watches `*.py` only, so a style edit never
restarts the server under this thread. The reverse is what the startup
compile is for: `--reload` restarts the server on every Python change, and
if the server only loaded the XML already compiled, a style edit that
landed around a restart -- or a change to the style code itself -- would be
served stale until the next save under `styles/`.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from pathlib import Path

import watchfiles

from lib import db

_log = logging.getLogger(__name__)

#: How long the tree must be quiet before a burst of changes is compiled.
QUIET_MS = 300

#: What the startup compile reports as changed.
STARTUP = ['(server start)']

_state = {
    'watching': False,
    'running': False,
    'compiles': 0,
    'changed': [],
    'error': None,
    'finished_at': None,
    'seconds': None,
}
_lock = threading.Lock()


def state() -> dict:
    with _lock:
        return dict(_state)


class Watcher:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='style-watcher', daemon=True)

    def start(self) -> Watcher:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        # Before watching, not after: the XML the server just loaded may be
        # older than the style files or the code that compiles them.
        recompile(STARTUP)
        _update(watching=True)
        _log.info('watching %s for style changes', self.directory)
        try:
            for changes in watchfiles.watch(self.directory, step=QUIET_MS,
                                            stop_event=self._stop):
                changed = sorted({str(Path(path).relative_to(self.directory))
                                  for _, path in changes})
                recompile(changed)
        finally:
            _update(watching=False)


def recompile(changed: list[str]) -> None:
    """Compile, clear the tile cache, reload. A failure is reported, not raised."""
    from renderer import cache, styles
    from web import meta

    _log.info('styles changed: %s', ', '.join(changed))
    _update(running=True, changed=changed)
    started = time.perf_counter()
    try:
        schema = db.active_schema()
        styles.run(schema)
        # Style development wants to see the change on the next tile, not
        # the tile cached before it.
        cache.clear_area(db.area_of(schema))
        meta.reload_all()
    except Exception as exc:                  # noqa: BLE001 - the next save retries
        _log.exception('style recompile failed')
        _update(running=False, error=str(exc) or type(exc).__name__,
                finished_at=_now(), seconds=time.perf_counter() - started)
        return
    seconds = time.perf_counter() - started
    _log.info('styles recompiled in %.1f s', seconds)
    with _lock:
        _state.update(running=False, error=None, finished_at=_now(), seconds=seconds,
                      compiles=_state['compiles'] + 1)


def _update(**values) -> None:
    with _lock:
        _state.update(values)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()
