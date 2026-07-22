#!/bin/sh
set -eu
export DATABASE_URL="${CHATBOT_DATABASE_URL:?CHATBOT_DATABASE_URL required}"
export CHATBOT_SKIP_INIT="${CHATBOT_SKIP_INIT:-1}"
export PYTHONPATH="/srv/chatbot"
cd /srv/chatbot
exec uvicorn app.main:app --host 127.0.0.1 --port 8001 --proxy-headers --forwarded-allow-ips=*
