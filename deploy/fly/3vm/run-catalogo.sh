#!/bin/sh
set -eu
export CATALOGO_DATABASE_PATH="${CATALOGO_DATABASE_PATH:-/data/catalogo/catalogo.db}"
export CATALOGO_SECURE_COOKIE="${CATALOGO_SECURE_COOKIE:-1}"
# 3-VM: catalogo atras de https://app2037.fly.dev/catalogo
export CATALOGO_PUBLIC_BASE_URL="${CATALOGO_PUBLIC_BASE_URL:-https://app2037.fly.dev/catalogo}"
export CATALOGO_URL_PREFIX="${CATALOGO_URL_PREFIX:-/catalogo}"
export PYTHONPATH="/srv/catalogo"
mkdir -p "$(dirname "$CATALOGO_DATABASE_PATH")"
cd /srv/catalogo
exec uvicorn app.main:app --host 127.0.0.1 --port 8003 --proxy-headers --forwarded-allow-ips=*