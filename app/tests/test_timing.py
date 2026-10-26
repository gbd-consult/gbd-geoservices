"""The step timings a slow tile or search logs."""

from __future__ import annotations

import logging

from lib import timing


def test_a_slow_request_is_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(timing, 'slow_ms', lambda: 0)
    steps = timing.Steps()
    steps.add('step_1', 12.4)
    steps.add('step_2', 3.0, 7)
    with caplog.at_level(logging.DEBUG):
        timing.report(logging.getLogger('timing_test'), steps, 'request_1')
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert record.getMessage().startswith('slow request_1 ')
    assert record.getMessage().endswith(': step_1 12 step_2 3(7)')


def test_a_fast_request_is_debug(monkeypatch, caplog):
    monkeypatch.setattr(timing, 'slow_ms', lambda: 10_000)
    with caplog.at_level(logging.DEBUG):
        timing.report(logging.getLogger('timing_test'), timing.Steps(), 'request_1')
    [record] = caplog.records
    assert record.levelno == logging.DEBUG
