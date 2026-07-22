#!/bin/sh
# Worker Playwright sob demanda: Xvfb + processa fila do provedor + exit 0.
# A Machine com restart on-failure fica stopped após saída limpa.
set -eu

export DISPLAY="${DISPLAY:-:99}"
export MOTOR_BROWSER_HEADLESS="${MOTOR_BROWSER_HEADLESS:-0}"
export PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL="${PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL:-0}"
export MOTOR_WORKER_ON_DEMAND="${MOTOR_WORKER_ON_DEMAND:-1}"
export MOTOR_WORKER_IDLE_STOP_SECONDS="${MOTOR_WORKER_IDLE_STOP_SECONDS:-60}"

# Provedor obrigatório em slots dedicados (ex.: santander).
# MACHINE Launch / seed de imagem: MOTOR_WORKER_SEED=1 → exit 0 (stopped, sem crash-loop).
if [ -z "${MOTOR_WORKER_PROVEDOR:-}" ]; then
  if [ "${MOTOR_WORKER_SEED:-}" = "1" ] || [ "${MOTOR_WORKER_SEED:-}" = "true" ]; then
    echo "on-demand-worker: seed/image machine (sem MOTOR_WORKER_PROVEDOR) — exit 0" >&2
    exit 0
  fi
  echo "on-demand-worker: MOTOR_WORKER_PROVEDOR não definido" >&2
  exit 1
fi

_display_num="${DISPLAY#:}"

_limpar_display_morto() {
  if pgrep -x Xvfb >/dev/null 2>&1; then
    return 0
  fi
  rm -f "/tmp/.X${_display_num}-lock" 2>/dev/null || true
  rm -f "/tmp/.X11-unix/X${_display_num}" 2>/dev/null || true
}

_iniciar_xvfb() {
  if pgrep -x Xvfb >/dev/null 2>&1; then
    return 0
  fi
  _limpar_display_morto
  Xvfb "$DISPLAY" -screen 0 1366x768x24 -ac +extension GLX +render -noreset \
    >/tmp/xvfb.log 2>&1 &
  i=0
  while [ "$i" -lt 20 ]; do
    if pgrep -x Xvfb >/dev/null 2>&1 && [ -S "/tmp/.X11-unix/X${_display_num}" ]; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  echo "on-demand-worker: Xvfb não subiu em $DISPLAY — veja /tmp/xvfb.log" >&2
  cat /tmp/xvfb.log >&2 || true
  return 1
}

if [ "$MOTOR_BROWSER_HEADLESS" = "0" ] || [ "$MOTOR_BROWSER_HEADLESS" = "false" ]; then
  _iniciar_xvfb || true
fi

echo "on-demand-worker: provedor=${MOTOR_WORKER_PROVEDOR} idle=${MOTOR_WORKER_IDLE_STOP_SECONDS}s"
exec python -m app.worker
