#!/bin/sh
set -eu
export DATABASE_URL="${MOTOR_DATABASE_URL:?MOTOR_DATABASE_URL required}"
export MOTOR_ENV="${MOTOR_ENV:-production}"
export MOTOR_SKIP_INIT="${MOTOR_SKIP_INIT:-1}"
export MOTOR_ORCHESTRATOR_ONLY="${MOTOR_ORCHESTRATOR_ONLY:-1}"
export MOTOR_WORKER_TIPOS="${MOTOR_WORKER_TIPOS:-api,mock}"
export MOTOR_SCREENSHOT_DIR="${MOTOR_SCREENSHOT_DIR:-/data/motor/screenshots}"
export MOTOR_STORAGE_STATE_DIR="${MOTOR_STORAGE_STATE_DIR:-/data/motor/storage_state}"
export PYTHONPATH="/srv/motor"
mkdir -p "$MOTOR_SCREENSHOT_DIR" "$MOTOR_STORAGE_STATE_DIR"
exec /srv/scripts/motor-entrypoint.sh
