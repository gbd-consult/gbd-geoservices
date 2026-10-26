"""The management CLI and the extract it resolves.

`manage.py` is meant to be thin -- it sequences module functions and touches
neither the database nor the filesystem itself -- so what is worth testing
is the wiring and the area-name handling, not behaviour that lives in the
importer.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from importer import extract
from tools import manage


@pytest.fixture(autouse=True)
def import_log(monkeypatch, tmp_path):
    """Not the container's /data/import.log."""
    opt = manage.progress.config.opt
    monkeypatch.setattr(manage.progress.config, 'opt', lambda path, default=None:
                        str(tmp_path) if path == 'data_dir' else opt(path, default))
    return tmp_path / 'import.log'


# --- areas ---------------------------------------------------------------

def test_every_area_resolves_to_a_pbf():
    for area, path in extract.areas().items():
        assert path.endswith('.osm.pbf'), area


def test_the_default_areas():
    assert set(extract.areas()) == {'li', 'de_sh', 'de_nrw', 'de_nb', 'de'}
    assert extract.areas()['li'].endswith('liechtenstein-latest.osm.pbf')
    assert extract.areas()['de_sh'].endswith('schleswig-holstein-latest.osm.pbf')


def test_an_area_is_added_by_the_options(monkeypatch):
    monkeypatch.setattr(extract.config, 'opt', lambda path, default=None:
                        {'area_1': 'europe/area_1-latest.osm.pbf'} if path == 'areas' else default)
    assert extract.path_for('area_1', Path('/d')) == Path('/d/area_1-latest.osm.pbf')
    with pytest.raises(ValueError, match='unknown area'):
        extract.check('de_sh')


@pytest.mark.parametrize('name', ['Area_1', '1area', 'area-1', 'area 1', '../area_1'])
def test_an_area_name_that_is_no_plain_identifier_is_refused(monkeypatch, name):
    """The name becomes a schema name and a directory under data_dir."""
    monkeypatch.setattr(extract.config, 'opt', lambda path, default=None:
                        {name: 'europe/area_1-latest.osm.pbf'} if path == 'areas' else default)
    with pytest.raises(ValueError, match='lowercase letters'):
        extract.check(name)


def test_url_is_built_from_the_option():
    url = extract.url_for('de_sh')
    assert url.endswith('/europe/germany/schleswig-holstein-latest.osm.pbf')
    assert url.startswith('https://')
    # No doubled slash where the base and the path meet.
    assert '//' not in url.split('://', 1)[1]


@pytest.mark.parametrize('area', sorted(extract.areas()))
def test_url_for_every_area(area):
    assert extract.url_for(area).endswith(extract.areas()[area])


def test_unknown_area_names_the_valid_ones():
    # The common typo, and it would otherwise surface much later as an
    # empty schema.
    with pytest.raises(ValueError, match='unknown area') as excinfo:
        extract.url_for('schleswig-holstein')
    message = str(excinfo.value)
    for area in extract.areas():
        assert area in message


def test_path_is_the_basename_in_downloads(tmp_path):
    assert extract.path_for('de_sh', tmp_path) == tmp_path / 'schleswig-holstein-latest.osm.pbf'


# --- fetching ------------------------------------------------------------

def test_an_existing_extract_is_reused(tmp_path, monkeypatch):
    # A `de` extract is several gigabytes; re-downloading it because
    # a run was repeated is not a small mistake.
    existing = tmp_path / 'schleswig-holstein-latest.osm.pbf'
    existing.write_bytes(b'not really a pbf')

    def fail(*args, **kwargs):
        raise AssertionError('should not download an extract that is already here')

    monkeypatch.setattr(extract, 'urlretrieve', fail)
    assert extract.ensure('de_sh', tmp_path) == existing


def test_a_missing_extract_is_downloaded(tmp_path, monkeypatch):
    calls = []

    def fake(url, target):
        calls.append((url, Path(target)))
        Path(target).write_bytes(b'')

    monkeypatch.setattr(extract, 'urlretrieve', fake)
    result = extract.ensure('li', tmp_path / 'nested')

    assert len(calls) == 1
    url, target = calls[0]
    assert url == extract.url_for('li')
    assert target == result == tmp_path / 'nested' / 'liechtenstein-latest.osm.pbf'


def test_ensure_rejects_an_unknown_area(tmp_path):
    with pytest.raises(ValueError, match='unknown area'):
        extract.ensure('nope', tmp_path)


# --- the CLI -------------------------------------------------------------

@pytest.fixture
def imported(monkeypatch):
    """The import's collaborators, faked: it needs the database and a pbf."""
    monkeypatch.setattr(manage.extract, 'ensure', lambda area, downloads=None: Path('x.pbf'))
    monkeypatch.setattr(manage.run, 'summary', lambda path, result: 'summary_1')


