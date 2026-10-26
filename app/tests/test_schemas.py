"""An import per schema: names, the schema served, publishing, the lock."""

from __future__ import annotations

import datetime

import pytest
from psycopg import sql

from lib import config
from lib import db as db_module

AREA = 'area_1'


def test_a_schema_is_named_by_area_and_start_time():
    started = datetime.datetime(2026, 9, 28, 14, 32, 5)
    assert db_module.schema_name(AREA, started) == 'area_1_20260928_143205'
    assert db_module.temp_name('area_1_20260928_143205') == '_area_1_20260928_143205'


@pytest.mark.parametrize('schema, area', [
    ('area_1_20260928_143205', 'area_1'),
    ('_area_1_20260928_143205', 'area_1'),
    ('de_sh_20260928_143205', 'de_sh'),
    ('de_sh', 'de_sh'),
])
def test_the_area_of_a_schema(schema, area):
    assert db_module.area_of(schema) == area


def test_a_forced_schema_is_served_without_asking_the_database(monkeypatch):
    options = {'serve_area': AREA, 'force_schema': 'area_1_20260101_000000'}
    monkeypatch.setattr(config, 'opt', lambda path, default=None: options.get(path, default))
    monkeypatch.setattr(db_module, 'connection', lambda: pytest.fail('queried'))
    assert db_module.active_schema() == 'area_1_20260101_000000'


def test_a_forced_schema_of_another_area_does_not_apply(monkeypatch):
    options = {'serve_area': AREA, 'force_schema': 'area_2_20260101_000000'}
    monkeypatch.setattr(config, 'opt', lambda path, default=None: options.get(path, default))
    monkeypatch.setattr(db_module, '_active', {AREA: 'area_1_20260102_000000'})
    assert db_module.active_schema() == 'area_1_20260102_000000'


def test_a_schema_name_is_taken_as_it_is(monkeypatch):
    monkeypatch.setattr(db_module, 'active_schema', lambda area=None: pytest.fail('resolved'))
    assert db_module.schema_for('area_1_20260101_000000') == 'area_1_20260101_000000'


# --- against the database ------------------------------------------------

@pytest.fixture
def schemas(db):
    """Creates schemas of `area_1` by name; drops every one afterwards."""
    def create(*names):
        for name in names:
            db.execute(sql.SQL('create schema {}').format(sql.Identifier(name)))
        db.commit()

    yield create
    db.rollback()
    for name in (db_module.complete_schemas(db, AREA) + db_module.temp_schemas(db, AREA)
                 + ['area_1', 'area_1_other_20260101_000000']):
        db.execute(sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(name)))
    db.commit()


def test_only_complete_imports_of_the_area_are_listed_newest_first(db, schemas):
    schemas('area_1_20260101_000000', 'area_1_20260102_000000', '_area_1_20260103_000000',
            'area_1', 'area_1_other_20260101_000000')
    assert db_module.complete_schemas(db, AREA) == ['area_1_20260102_000000',
                                                    'area_1_20260101_000000']
    assert db_module.temp_schemas(db, AREA) == ['_area_1_20260103_000000']


def test_publishing_renames_and_keeps_the_newest_two(db, schemas, tmp_path, monkeypatch):
    from importer import run

    monkeypatch.setattr(config, 'opt', lambda path, default=None: None)
    schemas('area_1_20260101_000000', 'area_1_20260102_000000', '_area_1_20260103_000000')
    styles = tmp_path / 'styles' / 'area_1_20260101_000000'
    styles.mkdir(parents=True)

    dropped = run.publish(db, AREA, 'area_1_20260103_000000', keep=2, data_dir=tmp_path)
    assert dropped == ['area_1_20260101_000000']
    assert db_module.complete_schemas(db, AREA) == ['area_1_20260103_000000',
                                                    'area_1_20260102_000000']
    assert db_module.temp_schemas(db, AREA) == []
    assert not styles.exists()


def test_publishing_never_drops_the_forced_schema(db, schemas, tmp_path, monkeypatch):
    """It is the one being served, however old."""
    from importer import run

    monkeypatch.setattr(config, 'opt', lambda path, default=None:
                        'area_1_20260101_000000' if path == 'force_schema' else None)
    schemas('area_1_20260101_000000', 'area_1_20260102_000000', '_area_1_20260103_000000')
    assert run.publish(db, AREA, 'area_1_20260103_000000', keep=2, data_dir=tmp_path) == []
    assert 'area_1_20260101_000000' in db_module.complete_schemas(db, AREA)


def test_a_second_import_of_the_area_is_refused(db):
    from importer import run

    with run.area_lock(AREA), pytest.raises(RuntimeError, match='another import'), \
            run.area_lock(AREA):
        pass
    # Released when the first one ends.
    with run.area_lock(AREA):
        pass


# --- serving -------------------------------------------------------------

def test_an_area_with_no_import_is_a_503(monkeypatch):
    from fastapi.testclient import TestClient

    from web.main import create_app

    def none(area=None):
        raise db_module.NoImportError('no complete import of area_1')

    monkeypatch.setattr(db_module, 'active_schema', none)
    response = TestClient(create_app()).get('/xyz/std/0/0/0.png')
    assert response.status_code == 503
    assert 'area_1' in response.json()['detail']


# --- pre-cache --fast ----------------------------------------------------

def test_fast_stops_before_the_first_level_with_too_many_tiles():
    from renderer import matrix, precache

    tms = matrix.load()['GoogleMapsCompatible']
    world = tms.bbox(0, 0, 0)
    # Over the whole world, level n has 4**n tiles.
    assert precache.fast_depth(tms, world, 16) == 2
    assert precache.fast_depth(tms, world, 15) == 1
    assert precache.fast_depth(tms, world, 0) == -1
