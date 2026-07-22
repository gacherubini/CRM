#!/bin/sh
# Estoque: API + outbox worker na mesma machine (modo lab).
set -eu
cd /srv/estoque
worker_pid=""
api_pid=""

encerrar() {
  [ -z "$api_pid" ] || kill "$api_pid" 2>/dev/null || true
  [ -z "$worker_pid" ] || kill "$worker_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
  wait "$worker_pid" 2>/dev/null || true
}
trap encerrar EXIT INT TERM

python -m app.worker &
worker_pid=$!
uvicorn app.main:app --host 127.0.0.1 --port 8002 --proxy-headers --forwarded-allow-ips=* &
api_pid=$!

while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
  sleep 2
done
echo "estoque-entrypoint: API ou outbox encerrou" >&2
exit 1
