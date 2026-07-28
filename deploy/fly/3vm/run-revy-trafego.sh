#!/bin/sh
set -eu
# Mesmo SQLite/Postgres do portal — fonte única de campanhas/ROI/CAPI.
export REVY_TRAFEGO_DATABASE_URL="${REVY_TRAFEGO_DATABASE_URL:-${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}}"
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}"
export REVY_TRAFEGO_SECURE_COOKIE="${REVY_TRAFEGO_SECURE_COOKIE:-1}"
export REVY_TRAFEGO_URL_PREFIX="${REVY_TRAFEGO_URL_PREFIX:-/trafego}"
# Cutover B5: este processo é o dono dos workers (shared DB com o portal).
export REVY_TRAFEGO_CAPI_WORKER="${REVY_TRAFEGO_CAPI_WORKER:-1}"
export REVY_TRAFEGO_META_SPEND_SYNC_ENABLED="${REVY_TRAFEGO_META_SPEND_SYNC_ENABLED:-1}"
# O código do worker lê PORTAL_* — forçar ON aqui (portal shell força OFF).
export PORTAL_CAPI_RETRY_ENABLED=1
export PORTAL_META_SPEND_SYNC_ENABLED=1
# Chatbot no loopback do bundle
export CHATBOT_API_URL="${CHATBOT_API_URL:-http://127.0.0.1:8001}"
export PYTHONPATH="/srv/revy-trafego"
cd /srv/revy-trafego
exec uvicorn app.main:app --host 127.0.0.1 --port 9010 --proxy-headers --forwarded-allow-ips=*
