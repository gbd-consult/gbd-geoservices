#!/bin/bash
#
# deploy.sh -- build the image on the server and ship the stack definition
# and its configuration.
#
#   app/scripts/deploy.sh <ssh-host>          e.g.  app/scripts/deploy.sh geoservices
#
# <ssh-host> is a Host entry from ~/.ssh/config. Nothing is required in the
# environment.
#
# The image is built on the server, from the build context copied to src/
# there: no registry, no credentials, and an image of the server's own
# architecture whatever machine this runs on (an arm64 Mac builds arm64,
# which an x86_64 server cannot run). Publishing to Docker Hub is a separate
# step, app/scripts/publish.sh, which no deploy needs.
#
# The stack lives in /opt/gbd-geoservices/v0.3 on the server. This script
# copies three things there: the build context (Dockerfile, requirements.txt,
# app/) to src/, and docker-compose.yml and config/, the deployment's
# configuration, from this checkout:
#
#   config/options.yaml              options, API keys
#   config/postgres.env              database credentials
#   config/postgresql.conf           config/pg_hba.conf        config/Caddyfile
#   config/pgbouncer.ini
#
# config/ is git-ignored -- it holds the production password and the API
# keys -- so it exists only here and on the server.
# Create it from config.example/ (see its README.md); this script checks it
# before building anything and never writes to it. The code is in the image.
#
# It does not touch the running stack: nothing is restarted, imported or
# compiled. The server keeps running the previous image and configuration
# until `manage.sh reload` (the app: image, options.yaml) or `manage.sh
# restart` (the whole stack, for the other config files) on the server; the
# app compiles the styles when it starts.

set -euo pipefail

#: The server's own image, never pulled: not publish.sh's gbdconsult/
#: repository, so a `docker compose pull` cannot replace it with whatever
#: was last published.
IMAGE_REPO=gbd-geoservices
#: The moving tag docker-compose.yml runs.
MOVING_TAG=0.3
BASE=/opt/gbd-geoservices/v0.3

usage() {
    echo "usage: $0 <ssh-host>     (a Host from ~/.ssh/config, e.g. geoservices)" >&2
}

