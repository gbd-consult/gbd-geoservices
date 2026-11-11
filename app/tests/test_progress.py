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
    monkeypatch.setattr(progress_module, 'peak_rss_gb', lambda: 1.234)
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
                     '  ways: 3,072 read, 1,536 kept, 4 s, done, peak 1.23g']


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


GB = 1024 ** 3


def cgroup(monkeypatch, tmp_path, limit, current, inactive):
    (tmp_path / 'memory.max').write_text(f'{limit}\n')
    (tmp_path / 'memory.current').write_text(f'{current}\n')
    (tmp_path / 'memory.stat').write_text(f'anon 1\ninactive_file {inactive}\n')
    monkeypatch.setattr(progress_module, 'CGROUP', str(tmp_path))
    monkeypatch.setattr(progress_module, '_field', lambda path, name, f=progress_module._field:
                        64 * 1024 ** 2 if path == '/proc/meminfo' else f(path, name))


def test_a_container_limit_bounds_the_available_memory(monkeypatch, tmp_path):
    """/proc/meminfo is the host's; the OOM killer goes by the container's limit.
    Inactive page cache counts as free, as the kernel reclaims it first."""
    cgroup(monkeypatch, tmp_path, 4 * GB, 3 * GB, GB // 2)
    assert progress_module.available_gb() == 1.5


def test_without_a_limit_the_host_figure_stands(monkeypatch, tmp_path):
    cgroup(monkeypatch, tmp_path, 'max', 3 * GB, 0)
    assert progress_module.available_gb() == 64


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


def test_a_pass_worker_logs_to_the_import_log(data_dir):
    """The passes run in spawned processes, which inherit no handler."""
    root = logging.getLogger()
    with progress_module.import_run('area_1', 0.0):
        target = progress_module.log_target()
        handlers = root.handlers
        try:
            progress_module.log_to(target)            # what the worker's initializer does
            logging.getLogger('importer').info('line_1')
        finally:
            root.handlers[0].close()
            root.handlers = handlers
    assert target == (str(data_dir / 'import.log'), 0.0)
    assert (data_dir / 'import.log').read_text().splitlines()[-1].endswith(':: line_1')


def test_outside_an_import_there_is_no_log_target():
    assert progress_module.log_target() is None
