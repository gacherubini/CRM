#!/usr/bin/env bash
# Para TODA a suíte no Fly (lab) — zera compute, NÃO apaga apps/volumes/dados.
#
# Uso (na raiz do repo ou nesta pasta):
#   bash deploy/fly/down-all.sh
#   bash deploy/fly/down-all.sh --yes          # sem confirmação
#
# O que faz:
#   fly machine stop em cada app da suíte
#
# O que NÃO faz:
#   destroy app, volume, secrets, IP — setup always-on dos backends PERMANECE
#   na config da machine (volta no próximo up-all.sh)
#
# Depois de desligar, para testar de novo:
#   bash deploy/fly/up-all.sh
set -euo pipefail

export PATH="${HOME}/.fly/bin:${PATH}"
FLY="${FLY:-}"
if [ -z "$FLY" ]; then
  if command -v fly >/dev/null 2>&1; then FLY=fly
  elif command -v flyctl >/dev/null 2>&1; then FLY=flyctl
  else
    echo "erro: fly/flyctl não encontrado (instale e faça fly auth login)"
    exit 1
  fi
fi

# Ordem irrelevante no stop; listamos explícito para o status final.
APPS=(
  portal2037
  catalogo2037
  motor2037
  estoque2037
  chatbot2037
  n8n2037
  evolution2037
  suite-pg
)

ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

if [ "$ASSUME_YES" -ne 1 ]; then
  echo "Vai PARAR as machines destes apps (sem apagar volume/app):"
  printf '  - %s\n' "${APPS[@]}"
  echo ""
  read -r -p "Confirma down da suíte? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "cancelado."; exit 0 ;;
  esac
fi

machine_ids() {
  local app="$1"
  "$FLY" machine list -a "$app" --json 2>/dev/null \
    | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(data, list):
    data = [data] if data else []
for m in data:
    mid = m.get("id")
    if mid:
        print(mid)
' 2>/dev/null || true
}

echo ">> down-all (stop machines) ..."
for app in "${APPS[@]}"; do
  ids=$(machine_ids "$app")
  if [ -z "$ids" ]; then
    echo "  -- $app: nenhuma machine"
    continue
  fi
  for id in $ids; do
    if "$FLY" machine stop "$id" -a "$app" >/dev/null 2>&1; then
      echo "  stop  $app/$id"
    else
      # já parada ou erro transitório
      echo "  skip  $app/$id (já parada ou falhou)"
    fi
  done
done

echo ""
echo ">> status (esperado: stopped)"
for app in "${APPS[@]}"; do
  state=$("$FLY" machine list -a "$app" --json 2>/dev/null \
    | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print("?"); sys.exit(0)
if not data:
    print("none"); sys.exit(0)
states = sorted({m.get("state") or "?" for m in data})
print(",".join(states))
' 2>/dev/null || echo "?")
  printf '  %-16s %s\n' "$app" "$state"
done

echo ""
echo "Pronto. Compute parado; volumes/apps intactos."
echo "Config always-on dos backends (autostop=off) permanece na machine."
echo "Para voltar:  bash deploy/fly/up-all.sh"
echo "Obs: volumes ainda podem gerar custo residual pequeno no Fly."