if [ $# -ne 1 ] || [ -z "$1" ] || [ "${1#-}" != "$1" ]; then
    usage
    exit 2
fi
SSH_HOST=$1

REPO=$(realpath "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../..")
CONFIG=$REPO/config
CONFIG_OPTIONS=$CONFIG/options.yaml
CONFIG_ENV=$CONFIG/postgres.env

VERSION=$(sed -n "s/^__version__ = ['\"]\(.*\)['\"]$/\1/p" "$REPO/app/lib/version.py")
if [ -z "$VERSION" ]; then
    echo "error: could not read __version__ from app/lib/version.py" >&2
    exit 1
fi
# What /status reports as `build`, so a restarted server can be told apart
# from one still on the previous image. -dirty: built from uncommitted code.
BUILD_ID=$(git -C "$REPO" rev-parse --short HEAD)
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
    BUILD_ID="$BUILD_ID-dirty"
fi

DEPLOY_DONE=
report() {
    local rc=$?
    if [ -z "$DEPLOY_DONE" ] && [ "$rc" -ne 0 ]; then
        echo "==> Deploy to $SSH_HOST FAILED (exit $rc)." >&2
    fi
}
trap report EXIT

step() { echo; echo "==> $*"; }

# One value out of config/options.yaml, e.g. `config_value host`; empty
# when it is not set. Read here, on this machine: nothing secret is sent to
# the server except by copying the file itself. Needs PyYAML, as
# gen_model.sh does.
config_value() {
    python3 - "$CONFIG_OPTIONS" "$1" <<'PY'
import sys, yaml
node = yaml.safe_load(open(sys.argv[1])) or {}
for part in sys.argv[2].split('.'):
    node = node.get(part) if isinstance(node, dict) else None
print('' if node is None else node)
PY
}

# Before anything is built: is config/ complete, and filled in rather than
# copied from the template?
check_config() {
    step "Checking $CONFIG"
    local problems=() f host
    for f in options.yaml postgres.env postgresql.conf pg_hba.conf pgbouncer.ini Caddyfile; do
        [ -f "$CONFIG/$f" ] || problems+=("missing config/$f")
    done
    if [ -f "$CONFIG_OPTIONS" ]; then
        if ! python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' "$CONFIG_OPTIONS" 2>/dev/null; then
            problems+=("config/options.yaml is not valid YAML")
        else
            if grep -q CHANGEME "$CONFIG_OPTIONS"; then
                problems+=("config/options.yaml: replace every CHANGEME (keys)")
            fi
            [ -n "$(config_value serve_area)" ] || problems+=("config/options.yaml: set serve_area")
            host=$(config_value host)
            case "$host" in
                ''|*example.org) problems+=("config/options.yaml: set host") ;;
                *)
                    # Caddy cannot read options.yaml, so the name is in the Caddyfile
                    # too; out of step, Caddy gets a certificate for a name
                    # nobody requests.
                    if [ -f "$CONFIG/Caddyfile" ] && ! grep -qE "^${host//./\\.}[[:space:]]*\{" "$CONFIG/Caddyfile"; then
                        problems+=("config/Caddyfile has no site block for $host (options.yaml's host)")
                    fi ;;
            esac
        fi
    fi
    if [ -f "$CONFIG_ENV" ]; then
        grep -qE '^POSTGRES_PASSWORD=.' "$CONFIG_ENV" \
            || problems+=("config/postgres.env: set POSTGRES_PASSWORD")
        grep -q CHANGEME "$CONFIG_ENV" \
            && problems+=("config/postgres.env: replace CHANGEME")
    fi
    for f in "$CONFIG_OPTIONS" "$CONFIG_ENV"; do
        [ -f "$f" ] || continue
        case "$(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f")" in
            *[1-7]) problems+=("config/$(basename "$f") is readable by others: chmod 600 it") ;;
        esac
    done
    if [ -f "$CONFIG/Caddyfile" ]; then
        grep -q 'example\.org' "$CONFIG/Caddyfile" \
            && problems+=("config/Caddyfile still has the template's example.org")
        # Caddy is given no environment, so a {$HOST}-style placeholder
        # expands to nothing. Caddy starts either way and serves nothing.
        grep -qE '^[^#]*\{\$[A-Z_]+\}' "$CONFIG/Caddyfile" \
            && problems+=("config/Caddyfile uses {\$...} environment placeholders; nothing sets them -- write the values in (config.example/Caddyfile)")
        grep -qE '^[[:space:]]*reverse_proxy[[:space:]]+app:8000([[:space:]]|$)' "$CONFIG/Caddyfile" \
            || problems+=("config/Caddyfile does not proxy to app:8000, where the app listens")
    fi
    if [ -f "$CONFIG/postgresql.conf" ] \
            && grep -qE '^[[:space:]]*(fsync|full_page_writes)[[:space:]]*=[[:space:]]*off' "$CONFIG/postgresql.conf"; then
        problems+=("config/postgresql.conf turns off fsync or full_page_writes -- config.local's dev shortcut, never production's")
    fi
    if [ "${#problems[@]}" -eq 0 ]; then
        echo "==> OK: config/ is complete"
        return
    fi
    echo "error: config/ is not ready to deploy:" >&2
    printf '  - %s\n' "${problems[@]}" >&2
    echo "  (start from config.example/: cp -r config.example config && chmod 600 config/options.yaml config/postgres.env)" >&2
    exit 1
}

