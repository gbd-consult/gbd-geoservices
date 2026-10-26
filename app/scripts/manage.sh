#!/bin/sh
#
# manage.sh -- reload the app or restart the stack on the server, or run a
# manage.py subcommand in its app container.
#
#   ./manage.sh reload          the app only: new image, options.yaml, import
#   ./manage.sh restart         the whole stack: docker compose down, then up
#   ./manage.sh import de_sh    in the background, logging to data/import.log
#   ./manage.sh update de_sh    import in the foreground, then reload: for cron
#   ./manage.sh drop-cache      any other argument: a manage.py subcommand
#
# deploy.sh copies it next to docker-compose.yml on the server. deploy.sh
# only builds the image and copies files, and `import` writes a new schema
# beside the served one; the app takes them up when it is recreated. It
# compiles the styles for the newest import when it starts, so nothing here
# does. The tile cache is kept; `./manage.sh drop-cache` empties it.
#
# `reload` recreates the app and nothing else: postgres, pgbouncer and Caddy
# keep running with the configuration they have. A change to postgresql.conf,
# pg_hba.conf, pgbouncer.ini, the Caddyfile or postgres.env takes `restart`,
# which stops everything and starts it again -- `down` removes the old
# containers and their logs with them. Both return once the containers are
# started, not healthy: the app compiles the styles and loads its Map pool
# for minutes after that, which `docker compose logs -f app` shows.
#
# Everything but `import` runs in the foreground and writes to stdout.
# `import` runs for minutes to hours, so it runs detached in the app
# container (`exec -d`), where neither a dropped ssh connection nor a Ctrl-C
# reaches it, and returns at once. The import appends to data/import.log
# itself, under a line naming the run, and holds data/import.status while
# it runs; a second import refuses to start. `update` waits for the import
# and reloads only if it succeeded, so a cron job needs nothing else.

set -eu

if [ $# -eq 0 ]; then
    echo "usage: $0 reload | restart | <manage.py subcommand> [args...]     e.g. $0 import de_sh" >&2
    exit 2
fi

cd "$(dirname "$0")"

# -T: no terminal is attached under cron, and `exec` without it
# fails with "the input device is not a TTY".
manage_py() {
    docker compose exec -T app python tools/manage.py "$@"
}

import_background() {
    if [ -e data/import.status ]; then
        echo "warning: data/import.status exists: $(cat data/import.status)" >&2
    fi
    docker compose exec -d app python tools/manage.py "$@"
    echo "import started, tail -f $PWD/data/import.log to monitor"
}

reload() {
    # --no-deps: postgres and pgbouncer are left as they are. The app reads
    # options.yaml once, when it starts; `up` alone recreates it only for a
    # new image or environment.
    docker compose up -d --no-deps --force-recreate app
    echo "app recreated, docker compose logs -f app to monitor"
}

restart() {
    docker compose down --remove-orphans
    docker compose up -d
    echo "stack started, docker compose logs -f to monitor"
}

case "$1" in
    reload)       reload ;;
    restart)      restart ;;
    import)       import_background "$@" ;;
    update)       shift; manage_py import "$@"; reload ;;
    *)            manage_py "$@" ;;
esac
