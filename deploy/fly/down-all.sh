#!/usr/bin/env bash
# Para machines no Fly (lab) — zera compute, NÃO apaga apps/volumes/dados.
#
# Preferido (arquitetura 3-VM — deploy/fly/3vm/):
#   bash deploy/fly/down-all.sh --3vm
#   bash deploy/fly/down-all.sh --3vm --yes
#     para: suite-pg, evolution2037, app2037, n8n2037
#     + motor2037 se estiver up (workers on-demand; idle deve estar stopped)
#   NÃO toca apps legados (removidos a pedido do owner).
#
# Legado (default sem --3vm): tenta monólitos por serviço (provavelmente inexistentes).
#
# Uso (na raiz do repo ou nesta pasta):
#   bash deploy/fly/down-all.sh --3vm
#   bash deploy/fly/down-all.sh --3vm --yes
#   bash deploy/fly/down-all.sh
#   bash deploy/fly/down-all.sh --yes          # sem confirmação
#
# O que faz:
#   fly machine stop em cada app da lista
#
# O que NÃO faz:
#   destroy app, volume, secrets, IP — setup always-on dos backends PERMANECE
#   na config da machine (volta no próximo up-all.sh)
#
# Depois de desligar, para testar de novo:
#   bash deploy/fly/up-all.sh --3vm
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

MODE_3VM=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --3vm) MODE_3VM=1 ;;
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      sed -n '2,28p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "arg desconhecido: $arg (use --help)"
      exit 1
      ;;
  esac
done

if [ "$MODE_3VM" -eq 1 ]; then
  # Always-on 3-VM + motor worker (se estiver ligado). Sem apps legados.
  # motor2037: só para garantir stop se algum job deixou worker started.
  APPS=(
    app2037
    n8n2037
    evolution2037
    suite-pg
    motor2037
  )
else
  # Legado: monólito por serviço (apps podem já ter sido destruídos no Fly)
  APPS=(
    portal2037
    catalogo2037
    motor2037
    estoque2037
    chatbot2037
    n8n2037
    evolution2037
    suite-pg
    app2037
  )
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  if [ "$MODE_3VM" -eq 1 ]; then
    echo "Vai PARAR as machines 3-VM (sem apagar volume/app):"
  else
    echo "Vai PARAR as machines destes apps (sem apagar volume/app):"
  fi
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

if [ "$MODE_3VM" -eq 1 ]; then
  echo ">> down-all --3vm (stop machines always-on + motor se up) ..."
else
  echo ">> down-all (stop machines legado) ..."
fi
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
if [ "$MODE_3VM" -eq 1 ]; then
  echo "Para voltar:  bash deploy/fly/up-all.sh --3vm"
else
  echo "Para voltar (3-VM): bash deploy/fly/up-all.sh --3vm"
  echo "Para voltar (legado): bash deploy/fly/up-all.sh"
fi
echo "Obs: volumes ainda podem gerar custo residual pequeno no Fly."