check_server() {
    step "Checking $SSH_HOST:$BASE"
    local report
    # shellcheck disable=SC2087 # $BASE is meant to expand locally
    report=$(ssh "$SSH_HOST" bash -s -- "$BASE" <<'REMOTE'
set -u
base=$1
docker compose version >/dev/null 2>&1 || echo "NODOCKER"
command -v rsync >/dev/null || echo "NORSYNC"
mkdir -p "$base/src" "$base/config" "$base/data" "$base/pgdata" "$base/caddy/data" "$base/caddy/config" \
    2>/dev/null || echo "NOMKDIR"
REMOTE
)
    if [ -z "$report" ]; then
        echo "==> OK: docker compose and rsync present, $BASE in place"
        return
    fi
    echo "error: $SSH_HOST is not ready to run the 0.3 stack:" >&2
    while read -r line; do
        case "$line" in
            NODOCKER)  echo "  - docker compose is not installed" >&2 ;;
            NORSYNC)   echo "  - rsync is not installed" >&2 ;;
            NOMKDIR)   echo "  - cannot create $BASE (run once: sudo mkdir -p $BASE && sudo chown \$USER $BASE)" >&2 ;;
        esac
    done <<< "$report"
    exit 1
}

# The build context is what .dockerignore allows, and --delete keeps src/
# exactly that: a file removed here must not linger in the next image.
build_on_server() {
    step "Copying the build context to $SSH_HOST:$BASE/src"
    (cd "$REPO" && rsync -rtl --delete \
        --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
        --exclude app/tools/.cache \
        .dockerignore Dockerfile requirements.txt app "$SSH_HOST:$BASE/src/")

    step "Building $IMAGE_REPO:$VERSION ($BUILD_ID) on $SSH_HOST"
    # shellcheck disable=SC2029 # expanded locally on purpose
    ssh "$SSH_HOST" "docker build --build-arg GBD_BUILD_ID=$BUILD_ID \
        --tag $IMAGE_REPO:$VERSION --tag $IMAGE_REPO:$MOVING_TAG $BASE/src"
}

# What ship() changed on the server: config/ files by name, for the log.
CHANGED=

# The server needs the stack definition and config/ -- the code is in the
# image. --inplace: postgres, pgbouncer and caddy mount their files one by
# one, and a single-file mount keeps the inode it started with, so a copy
# that renamed a new file into place would leave a running container on the
# old one.
# Permissions: postgres reads its two files as its own user, so those are
# world-readable; options.yaml with the keys is read by root only (the app), and
# postgres.env with the password by compose, as the user running it.
# Set by chmod on the server, not rsync --chmod: macOS's rsync (openrsync)
# refuses GNU's `D755,F644` and ignores the option altogether.
ship() {
    step "Copying docker-compose.yml and config/ to $SSH_HOST:$BASE"
    scp -q "$REPO/docker-compose.yml" "$REPO/app/scripts/manage.sh" "$REPO/app/scripts/setup.sh" "$SSH_HOST:$BASE/"
    CHANGED=$( {
        rsync -rt --inplace --itemize-changes \
            --exclude options.yaml --exclude postgres.env \
            "$CONFIG/" "$SSH_HOST:$BASE/config/"
        rsync -t --inplace --itemize-changes \
            "$CONFIG_OPTIONS" "$CONFIG_ENV" "$SSH_HOST:$BASE/config/"
    } | awk '$1 ~ /^[<>]f/ { print $2 }')
    # shellcheck disable=SC2029 # expanded locally on purpose
    ssh "$SSH_HOST" "chmod 755 $BASE/config \
        && chmod 600 $BASE/config/options.yaml $BASE/config/postgres.env \
        && find $BASE/config -type f ! -name options.yaml ! -name postgres.env -exec chmod 644 {} +"
    if [ -n "$CHANGED" ]; then
        echo "==> changed: $(echo "$CHANGED" | tr '\n' ' ')"
    fi
}

finish() {
    DEPLOY_DONE=1
    cat <<EOF

==> Deploy of $VERSION ($BUILD_ID) to $SSH_HOST succeeded. The server still
    runs what it ran before. To start the new image and options.yaml:

        ssh $SSH_HOST $BASE/manage.sh reload

    or, for a changed postgresql.conf, pg_hba.conf, pgbouncer.ini, Caddyfile
    or postgres.env, the whole stack:

        ssh $SSH_HOST $BASE/manage.sh restart
EOF
}

check_config
check_server
build_on_server
ship
finish
