#!/bin/sh
# Fly.io: API always-on + worker leve (orquestrador / API / mock).
# Playwright roda em Machines sob demanda (on-demand-worker-entrypoint.sh).
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

# Orquestrador: sem Xvfb/Chromium. Só processa tipo api/mock (e acorda slots Playwright).
# Override: MOTOR_ORCHESTRATOR_ONLY=0 volta ao worker headed (não usar com 512MB).
_orch="${MOTOR_ORCHESTRATOR_ONLY:-1}"
_tipos="${MOTOR_WORKER_TIPOS:-api,mock}"

if [ "$_orch" = "1" ] || [ "$_orch" = "true" ] || [ "$_orch" = "yes" ]; then
  export MOTOR_WORKER_TIPOS="${MOTOR_WORKER_TIPOS:-api,mock}"
  export MOTOR_WORKER_ON_DEMAND=0
  # Evita subir Xvfb; worker de API não precisa de display.
  export MOTOR_BROWSER_HEADLESS="${MOTOR_BROWSER_HEADLESS:-1}"
  echo "fly-entrypoint: modo orquestrador (tipos=${MOTOR_WORKER_TIPOS}, sem Xvfb)"
  python -m app.worker &
  worker_pid=$!
else
  echo "fly-entrypoint: modo worker headed (Xvfb)"
  /srv/scripts/worker-entrypoint.sh &
  worker_pid=$!
fi

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
  sleep 2
done

echo "fly-entrypoint: API ou worker encerrou; reiniciando a Machine" >&2
exit 1
