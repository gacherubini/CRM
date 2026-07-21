#!/usr/bin/env bash
# Always-on em todos os apps principais (sem auto_stop).
# Inclui backends + front + site. Evolution/n8n já são always-on.
#
# Pré-requisito: flyctl autenticado (fly auth login).
# Uso (a partir da raiz do repo ou desta pasta):
#   bash deploy/fly/apply-always-on-backends.sh
#
# O que faz:
#   1) Aplica a config dos fly.toml (deploy --ha=false)
#   2) Garante scale count >= 1 e máquinas started
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FLY="${FLY:-fly}"
if ! command -v "$FLY" >/dev/null 2>&1; then
  FLY=flyctl
fi
if ! command -v "$FLY" >/dev/null 2>&1; then
  echo "erro: fly/flyctl não encontrado. Instale: https://fly.io/docs/hands-on/install-flyctl/"
  exit 1
fi

deploy_app() {
  local dir="$1"
  local app="$2"
  echo ""
  echo "========== $app ($dir) =========="
  (
    cd "$ROOT/$dir"
    # --ha=false: lab com 1 machine; não cria segunda réplica
    "$FLY" deploy --ha=false --app "$app"
  )
  echo ">> scale count 1 em $app"
  "$FLY" scale count 1 --app "$app" --yes 2>/dev/null \
    || "$FLY" scale count app=1 --app "$app" --yes 2>/dev/null \
    || true
  # Acorda qualquer machine parada
  ids=$("$FLY" machine list -a "$app" --json 2>/dev/null \
        | grep -oE '"id": "[0-9a-f]{6,}"' | sed -E 's/.*"([0-9a-f]{6,})".*/\1/' || true)
  for id in $ids; do
    "$FLY" machine start "$id" -a "$app" >/dev/null 2>&1 || true
    echo "  machine $id started (ou já ligada)"
  done
  "$FLY" status -a "$app" || true
}

deploy_app "motor-simulacao" "motor2037"
deploy_app "estoque-api" "estoque2037"
deploy_app "chatbot-api" "chatbot2037"
deploy_app "portal-gestao" "portal2037"
deploy_app "catalogo-publico" "catalogo2037"
deploy_app "site" "site2037"

echo ""
echo "========== checagem rápida =========="
for app in motor2037 estoque2037 chatbot2037 portal2037 catalogo2037 site2037; do
  echo "--- $app ---"
  "$FLY" status -a "$app" 2>/dev/null | head -40 || true
done

echo ""
echo "Pronto. Todos os apps principais ficam always-on (auto_stop desligado)."
echo "Teste: https://portal2037.fly.dev  |  https://catalogo2037.fly.dev  |  https://site2037.fly.dev"