def test_help_lists_every_subcommand(capsys):
    # The docstring above `main` names the ones that exist; help is where a
    # user finds out, so a subcommand added without reaching here is one
    # nobody can discover.
    with pytest.raises(SystemExit) as excinfo:
        manage.main(['--help'])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for command in ('import', 'compile-styles', 'pre-cache', 'drop-cache'):
        assert command in out


def test_a_command_is_required(capsys):
    with pytest.raises(SystemExit) as excinfo:
        manage.main([])
    assert excinfo.value.code != 0


def test_an_unknown_area_is_rejected_before_anything_runs(monkeypatch, capsys):
    # argparse `choices`, so it fails at parse time rather than after the
    # import has already started.
    monkeypatch.setattr(manage.run, 'import_area', lambda *a, **k: pytest.fail('ran'))
    with pytest.raises(SystemExit) as excinfo:
        manage.main(['import', 'schleswig-holstein'])
    assert excinfo.value.code != 0


def test_import_passes_the_extract_and_the_area(monkeypatch, capsys, imported):
    seen = {}

    def fake_ensure(area, downloads=None):
        seen['area'] = area
        return Path('/data/downloads/schleswig-holstein-latest.osm.pbf')

    def fake_import(path, area, *, water=True, params=None, pass_workers=1):
        seen['path'], seen['import_area'], seen['water'] = path, area, water
        return {'timings': {'total': 123.0}, 'counts': {}}

    monkeypatch.setattr(manage.extract, 'ensure', fake_ensure)
    monkeypatch.setattr(manage.run, 'import_area', fake_import)

    assert manage.main(['import', 'de_sh']) == 0
    assert seen['area'] == seen['import_area'] == 'de_sh'
    assert seen['path'].name == 'schleswig-holstein-latest.osm.pbf'
    assert seen['water'] is True


def test_no_water_is_passed_through(monkeypatch, imported):
    seen = {}
    monkeypatch.setattr(manage.run, 'import_area',
                        lambda path, area, *, water=True, params=None, pass_workers=1:
                        seen.update(water=water) or {'timings': {'total': 1.0}, 'counts': {}})
    manage.main(['import', 'li', '--no-water'])
    assert seen['water'] is False


def test_pass_workers_is_passed_through(monkeypatch, imported):
    seen = {}
    monkeypatch.setattr(manage.run, 'import_area',
                        lambda path, area, *, water=True, params=None, pass_workers=1:
                        seen.update(pass_workers=pass_workers)
                        or {'timings': {'total': 1.0}, 'counts': {}})
    manage.main(['import', 'li'])
    assert seen['pass_workers'] == 1
    manage.main(['import', 'li', '-pw', '3'])
    assert seen['pass_workers'] == 3


def test_import_leaves_styles_and_cache_alone(monkeypatch, imported):
    """Each command is one action: the served schema, its styles and the
    area's cache change only when their own command runs."""
    from renderer import styles

    monkeypatch.setattr(manage.run, 'import_area',
                        lambda *a, **k: {'timings': {'total': 1.0}, 'counts': {}})
    monkeypatch.setattr(styles, 'run', lambda *a, **k: pytest.fail('compiled'))
    monkeypatch.setattr(manage.cache, 'clear_area', lambda *a: pytest.fail('cleared'))
    assert manage.main(['import', 'de_sh']) == 0


def test_compile_styles_leaves_the_cache_alone(monkeypatch, capsys):
    from lib import db
    from renderer import styles

    runs = []
    monkeypatch.setattr(db, 'active_schema', lambda area=None: f'{area}_20260101_000000')
    monkeypatch.setattr(styles, 'run', lambda schema=None: runs.append(schema) or [])
    monkeypatch.setattr(manage, 'reload_server', lambda: 'reloaded')
    monkeypatch.setattr(manage.cache, 'clear_area', lambda *a: pytest.fail('cleared'))
    assert manage.main(['compile-styles', 'de_sh']) == 0
    assert runs == ['de_sh_20260101_000000']


def test_drop_cache_empties_the_area_s_cache(monkeypatch, capsys):
    cleared = []
    monkeypatch.setattr(manage.cache, 'clear_area', lambda area: cleared.append(area) or 7)
    assert manage.main(['drop-cache', 'de_sh']) == 0
    assert cleared == ['de_sh']
    assert '7 cached tiles' in capsys.readouterr().err


