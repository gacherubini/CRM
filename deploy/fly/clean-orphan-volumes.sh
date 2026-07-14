#!/usr/bin/env bash
# Apaga volumes ORFAOS (sem maquina anexada) de todos os apps.
# Seguro: so remove volumes com attached_machine_id == null; nunca o que esta em uso.
# Uso:
#   bash clean-orphan-volumes.sh          -> mostra o que apagaria (dry-run)
#   bash clean-orphan-volumes.sh --apply  -> apaga de verdade
set -uo pipefail

APPS="portal2037 catalogo2037 motor2037 estoque2037 chatbot2037 n8n2037 evolution2037"
APPLY="${1:-}"

total=0
for app in $APPS; do
  # Extrai IDs de volume cujo attached_machine_id e' null (orfaos).
  orphans=$(flyctl volumes list -a "$app" --all --json 2>/dev/null | awk '
    /"id": "vol_/      { gsub(/[",]/,""); split($0,a,": "); id=a[2] }
    /"attached_machine_id":/ { if ($0 ~ /null/) print id }
  ')
  for vol in $orphans; do
    total=$((total+1))
    if [ "$APPLY" = "--apply" ]; then
      echo "apagando $vol ($app)"
      flyctl volumes destroy "$vol" -a "$app" -y >/dev/null 2>&1 \
        && echo "  ok" || echo "  falhou"
    else
      echo "[dry-run] apagaria $vol ($app)"
    fi
  done
done

echo "----"
if [ "$APPLY" = "--apply" ]; then
  echo "Concluido. $total volume(s) orfao(s) processado(s)."
else
  echo "$total volume(s) orfao(s) encontrados. Rode com --apply para apagar."
fi
