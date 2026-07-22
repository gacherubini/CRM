#!/bin/sh
set -eu
export CATALOGO_DATABASE_PATH="${CATALOGO_DATABASE_PATH:-/data/catalogo/catalogo.db}"
export CATALOGO_SECURE_COOKIE="${CATALOGO_SECURE_COOKIE:-1}"
export PYTHONPATH="/srv/catalogo"
mkdir -p "$(dirname "$CATALOGO_DATABASE_PATH")"
cd /srv/catalogo
exec uvicorn app.main:app --host 127.0.0.1 --port 8003 --proxy-headers --forwarded-allow-ips=*
