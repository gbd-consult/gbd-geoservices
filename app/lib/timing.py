"""Per-request step timings, logged when a request is slow.

A request that takes seconds says so in the access log and nothing else:
whether a tile waited for a Map handle or rendered slowly, which of a
phrase's steps ran long. `Steps` records named steps of one request, and
`report` writes them as one line -- as a warning above `slow_log_ms`, at
debug below it, so `log_level: debug` shows every request's breakdown.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

from lib import config


class Steps:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.steps: list[tuple[str, float, int | None]] = []

    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, (time.perf_counter() - started) * 1000)

    def add(self, name: str, ms: float, rows: int | None = None) -> None:
        self.steps.append((name, ms, rows))

    def rows(self, count: int) -> None:
        """The row count of the step just recorded."""
        name, ms, _ = self.steps[-1]
        self.steps[-1] = (name, ms, count)

    def total_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000

    def summary(self) -> str:
        return ' '.join(f'{name} {ms:.0f}' + (f'({rows})' if rows is not None else '')
                        for name, ms, rows in self.steps)


def slow_ms() -> float:
    return float(config.opt('slow_log_ms', 1000))


def report(log: logging.Logger, steps: Steps, what: str) -> None:
    total = steps.total_ms()
    level = logging.WARNING if total >= slow_ms() else logging.DEBUG
    if log.isEnabledFor(level):
        log.log(level, '%s %s %.0fms: %s', 'slow' if level == logging.WARNING else 'timing',
                what, total, steps.summary())