def test_pre_cache_passes_fast_and_force(monkeypatch, capsys):
    from lib import db
    from renderer import precache

    seen = {}
    monkeypatch.setattr(db, 'active_schema', lambda area=None: f'{area}_20260101_000000')
    monkeypatch.setattr(precache, 'run', lambda schema, **kwargs:
                        seen.update(schema=schema, **kwargs) or {})
    assert manage.main(['pre-cache', 'de_sh', '--fast', '--force']) == 0
    assert seen['schema'] == 'de_sh_20260101_000000'
    assert seen['fast'] is True and seen['force'] is True


def test_import_ends_with_the_summary_and_complete(monkeypatch, capsys, imported, import_log):
    """An import runs overnight and is read with `tail import.log`: the last
    line says how it ended, and nothing -- no hint, no result dump -- comes
    after it."""
    monkeypatch.setattr(manage.run, 'import_area',
                        lambda *a, **k: {'timings': {'total': 90.0}, 'counts': {}})
    assert manage.main(['import', 'li']) == 0
    assert capsys.readouterr() == ('', '')
    lines = import_log.read_text().splitlines()
    assert lines.pop(0).endswith(' import li')
    assert re.fullmatch(r' {4}\ds [ \d.]{5}\dg :: Starting import "li"', lines[0])
    assert any(line.endswith(':: summary_1') for line in lines)
    assert re.fullmatch(r'[ \d]{4}\ds [ \d.na]{6}g :: Import "li" complete in \d+sec',
                        lines[-1])


def test_a_failed_import_ends_with_the_error(monkeypatch, imported, import_log):
    def fail(*args, **kwargs):
        raise RuntimeError('error_1')

    monkeypatch.setattr(manage.run, 'import_area', fail)
    assert manage.main(['import', 'li']) == 1
    err = import_log.read_text()
    assert 'Traceback' in err
    assert ':: RuntimeError: error_1' in err
    assert re.search(r':: Import "li" ERROR after \d+sec$', err.rstrip('\n'))


def test_import_leaves_the_root_logger_as_it_found_it(monkeypatch, imported):
    """caplog listens on the root logger; its handler left off would silence
    every later test of the import's log lines."""
    monkeypatch.setattr(manage.run, 'import_area',
                        lambda *a, **k: {'timings': {'total': 1.0}, 'counts': {}})
    root = logging.getLogger()
    handlers = list(root.handlers)
    manage.main(['import', 'li'])
    assert root.handlers == handlers


def test_a_second_import_is_refused(monkeypatch, capsys, imported, import_log):
    monkeypatch.setattr(manage.run, 'import_area', lambda *a, **k: pytest.fail('ran'))
    with manage.progress.import_run('de', 0.0):
        assert manage.main(['import', 'li']) == 1
    assert 'an import is running: pid ' in capsys.readouterr().err


def test_the_summary_counts_the_features_of_the_three_passes(tmp_path):
    from importer import run

    pbf = tmp_path / 'file_1.osm.pbf'
    pbf.write_bytes(b'x' * 2_500_000)
    result = {'timings': {'total': 10.0},
              'counts': {'nodes': {'point': 100, 'search': 7},
                         'ways': {'line': 300, 'street_ends': 9},
                         'areas': {'polygon': 400, 'building': 200},
                         'places': {'objects': 5, 'addresses': 6}}}
    assert run.summary(pbf, result) == (
        '2.5 MB pbf, 1,000 features (point 100, line 300, polygon 400, building 200), '
        '5 search objects, 6 addresses, 100 features/s')


def test_the_index_build_is_inside_its_timing_block():
    """Every step is measured (DESIGN.md "Principles"), and run.py's
    docstring says a step that doubles the import has to be visible in the
    step that caused it.

    With `create_indexes` *after* `with step('indexes', ...)`, the most
    expensive part of the post-processing -- minutes on a real extract --
    is the one step nothing measures, and `timings['indexes']` reports the
    milliseconds of statement planning instead.
    """
    import inspect

    from importer import run

    source = inspect.getsource(run.import_area)
    block = source.split("with step('indexes'):", 1)[1]
    # Everything up to the next `with step(` belongs to this block.
    block = block.split('with step(', 1)[0]
    assert 'create_indexes' in block, \
        'create_indexes ran outside the step() that is supposed to time it'


def test_the_steps_are_numbered_out_of_the_steps_that_run(caplog):
    """`[n/total]` is how a long import says how far it is; without water
    two steps do not run and must not count."""
    import logging

    from importer import run

    for water, total in ((True, 16), (False, 14)):
        names = run.STEPS if water else tuple(n for n in run.STEPS if n not in run.WATER_STEPS)
        step = run.Steps(names)
        with caplog.at_level(logging.INFO, logger='importer'), step('merge streets'):
            pass
        assert f'[5/{total}] merge streets ...' in caplog.text if water else \
            f'[4/{total}] merge streets ...' in caplog.text
        assert 'merge streets' in step.timings
        caplog.clear()
