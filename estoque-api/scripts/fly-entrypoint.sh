#!/bin/sh
# Fly.io modo laboratório: API e outbox na mesma Machine.
set -eu

worker_pid=""
api_pid=""

encerrar() {
  [ -z "$api_pid" ] || kill "$api_pid" 2>/dev/null || true
  [ -z "$worker_pid" ] || kill "$worker_pid" 2>/dev/null || true
  [ -z "$api_pid" ] || wait "$api_pid" 2>/dev/null || true
  [ -z "$worker_pid" ] || wait "$worker_pid" 2>/dev/null || true
}
trap encerrar EXIT INT TERM

python -m app.worker &
worker_pid=$!
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
  sleep 2
done

echo "fly-entrypoint: API ou outbox encerrou; reiniciando a Machine" >&2
exit 1
