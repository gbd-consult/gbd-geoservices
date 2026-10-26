"""Progress lines of the import passes."""

from __future__ import annotations

import logging
import re

import pytest

from importer import progress as progress_module
from importer.progress import Progress


def test_a_line_every_interval_and_one_at_the_end(caplog, monkeypatch):
    clock = iter(range(0, 10_000))
    monkeypatch.setattr(progress_module.time, 'monotonic', lambda: next(clock))
    progress = Progress('ways', 2)
    with caplog.at_level(logging.INFO, logger='importer'):
        for i in range(3 * 1024):
            progress.tick()
            if i % 2:
                progress.keep()
        progress.done()
    lines = [r.getMessage() for r in caplog.records]
    # The clock is read once per 1024 objects and moves one second per read.
    # The line is written on the tick, before that object's keep().
    assert lines == ['  ways: 2,048 read, 1,023 kept, 2 s',
                     '  ways: 3,072 read, 1,536 kept, 4 s, done']


@pytest.mark.parametrize('seconds, text', [
    (0, '0sec'), (33.9, '33sec'), (60, '1min'), (7203, '2hr 3sec'), (7533, '2hr 5min 33sec'),
])
def test_duration_leaves_out_the_parts_that_are_zero(seconds, text):
    assert progress_module.duration(seconds) == text


def test_the_prefix_is_elapsed_seconds_and_available_memory(monkeypatch):
    monkeypatch.setattr(progress_module.time, 'monotonic', lambda: 1123.9)
    monkeypatch.setattr(progress_module, 'available_gb', lambda: 3.554)
    formatter = progress_module.Formatter(1000.0)
    record = logging.LogRecord('importer', logging.INFO, __file__, 1, 'message_1', None, None)
    assert formatter.format(record) == '  123s   3.55g :: message_1'


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    opt = progress_module.config.opt
    monkeypatch.setattr(progress_module.config, 'opt', lambda path, default=None:
                        str(tmp_path) if path == 'data_dir' else opt(path, default))
    return tmp_path


def test_each_import_is_appended_under_a_line_naming_it(data_dir):
    (data_dir / 'import.log').write_text('line_1\n')
    with progress_module.import_run('area_1', 0.0):
        logging.getLogger('importer').warning('line_2')
    lines = (data_dir / 'import.log').read_text().splitlines()
    assert lines[0] == 'line_1'
    assert re.fullmatch(r'==> \d{4}-\d\d-\d\d \d\d:\d\d:\d\d import area_1', lines[1])
    assert lines[2].endswith(':: line_2')
    assert len(lines) == 3


def test_the_status_file_names_the_import_and_is_gone_after_it(data_dir):
    with progress_module.import_run('area_1', 0.0):
        assert ', area area_1, started ' in (data_dir / 'import.status').read_text()
    assert not (data_dir / 'import.status').exists()


def test_a_running_import_is_not_disturbed(data_dir):
    with progress_module.import_run('area_1', 0.0):
        logging.getLogger('importer').warning('line_1')
        with (pytest.raises(progress_module.ImportRunning, match='area area_1'),
              progress_module.import_run('area_2', 0.0)):
            pass
        assert (data_dir / 'import.status').exists()
    assert 'line_1' in (data_dir / 'import.log').read_text()


def test_a_status_file_left_by_a_killed_import_blocks_nothing(data_dir):
    """The kernel dropped the killed import's lock; the file is all that is left."""
    (data_dir / 'import.status').write_text('pid 1, area area_1, started 2026-01-01 00:00:00\n')
    with progress_module.import_run('area_2', 0.0):
        assert 'area area_2' in (data_dir / 'import.status').read_text()
