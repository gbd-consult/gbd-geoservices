"""The option layers, and the deployment file they read.

The deployment file is config/options.yaml; the database credentials are
not in it but in postgres.env. What is pinned here is what would go wrong without a sound:
a misspelt option that leaves the default in force, and a password that
reaches the connection some way other than libpq's environment -- which
would put it in the compiled Mapnik XML.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from lib import config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """Write a deployment file, point the loader at it, and load."""
    # load() exports PG* into the process environment; keep the suite's.
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    # The dev compose file sets it, and the environment outranks the file.
    os.environ.pop('GEOSERVICES_SCHEMA', None)

    def write(content: dict) -> dict:
        path = tmp_path / 'options.yaml'
        path.write_text(yaml.safe_dump(content))
        os.environ['GEOSERVICES_CONFIG_FILE'] = str(path)
        return config.load(refresh=True)

    yield write
    # Still inside the patched environment: reload from the real file, not
    # the temporary one, so the cache is what the rest of the suite expects.
    os.environ.pop('GEOSERVICES_CONFIG_FILE', None)
    config.load(refresh=True)


def test_the_deployment_file_overrides_the_defaults(deployment):
    options = deployment({'serve_area': 'de_nrw', 'db': {'pool_size': 3}})
    assert options['serve_area'] == 'de_nrw'
    assert options['db']['pool_size'] == 3
    # A nested mapping merges: the rest of `db` keeps its defaults.
    assert options['db']['port'] == 6432


def test_a_misspelt_option_is_refused(deployment):
    """`shema` would otherwise serve the default area without a word."""
    with pytest.raises(ValueError, match='shema'):
        deployment({'shema': 'de_nrw'})
    with pytest.raises(ValueError, match='db.pasword'):
        deployment({'db': {'pasword': 'x'}})


def test_the_credentials_are_not_options(deployment):
    """They are postgres.env's; a deployment file still carrying them is refused rather
    than holding a second password that the app would ignore."""
    with pytest.raises(ValueError, match='db.password'):
        deployment({'db': {'password': 'x'}})


def test_mappings_keyed_by_grid_are_values_not_branches(deployment):
    # precache's keys are grid ids; a new one is a value, not a misspelling.
    options = deployment({'precache': {'grid_1': 5}})
    assert options['precache']['grid_1'] == 5


def test_a_deployment_adds_an_area_and_keeps_the_defaults(deployment):
    # areas' keys are area names; a new one is a value, not a misspelling.
    options = deployment({'areas': {'area_1': 'europe/area_1-latest.osm.pbf'}})
    assert options['areas']['area_1'] == 'europe/area_1-latest.osm.pbf'
    assert 'de_sh' in options['areas']


def test_the_connection_goes_to_libpq_and_nowhere_else(deployment):
    """Mapnik's datasources carry no connection parameters; libpq reads these."""
    os.environ.update(POSTGRES_DB='database_1', POSTGRES_USER='user_1',
                      POSTGRES_PASSWORD='password_1')
    deployment({'db': {'host': 'db.internal', 'port': 6543}})
    assert os.environ['PGHOST'] == 'db.internal'
    assert os.environ['PGPORT'] == '6543'
    assert os.environ['PGDATABASE'] == 'database_1'
    assert os.environ['PGUSER'] == 'user_1'
    assert os.environ['PGPASSWORD'] == 'password_1'
    from lib import db
    assert db.conninfo() == ''


def test_an_empty_environment_variable_is_unset(deployment, monkeypatch):
    """Compose passes `${GEOSERVICES_SERVE_AREA:-}` as an empty string when the
    variable is unset; it must not blank the file's area."""
    monkeypatch.setitem(os.environ, 'GEOSERVICES_SERVE_AREA', '')
    assert deployment({'serve_area': 'de_nrw'})['serve_area'] == 'de_nrw'
    monkeypatch.setitem(os.environ, 'GEOSERVICES_SERVE_AREA', 'li')
    assert deployment({'serve_area': 'de_nrw'})['serve_area'] == 'li'


@pytest.mark.parametrize('directory', ['config.local', 'config.test', 'config.example'])
def test_the_tracked_deployment_files_name_only_real_options(directory):
    """A template naming a removed option would be copied into config/ and
    then refused on the server, mid-deploy."""
    path = ROOT / directory / 'options.yaml'
    defaults = config._read(config.DEFAULTS_PATH)
    assert config._read_deployment(path, defaults)


def postgres_env(directory: str) -> dict[str, str]:
    lines = (ROOT / directory / 'postgres.env').read_text().splitlines()
    return dict(line.split('=', 1) for line in lines if line and not line.startswith('#'))


@pytest.mark.parametrize('directory', ['config.local', 'config.test', 'config.example'])
def test_the_tracked_postgres_env_files_set_the_credentials(directory):
    """The names the postgres image initialises from, and lib.config maps."""
    assert set(postgres_env(directory)) == set(config.POSTGRES_ENV)


def test_the_example_holds_no_real_secret():
    example = yaml.safe_load((ROOT / 'config.example' / 'options.yaml').read_text())
    assert postgres_env('config.example')['POSTGRES_PASSWORD'] == 'CHANGEME'
    assert all(record['key'] == 'CHANGEME' for record in example['keys'])
