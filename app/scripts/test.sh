#!/bin/sh
# Run the test suite and the linter in the test stack. Host-side: this is one
# of the few things that runs outside a container, because it is what starts one.
#
#   app/scripts/test.sh              the whole suite
#   app/scripts/test.sh -k geometry  pytest arguments are passed through
#
# docker-compose.test.yml reads the dev stack's database on port 7778; the
# database-backed tests skip with a reason rather than failing if it is not up.
set -eu
cd "$(dirname "$0")/../.."

exec docker compose -f docker-compose.test.yml run --rm --build test "$@"
