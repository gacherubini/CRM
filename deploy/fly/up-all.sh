#!/usr/bin/env bash
# Sobe (start) todas as maquinas de todos os apps de uma vez.
# Uso:
#   bash up-all.sh          -> so acorda tudo agora
#   bash up-all.sh 60       -> acorda e mantem ligado por 60 min (re-start a cada 2 min)
set -uo pipefail

APPS="suite-pg portal2037 catalogo2037 motor2037 estoque2037 chatbot2037 n8n2037 evolution2037"
MINUTES="${1:-0}"

start_all() {
  for app in $APPS; do
    ids=$(flyctl machine list -a "$app" --json 2>/dev/null \
          | grep -oE '"id": "[0-9a-f]{6,}"' | sed -E 's/.*"([0-9a-f]{6,})".*/\1/')
    if [ -z "$ids" ]; then
      echo "  -- $app: nenhuma maquina"
      continue
    fi
    for id in $ids; do
      if flyctl machine start "$id" -a "$app" >/dev/null 2>&1; then
        echo "  up  $app/$id"
      else
        echo "  ?? $app/$id (ja ligada ou erro)"
      fi
    done
  done
}

echo ">> subindo tudo..."
start_all

if [ "$MINUTES" -gt 0 ] 2>/dev/null; then
  end=$(( $(date +%s) + MINUTES * 60 ))
  echo ">> mantendo ligado por $MINUTES min (Ctrl+C para parar)"
  while [ "$(date +%s)" -lt "$end" ]; do
    sleep 120
    echo ">> keepalive $(date +%H:%M:%S)"
    start_all
  done
  echo ">> tempo esgotado; as maquinas voltam a dormir sozinhas."
fi
echo ">> pronto."
