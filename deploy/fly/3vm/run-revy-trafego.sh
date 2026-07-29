#!/bin/sh
set -eu
# Banco próprio: vendas chegam por projeção HTTP/outbox; nunca ler o schema do Portal.
export REVY_TRAFEGO_DATABASE_URL="${REVY_TRAFEGO_DATABASE_URL:-sqlite:////data/revy-trafego/revy_trafego.db}"
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}"
export REVY_TRAFEGO_SECURE_COOKIE="${REVY_TRAFEGO_SECURE_COOKIE:-1}"
export REVY_TRAFEGO_URL_PREFIX="${REVY_TRAFEGO_URL_PREFIX:-/trafego}"
# Este processo é o único dono dos workers de mídia.
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
