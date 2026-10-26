#!/bin/sh
# Inside the test container (docker-compose.test.yml): compile the styles the
# tile tests read, then the suite and the linter. Not run by hand.
set -eu

# The styles step reads the database. If it fails -- no database, or no
# `li` imported -- the tests that need compiled styles skip with a reason.
python /app/tools/manage.py compile-styles li >/dev/null || echo 'styles not compiled; the tests reading them will skip' >&2
python -m pytest -p no:cacheprovider "$@"
# From the repository root, so that `src = ["app"]` makes importer/lib
# first-party and the per-file ignores resolve.
python -m ruff check --no-cache app/
