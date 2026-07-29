#!/usr/bin/env bash
# Migrations + dirs de dados + supervisord.
set -euo pipefail

mkdir -p \
  /data/portal \
  /data/revy-trafego \
  /data/catalogo \
  /data/estoque/media \
  /data/motor/screenshots \
  /data/motor/storage_state

export PORTAL_HOST="${PORTAL_HOST:-portal2037.fly.dev}"
export CATALOGO_HOST="${CATALOGO_HOST:-catalogo2037.fly.dev}"
export SITE_HOST="${SITE_HOST:-site2037.fly.dev}"

# Co-localização (override via secrets/env)
export MOTOR_URL="${MOTOR_URL:-http://127.0.0.1:8004}"
export ESTOQUE_API_URL="${ESTOQUE_API_URL:-http://127.0.0.1:8002}"
export ESTOQUE_PUBLIC_URL="${ESTOQUE_PUBLIC_URL:-http://127.0.0.1:8002}"
export ESTOQUE_PUBLIC_API_URL="${ESTOQUE_PUBLIC_API_URL:-http://127.0.0.1:8002}"
export CHATBOT_API_URL="${CHATBOT_API_URL:-http://127.0.0.1:8001}"
# Prefer HTTPS público: flycast DNS nem sempre resolve entre apps neste org.
export CHATBOT_AUDIO_EVOLUTION_URL="${CHATBOT_AUDIO_EVOLUTION_URL:-https://evolution2037.fly.dev}"
export CHATBOT_IMAGE_EVOLUTION_URL="${CHATBOT_IMAGE_EVOLUTION_URL:-https://evolution2037.fly.dev}"
export SIMULATION_PROVIDER="${SIMULATION_PROVIDER:-http}"
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}"
export CATALOGO_DATABASE_PATH="${CATALOGO_DATABASE_PATH:-/data/catalogo/catalogo.db}"
# Pixel do catálogo = o que a equipe salvou no Revy Tráfego (por loja).
export PORTAL_PUBLIC_URL="${PORTAL_PUBLIC_URL:-http://127.0.0.1:9000}"
export REVY_TRAFEGO_URL="${REVY_TRAFEGO_URL:-http://127.0.0.1:9010}"
export REVY_TRAFEGO_PUBLIC_URL="${REVY_TRAFEGO_PUBLIC_URL:-http://127.0.0.1:9010}"
export REVY_TRAFEGO_URL_PREFIX="${REVY_TRAFEGO_URL_PREFIX:-/trafego}"
export REVY_TRAFEGO_DATABASE_URL="${REVY_TRAFEGO_DATABASE_URL:-sqlite:////data/revy-trafego/revy_trafego.db}"
export ESTOQUE_MEDIA_STORAGE_DIR="${ESTOQUE_MEDIA_STORAGE_DIR:-/data/estoque/media}"
export MOTOR_SCREENSHOT_DIR="${MOTOR_SCREENSHOT_DIR:-/data/motor/screenshots}"
export MOTOR_STORAGE_STATE_DIR="${MOTOR_STORAGE_STATE_DIR:-/data/motor/storage_state}"

run_alembic() {
  local dir="$1"
  if [ ! -f "$dir/alembic.ini" ]; then
    echo ">> ERRO: alembic.ini ausente em $dir" >&2
    return 1
  fi
  echo ">> alembic upgrade head ($dir)"
  (cd "$dir" && alembic upgrade head)
}

if [ -n "${CHATBOT_DATABASE_URL:-}" ]; then
  export DATABASE_URL="$CHATBOT_DATABASE_URL"
  run_alembic /srv/chatbot
fi
if [ -n "${ESTOQUE_DATABASE_URL:-}" ]; then
  export DATABASE_URL="$ESTOQUE_DATABASE_URL"
  run_alembic /srv/estoque
fi
if [ -n "${MOTOR_DATABASE_URL:-}" ]; then
  export DATABASE_URL="$MOTOR_DATABASE_URL"
  run_alembic /srv/motor
fi
if [ -n "${PORTAL_DATABASE_URL:-}" ]; then
  # Portal alembic env costuma usar PORTAL_DATABASE_URL ou DATABASE_URL
  export DATABASE_URL="$PORTAL_DATABASE_URL"
  run_alembic /srv/portal
fi
if [ -n "${REVY_TRAFEGO_DATABASE_URL:-}" ]; then
  export DATABASE_URL="$REVY_TRAFEGO_DATABASE_URL"
  run_alembic /srv/revy-trafego
fi

echo ">> starting supervisord"
exec /usr/bin/supervisord -n -c /etc/supervisord.conf
