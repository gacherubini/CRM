#!/bin/sh
# Worker do Motor: browser headed sob display virtual (Xvfb).
# Headless puro (headless_shell) é bloqueado pelo WAF do Santander/Akamai.
set -eu

export DISPLAY="${DISPLAY:-:99}"
export MOTOR_BROWSER_HEADLESS="${MOTOR_BROWSER_HEADLESS:-0}"
# Se alguém forçar headless, usa Chromium completo em vez do headless_shell.
export PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL="${PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL:-0}"

_display_num="${DISPLAY#:}"

_limpar_display_morto() {
  # Restart do container deixa lock/socket órfãos → Xvfb recusa subir e o
  # Chromium headed falha em ~200ms com "Missing X server".
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
  # Xvfb: tela virtual 1366x768 (mesmo viewport do driver).
  Xvfb "$DISPLAY" -screen 0 1366x768x24 -ac +extension GLX +render -noreset \
    >/tmp/xvfb.log 2>&1 &
  # Espera o processo e o socket existirem (restart pode ser lento no Docker Desktop).
  i=0
  while [ "$i" -lt 20 ]; do
    if pgrep -x Xvfb >/dev/null 2>&1 && [ -S "/tmp/.X11-unix/X${_display_num}" ]; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  echo "worker-entrypoint: Xvfb não subiu em $DISPLAY — veja /tmp/xvfb.log" >&2
  cat /tmp/xvfb.log >&2 || true
  return 1
}

if [ "$MOTOR_BROWSER_HEADLESS" = "0" ] || [ "$MOTOR_BROWSER_HEADLESS" = "false" ]; then
  _iniciar_xvfb || true
fi

exec python -m app.worker
