#!/bin/sh
set -eu
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}"
export PORTAL_ENV="${PORTAL_ENV:-production}"
export PORTAL_SECURE_COOKIE="${PORTAL_SECURE_COOKIE:-1}"
export PYTHONPATH="/srv/portal"
cd /srv/portal
# alembic opcional no start se ainda não rodou no entrypoint
if [ -f alembic.ini ]; then
  alembic upgrade head || true
fi
exec uvicorn app.main:app --host 127.0.0.1 --port 9000 --proxy-headers --forwarded-allow-ips=*
