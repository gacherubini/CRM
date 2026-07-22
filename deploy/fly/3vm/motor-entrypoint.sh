#!/bin/sh
# Motor orquestrador: API + worker api/mock (sem Playwright/Xvfb).
set -eu
cd /srv/motor
export MOTOR_ORCHESTRATOR_ONLY="${MOTOR_ORCHESTRATOR_ONLY:-1}"
export MOTOR_WORKER_TIPOS="${MOTOR_WORKER_TIPOS:-api,mock}"
export MOTOR_WORKER_ON_DEMAND=0
export MOTOR_BROWSER_HEADLESS="${MOTOR_BROWSER_HEADLESS:-1}"

worker_pid=""
api_pid=""

encerrar() {
  [ -z "$api_pid" ] || kill "$api_pid" 2>/dev/null || true
  [ -z "$worker_pid" ] || kill "$worker_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
  wait "$worker_pid" 2>/dev/null || true
}
trap encerrar EXIT INT TERM

echo "motor-entrypoint: orquestrador tipos=${MOTOR_WORKER_TIPOS}"
python -m app.worker &
worker_pid=$!
uvicorn app.main:app --host 127.0.0.1 --port 8004 &
api_pid=$!

while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
  sleep 2
done
echo "motor-entrypoint: API ou worker encerrou" >&2
exit 1
