#!/bin/sh
set -eu
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}"
export PORTAL_ENV="${PORTAL_ENV:-production}"
export PORTAL_SECURE_COOKIE="${PORTAL_SECURE_COOKIE:-1}"
# Cutover B5: workers de mídia só no revy-trafego (:9010).
export PORTAL_CAPI_RETRY_ENABLED="${PORTAL_CAPI_RETRY_ENABLED:-0}"
export PORTAL_META_SPEND_SYNC_ENABLED="${PORTAL_META_SPEND_SYNC_ENABLED:-0}"
export PYTHONPATH="/srv/portal"
cd /srv/portal
# alembic opcional no start se ainda não rodou no entrypoint
if [ -f alembic.ini ]; then
  alembic upgrade head || true
fi
exec uvicorn app.main:app --host 127.0.0.1 --port 9000 --proxy-headers --forwarded-allow-ips=*
