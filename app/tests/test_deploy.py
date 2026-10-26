"""The deployed stack's definition, and the checks the deploy relies on.

Nothing here needs a server. What is pinned is what would go wrong
silently: a password in a tracked file, a port published past the firewall,
a key in a log line, an image tag another version's deploys overwrite.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / 'docker-compose.yml'
LOCAL_COMPOSE = ROOT / 'docker-compose.local.yml'
TEST_COMPOSE = ROOT / 'docker-compose.test.yml'
DEPLOY = ROOT / 'app' / 'scripts' / 'deploy.sh'
PUBLISH = ROOT / 'app' / 'scripts' / 'publish.sh'
MANAGE = ROOT / 'app' / 'scripts' / 'manage.sh'
#: The production template and the dev stack's. config/ itself is git-ignored
#: and not here to test; deploy.sh checks it before every deploy.
CADDYFILES = [ROOT / 'config.example' / 'Caddyfile', ROOT / 'config.local' / 'Caddyfile']


@pytest.fixture(scope='module')
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


@pytest.fixture(scope='module')
def local_compose() -> dict:
    return yaml.safe_load(LOCAL_COMPOSE.read_text())


@pytest.fixture(scope='module')
def test_compose() -> dict:
    return yaml.safe_load(TEST_COMPOSE.read_text())


def service(compose, name):
    return compose['services'][name]


def image_tag(image: str) -> str:
    """The tag compose runs: the default of `${GBD_TAG:-0.3}`, or a literal."""
    match = re.search(r':\$\{GBD_TAG:-([^}]+)\}$', image)
    return match.group(1) if match else image.rsplit(':', 1)[1]


# --- docker-compose.yml --------------------------------------------------

def test_the_four_services(compose):
    assert set(compose['services']) == {'postgres', 'pgbouncer', 'app', 'caddy'}


def test_no_credential_is_in_any_compose_file(compose, local_compose, test_compose):
    """A compose file is tracked, so it must not carry the password.

    Postgres and the app both read it from postgres.env in the config
    directory -- one copy, so the two cannot drift apart.
    """
    for stack in (compose, local_compose, test_compose):
        for spec in stack['services'].values():
            assert not any('PASSWORD' in name for name in spec.get('environment') or {})


@pytest.mark.parametrize('stack, directory', [('compose', 'config'),
                                             ('local_compose', 'config.local')])
def test_each_stack_reads_its_own_config_directory(stack, directory, request):
    """docker-compose.yml loads config/, docker-compose.local.yml config.local/."""
    spec = request.getfixturevalue(stack)['services']
    assert f'./{directory}:/config:ro' in spec['app']['volumes']
    assert spec['postgres']['volumes'][1:] == [
        f'./{directory}/postgresql.conf:/etc/postgresql/postgresql.conf:ro',
        f'./{directory}/pg_hba.conf:/etc/postgresql/pg_hba.conf:ro']
    assert f'./{directory}/Caddyfile:/etc/caddy/Caddyfile:ro' in spec['caddy']['volumes']
    assert spec['pgbouncer']['volumes'] == [f'./{directory}/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro']
    assert spec['postgres']['env_file'] == f'./{directory}/postgres.env'
    assert spec['app']['env_file'] == f'./{directory}/postgres.env'
    assert 'env_file' not in spec['caddy']
    command = spec['postgres']['command']
    assert 'config_file=/etc/postgresql/postgresql.conf' in command
    # Named in postgresql.conf, next to which the compose file mounts it.
    assert postgres_settings(directory)['hba_file'] == '/etc/postgresql/pg_hba.conf'


def test_caddy_is_not_given_the_password(compose, local_compose):
    """The container facing the internet mounts its Caddyfile, not config/."""
    for stack in (compose, local_compose):
        for volume in service(stack, 'caddy')['volumes']:
            assert not volume.startswith('./config') or volume.split(':')[0].endswith('/Caddyfile')


def test_config_is_git_ignored_and_never_in_the_image():
    ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q',
                              'config/options.yaml'], capture_output=True)
    if ignored.returncode == 128:
        pytest.skip('git cannot read this checkout here (a worktree, mounted without its git dir)')
    assert ignored.returncode == 0
    # .dockerignore is an allowlist; config/ must not be on it.
    allowed = [line for line in (ROOT / '.dockerignore').read_text().splitlines()
               if line.startswith('!')]
    assert not any('config' in line for line in allowed)


def test_the_app_runs_the_image_built_on_the_server_never_a_pulled_one(compose):
    """deploy.sh builds the image on the server. Under publish.sh's
    gbdconsult/ name, a `docker compose pull` would swap it for whatever was
    last published; and a `build:` here would build without the commit id."""
    app = service(compose, 'app')
    assert not app['image'].startswith('gbdconsult/')
    assert app['pull_policy'] == 'never'
    assert image_tag(app['image']) == '0.3'
    assert not any('build' in spec for spec in compose['services'].values())


def test_the_app_is_published_on_loopback_only(compose):
    """Published on 0.0.0.0, the app is reachable past ufw, because
    Docker's rules run ahead of it, and a spoofed X-Forwarded-For opens the
    loopback-only reload route to anyone."""
    assert service(compose, 'app')['ports'] == ['127.0.0.1::8000']


def test_postgres_publishes_nothing(compose):
    # A published port is reachable past ufw.
    assert 'ports' not in service(compose, 'postgres')


def test_pgbouncer_publishes_nothing(compose, local_compose):
    for stack in (compose, local_compose):
        assert 'ports' not in service(stack, 'pgbouncer')


def test_caddy_cannot_reach_pgbouncer(compose):
    """pgbouncer trusts every client that reaches it, so the container
    facing the internet shares no network with it."""
    assert compose['networks']['db']['internal'] is True
    assert service(compose, 'pgbouncer')['networks'] == ['db']
    assert service(compose, 'postgres')['networks'] == ['db']
    assert 'db' in service(compose, 'app')['networks']
    assert 'networks' not in service(compose, 'caddy')


def test_the_app_connects_through_pgbouncer():
    """Straight to postgres, every Map load costs ~0.95 s instead of 0.06 s.
    Nothing fails either way."""
    defaults = yaml.safe_load((ROOT / 'app' / 'config' / 'options.yaml').read_text())
    assert defaults['db']['host'] == 'pgbouncer'
    for directory in ('config.example', 'config.local'):
        options = yaml.safe_load((ROOT / directory / 'options.yaml').read_text()) or {}
        assert 'db' not in options, directory


@pytest.mark.parametrize('stack', ['compose', 'local_compose'])
def test_the_app_waits_for_pgbouncer(stack, request):
    """A theme that cannot load at startup is logged and not served, so the
    app must not start before pgbouncer answers."""
    spec = request.getfixturevalue(stack)['services']
    assert spec['app']['depends_on'] == {'pgbouncer': {'condition': 'service_healthy'}}
    assert 'healthcheck' in spec['pgbouncer']


def test_reload_recreates_the_app_and_nothing_else():
    reload = re.search(r'^reload\(\) \{.*?^\}', MANAGE.read_text(), re.M | re.S).group(0)
    assert 'docker compose up -d --no-deps --force-recreate app' in reload
    assert 'down' not in reload


def test_reload_and_restart_return_without_waiting():
    """The app takes minutes to compile the styles and load its Map pool;
    `docker compose logs -f` is how to watch it."""
    assert '--wait' not in MANAGE.read_text()


def postgres_settings(directory: str) -> dict[str, str]:
    settings = {}
    for line in (ROOT / directory / 'postgresql.conf').read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            name, value = (part.strip() for part in line.split('=', 1))
            settings[name] = value.strip("'")
    return settings


def test_production_postgres_keeps_its_durability():
    """fsync=off and friends are the dev stack's shortcut, never production's."""
    settings = postgres_settings('config.example')
    for name in ('fsync', 'full_page_writes', 'synchronous_commit'):
        assert settings.get(name, 'on') != 'off'
    assert postgres_settings('config.local')['fsync'] == 'off'


@pytest.mark.parametrize('directory', ['config.example', 'config.local'])
def test_postgres_listens_on_the_network_without_the_jit(directory):
    settings = postgres_settings(directory)
    # A config_file of our own replaces initdb's, and with it initdb's '*'.
    assert settings['listen_addresses'] == '*'
    # Measured: JIT costs every low-zoom query 50-150 ms.
    assert settings['jit'] == 'off'


@pytest.mark.parametrize('directory', ['config.example', 'config.local'])
def test_only_the_local_socket_is_trusted(directory):
    for line in (ROOT / directory / 'pg_hba.conf').read_text().splitlines():
        fields = line.split('#', 1)[0].split()
        if fields and fields[-1] == 'trust':
            assert fields[0] == 'local', line


def test_the_app_command_trusts_the_proxy_and_logs_no_key(compose):
    command = service(compose, 'app')['command']
    assert 'web.main:app' in command
    # Without it GetCapabilities advertises http://app:8000/... tile URLs.
    assert '--proxy-headers' in command
    # uvicorn's own access log writes ?key= verbatim.
    assert '--no-access-log' in command
    assert '--reload' not in command


def test_the_app_healthcheck_allows_for_the_map_pool_preload(compose):
    # Measured at 111 s for twelve themes and two grids.
    start_period = service(compose, 'app')['healthcheck']['start_period']
    assert int(start_period.rstrip('s')) >= 180


def test_only_caddy_faces_the_world(compose):
    ports = service(compose, 'caddy')['ports']
    assert {'80:80', '443:443', '443:443/udp'} == set(ports)


# --- Caddyfiles ----------------------------------------------------------

@pytest.fixture(params=CADDYFILES, ids=lambda path: path.parent.name)
def caddyfile(request) -> str:
    return request.param.read_text()


def test_caddy_proxies_to_the_app(caddyfile):
    assert 'reverse_proxy app:8000' in caddyfile


def test_caddy_strips_the_key_from_both_its_logs(caddyfile):
    """The query parameter is the one carrier that reaches a log at all.

    Twice: the site's access log, and the global default log, which is
    where Caddy writes a request's error -- a 502, a timeout -- with the raw
    URI unless it is filtered there too.
    """
    assert len(re.findall(r'request>uri query \{\s*delete key\s*\}', caddyfile)) == 2
    assert re.search(r'^\tlog default \{', caddyfile, re.M)


def test_caddy_does_not_rate_limit(caddyfile):
    # The app does, on the key record; both would be worse.
    assert 'rate_limit' not in caddyfile


def test_caddy_pins_the_forwarded_for_header(caddyfile):
    assert 'header_up X-Forwarded-For {remote_host}' in caddyfile


# --- deploy.sh -----------------------------------------------------------

@pytest.mark.parametrize('script', [DEPLOY, PUBLISH, MANAGE], ids=lambda path: path.name)
def test_the_script_parses(script):
    subprocess.run(['bash', '-n', str(script)], check=True)


@pytest.mark.skipif(shutil.which('shellcheck') is None, reason='shellcheck not installed')
@pytest.mark.parametrize('script', [DEPLOY, PUBLISH, MANAGE], ids=lambda path: path.name)
def test_the_script_passes_shellcheck(script):
    subprocess.run(['shellcheck', str(script)], check=True)


@pytest.mark.parametrize('args', [[], ['--help'], ['a', 'b']])
def test_the_script_wants_exactly_one_host(args):
    result = subprocess.run(['bash', str(DEPLOY), *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'usage' in result.stderr


def test_the_script_never_writes_the_configuration():
    """It checks config/ and copies it; it never writes into it."""
    # A redirect or a tee into a config file, on one line.
    writes = re.compile(r'(?:^|[^<\w-])(?:>>?|\btee(?:\s+-a)?)[ \t]*\S*(?:CONFIG|config/)',
                        re.M)
    assert not writes.search(DEPLOY.read_text())
    # The check itself catches what it is for.
    assert writes.search('echo x > "$CONFIG_OPTIONS"')
    assert writes.search('printf x | tee $BASE/config/options.yaml')


def script_value(script: Path, name: str) -> str:
    return re.search(rf'^{name}=(\S+)$', script.read_text(), re.M).group(1)


def test_the_script_builds_the_image_compose_runs(compose):
    image = service(compose, 'app')['image']
    assert image.startswith(script_value(DEPLOY, 'IMAGE_REPO') + ':')
    assert image_tag(image) == script_value(DEPLOY, 'MOVING_TAG')


def test_the_script_builds_on_the_server_and_pushes_nothing():
    text = DEPLOY.read_text()
    assert 'docker push' not in text
    assert 'DOCKERHUB' not in text


def test_the_script_ships_manage_sh_and_setup_sh_next_to_the_compose_file():
    scp = next(line for line in DEPLOY.read_text().splitlines() if line.strip().startswith('scp '))
    assert scp.rstrip().endswith('"$SSH_HOST:$BASE/"')
    assert '"$REPO/app/scripts/manage.sh"' in scp
    assert '"$REPO/app/scripts/setup.sh"' in scp


# --- manage.sh -----------------------------------------------------------

def test_manage_wants_a_subcommand():
    result = subprocess.run(['sh', str(MANAGE)], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'usage' in result.stderr


def test_manage_runs_without_a_terminal():
    """Under cron there is no terminal: `exec` without -T fails with
    'the input device is not a TTY', and nothing runs."""
    text = MANAGE.read_text()
    assert 'docker compose exec -T app python tools/manage.py "$@"' in text
    assert 'docker compose exec app' not in text


def test_manage_detaches_only_the_import():
    """An import outlives an ssh session; everything else writes to stdout."""
    text = MANAGE.read_text()
    assert len(re.findall(r'docker compose exec -d ', text)) == 1
    assert re.search(r'^\s*import\)\s+import_background "\$@" ;;$', text, re.M)
    assert 'nohup' not in text
    assert 'manage.log' not in text


def test_manage_leaves_the_import_s_log_and_status_to_the_import():
    """It only warns: the import itself refuses to run beside another, and
    tells a leftover status file from a live one."""
    body = re.search(r'^import_background\(\) \{.*?^\}', MANAGE.read_text(), re.M | re.S).group(0)
    assert 'exit' not in body
    assert 'rm ' not in body and '>' not in body.replace('>&2', '')


def test_update_reloads_only_after_the_import_succeeded():
    """A cron job runs `update`: reloading while the import still runs, or
    after it failed, would serve the old schema or nothing new."""
    text = MANAGE.read_text()
    assert re.search(r'^\s*update\)\s+shift; manage_py import "\$@"; reload ;;$', text, re.M)
    assert text.index('set -eu') < text.index('update)')


def test_manage_leaves_the_styles_to_the_app():
    """The app compiles them when it starts, for the schema it resolved;
    a second compile here would be for whatever schema this one resolved."""
    assert 'compile-styles' not in MANAGE.read_text().split('set -eu', 1)[1]


def test_restart_starts_afresh():
    hard = re.search(r'^restart\(\) \{.*?^\}', MANAGE.read_text(), re.M | re.S).group(0)
    assert hard.index('down') < hard.index('up -d')


def test_deploy_leaves_the_running_stack_alone():
    """It builds and copies; manage.sh reload or restart is what the server runs next."""
    assert not re.search(r'docker compose (up|down|restart|stop|exec|run)\b', DEPLOY.read_text())


# --- publish.sh ----------------------------------------------------------

def test_publish_pushes_the_version_and_the_moving_0_3_tag_not_latest():
    """:latest belongs to another version in the same repository; this one
    must not fight it."""
    text = PUBLISH.read_text()
    assert script_value(PUBLISH, 'IMAGE_REPO') == 'gbdconsult/gbd-geoservices'
    assert script_value(PUBLISH, 'MOVING_TAG') == '0.3'
    assert 'docker push "$IMAGE_REPO:$VERSION"' in text
    assert 'docker push "$IMAGE_REPO:$MOVING_TAG"' in text
    assert 'latest' not in text.split('set -euo pipefail', 1)[1]


def test_publish_builds_for_the_servers_architecture_not_the_builders():
    """A build on an arm64 Mac is arm64 unless told otherwise, and an
    x86_64 server cannot run it."""
    assert script_value(PUBLISH, 'PLATFORM') == 'linux/amd64'
    assert '--platform "$PLATFORM"' in PUBLISH.read_text()


@pytest.mark.parametrize('args', [['a'], ['--help']])
def test_publish_takes_no_arguments(args):
    result = subprocess.run(['bash', str(PUBLISH), *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'usage' in result.stderr


# --- manage.py compile-styles reloads -------------------------------------

def test_styles_reports_a_server_that_is_not_running():
    """compile-styles generates, then reloads. No server is not an
    error -- it loads the styles when it starts."""
    from tools import manage
    message = manage.reload_server('http://127.0.0.1:9/internal/reload')
    assert 'no server answered' in message
