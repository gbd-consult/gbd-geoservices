"""The three configuration layers of DESIGN.md "Configuration".

    app/config/options.yaml               every option with its default, versioned
    /config/options.yaml                  the deployment: config.local/ or config/
    GEOSERVICES_<OPTION>                  environment, for compose and CI

The deployment file lives in a directory at the repository root:
docker-compose.local.yml mounts config.local/ at /config, docker-compose.yml
mounts config/. Next to it lie the other files that configure the stack --
postgresql.conf, pg_hba.conf, pgbouncer.ini, Caddyfile -- read by those
services, not here.

The database credentials are not in it but in postgres.env next to it,
which compose hands to both postgres and the app as POSTGRES_DB,
POSTGRES_USER and POSTGRES_PASSWORD: postgres creates the database from
them, and one file means the two cannot disagree. config/ is git-ignored
and reaches the server only by deploy.sh, so the production password is
never in the repository. The credentials and `db.host`/`db.port` go into the
libpq environment of this process (`_export_libpq`) and nowhere else, so
every compiled Mapnik XML still carries no connection parameters and is the
same on every deployment.

The versioned file is the *complete* list of options, which is what makes
the environment layer unambiguous and lets the deployment file be checked.
`GEOSERVICES_ONDEMAND_CACHE_MAX_MB` could otherwise mean
`ondemand.cache.max.mb` or the flat `ondemand_cache_max_mb`; since every
legal path is known up front, the lookup goes the other way -- each known
path computes the one variable name that sets it, and a variable matching no
option is ignored. A key in the deployment file matching no option is an
error instead: `serve_aera: de_nrw` would otherwise serve the default area.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ENV_PREFIX = 'GEOSERVICES_'
DEFAULTS_PATH = Path(__file__).resolve().parent.parent / 'config' / 'options.yaml'
#: Where the compose files mount config/ or config.local/. Not an option: it
#: is what locates the options.
DEPLOYMENT_PATH = Path('/config/options.yaml')

#: db option -> the libpq environment variable that carries it.
LIBPQ_ENV = {'host': 'PGHOST', 'port': 'PGPORT'}
#: postgres.env's variable, read by the postgres image -> libpq's name for it.
POSTGRES_ENV = {'POSTGRES_DB': 'PGDATABASE', 'POSTGRES_USER': 'PGUSER',
                'POSTGRES_PASSWORD': 'PGPASSWORD'}

#: Options that are mappings keyed by a value -- a grid id, an area name --
#: rather than by option names. A deployment may add a key to one, and each is
#: set from the environment as a whole, as YAML.
KEYED = frozenset({'precache', 'areas'})

_cache: dict[str, Any] | None = None


def load(*, refresh: bool = False) -> dict[str, Any]:
    """The merged options. Cached; `refresh` re-reads all three layers."""
    global _cache
    if _cache is None or refresh:
        options = _read(DEFAULTS_PATH)
        _merge(options, _read_deployment(deployment_path(), options))
        _apply_env(options)
        _export_libpq(options['db'])
        _cache = options
    return _cache


def deployment_path() -> Path:
    return Path(os.environ.get(ENV_PREFIX + 'CONFIG_FILE') or DEPLOYMENT_PATH)


def opt(path: str, default: Any = None) -> Any:
    """One option by dotted path: `opt('db.pool_size')`."""
    node: Any = load()
    for part in path.split('.'):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _read_deployment(path: Path, defaults: dict[str, Any]) -> dict[str, Any]:
    """The deployment file, refused if it names an option that does not exist.

    Absent is allowed -- the test suite and a bare `python` in the image run
    on the defaults.
    """
    if not path.is_file():
        return {}
    over = _read(path)
    unknown = _unknown(over, defaults)
    if unknown:
        raise ValueError(f'{path}: no such option: {", ".join(unknown)} '
                         f'(every option is listed in {DEFAULTS_PATH.name})')
    return over


def _unknown(over: dict[str, Any], base: dict[str, Any], prefix: str = '') -> list[str]:
    out = []
    for key, value in over.items():
        path = f'{prefix}{key}'
        if key not in base:
            out.append(path)
        elif isinstance(value, dict) and isinstance(base[key], dict) and path not in KEYED:
            out.extend(_unknown(value, base[key], path + '.'))
    return out


def _export_libpq(db: dict[str, Any]) -> None:
    """Hand the connection to libpq through its environment.

    Mapnik's PostGIS datasources are written with no host, user or password
    -- the compiled XML must not hold a credential -- and connect through
    libpq, which reads PGHOST, PGPASSWORD and the rest from the environment
    of this process. psycopg connects the same way (`db.conninfo()` is
    empty), so both reach the same database by construction, and a style
    file copied off the server tells nobody anything.

    Without postgres.env in the environment there is no password, and the
    first connection says so.
    """
    for option, variable in LIBPQ_ENV.items():
        if db.get(option) is not None:
            os.environ[variable] = str(db[option])
    for source, variable in POSTGRES_ENV.items():
        if os.environ.get(source):
            os.environ[variable] = os.environ[source]


def _merge(base: dict[str, Any], over: dict[str, Any]) -> None:
    """Recursive for mappings, replace for everything else.

    A deployment that sets `serve_grids` means *this* list, not this list
    appended to the default -- so lists replace. `precache`, keyed by grid
    id, is a mapping and merges per key.
    """
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def _apply_env(options: dict[str, Any]) -> None:
    for path, value in list(_leaves(options)):
        raw = os.environ.get(ENV_PREFIX + path.replace('.', '_').upper())
        # Empty is unset: compose passes `${GEOSERVICES_SERVE_AREA:-}` through as
        # an empty string, and an empty area would override the file's.
        if raw:
            _set(options, path, _coerce(raw, value))


def _leaves(node: Any, prefix: str = '') -> list[tuple[str, Any]]:
    """Every settable option path. A `KEYED` mapping is one value, not a branch."""
    out: list[tuple[str, Any]] = []
    for key, value in node.items():
        path = f'{prefix}{key}'
        if isinstance(value, dict) and path not in KEYED:
            out.extend(_leaves(value, path + '.'))
        else:
            out.append((path, value))
    return out


def _set(node: dict[str, Any], path: str, value: Any) -> None:
    *branch, leaf = path.split('.')
    for part in branch:
        node = node[part]
    node[leaf] = value


def _coerce(raw: str, current: Any) -> Any:
    """Parse an environment string against the shape of the default.

    Strings stay strings -- `GEOSERVICES_SERVE_AREA=de_sh` must not become
    anything cleverer -- and everything else goes through the YAML parser,
    which reads `12`, `true`, `[a, b]` and `{EPSG:3857: 12}` alike.
    """
    if isinstance(current, str):
        return raw
    return yaml.safe_load(raw)
