#!/bin/sh
set -eu
export DATABASE_URL="${ESTOQUE_DATABASE_URL:?ESTOQUE_DATABASE_URL required}"
export ESTOQUE_SKIP_INIT="${ESTOQUE_SKIP_INIT:-1}"
export ESTOQUE_MEDIA_STORAGE_DIR="${ESTOQUE_MEDIA_STORAGE_DIR:-/data/estoque/media}"
export PYTHONPATH="/srv/estoque"
exec /srv/scripts/estoque-entrypoint.sh
