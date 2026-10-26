from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from importer import params as params_module
from importer import rules as rules_module

MODEL = Path(__file__).resolve().parent.parent / 'model'
STYLES = Path(__file__).resolve().parent.parent / 'styles'
DATA = Path(__file__).resolve().parent / 'data'

# The dev deployment may narrow the served themes to shorten its restarts;
# the suite renders `default_std` and the rest regardless. Empty is "all".
os.environ['GEOSERVICES_SERVE_PALETTES'] = '[]'
os.environ['GEOSERVICES_SERVE_DETAILS'] = '[]'


@pytest.fixture(scope='session')
def raw_rules() -> list[dict]:
    return rules_module.load_rules(MODEL)


@pytest.fixture(scope='session')
def classifier() -> rules_module.Classifier:
    return rules_module.load(MODEL)


@pytest.fixture(scope='session')
def params() -> params_module.Params:
    return params_module.load(MODEL, STYLES)


@pytest.fixture(scope='session')
def styles():
    from renderer import resolve
    return resolve.load(STYLES)


@pytest.fixture(scope='session')
def tagsets() -> list[dict]:
    return json.loads((DATA / 'tagsets_sh.json').read_text())


@pytest.fixture(scope='session')
def db():
    """A connection to the dev database, or a skip.

    psycopg and the database both exist only inside the container, so on a
    host run these tests skip rather than error. Imported inside the
    fixture for the same reason.
    """
    pytest.importorskip('psycopg', reason='psycopg is installed in the container')
    from lib import db as db_module
    try:
        conn = db_module.connect(autocommit=True)
    except Exception as exc:                      # noqa: BLE001 - any failure means no database
        pytest.skip(f'no database reachable: {exc}')
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def temp_schema(db):
    """A scratch schema, dropped afterwards."""
    from psycopg import sql
    name = 'test_importer'
    ident = sql.Identifier(name)
    db.execute(sql.SQL('drop schema if exists {} cascade').format(ident))
    db.execute(sql.SQL('create schema {}').format(ident))
    try:
        yield name
    finally:
        db.execute(sql.SQL('drop schema if exists {} cascade').format(ident))


def small_schema() -> str | None:
    """The newest complete import of `li`, or None without one or a database."""
    from lib import db
    try:
        with db.connection() as conn:
            schemas = db.complete_schemas(conn, 'li')
    except Exception:                             # noqa: BLE001 - no database is no import
        return None
    return schemas[0] if schemas else None


@pytest.fixture
def small(db, monkeypatch):
    """The newest `li` (Liechtenstein) schema, with search pointed at it.

    Skips rather than fails when it is absent: the suite has to run on a
    machine that has never imported anything. `api.schema` is patched
    rather than the option set, so the override cannot leak into another
    test through the config cache.
    """
    schema = small_schema()
    if schema is None:
        pytest.skip("no 'li' import; run tools/manage.py import li")
    from search import api
    monkeypatch.setattr(api, 'schema', lambda: schema)
    api.clear_cache()
    yield schema
    api.clear_cache()
