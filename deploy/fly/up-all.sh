#!/usr/bin/env bash
# Sobe a suíte no Fly (always-on em tudo):
#
# Preferido (arquitetura 3-VM — deploy/fly/3vm/):
#   bash deploy/fly/up-all.sh --3vm
#     sobe: suite-pg, evolution2037, app2037
#     NÃO sobe: motor2037 (workers Playwright ficam stopped; sobem on-demand)
#
# Inventário operacional (apps monólito legados removidos a pedido do owner):
#   always-on: suite-pg, evolution2037, app2037
#   on-demand: motor2037 (workers Playwright; idle stopped)
#
# Uso:
#   bash deploy/fly/up-all.sh --3vm         # 3-VM always-on (recomendado / único path real)
#   bash deploy/fly/up-all.sh --3vm 45      # 3-VM + keepalive 45 min
#   bash deploy/fly/up-all.sh              # legado: apps monólito (provavelmente inexistentes)
#   bash deploy/fly/up-all.sh --catalogo   # legado
#   bash deploy/fly/up-all.sh --no-portal  # legado
#   bash deploy/fly/up-all.sh 45           # legado + keepalive
#
# Par: bash deploy/fly/down-all.sh --3vm
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

WITH_PORTAL=1
WITH_CATALOGO=0
MODE_3VM=0
MINUTES=0

for arg in "$@"; do
  case "$arg" in
    --3vm) MODE_3VM=1 ;;
    --catalogo|--with-catalogo) WITH_CATALOGO=1 ;;
    --no-portal) WITH_PORTAL=0 ;;
    --no-catalogo) WITH_CATALOGO=0 ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    '' ) ;;
    *)
      if [[ "$arg" =~ ^[0-9]+$ ]]; then
        MINUTES="$arg"
      else
        echo "arg desconhecido: $arg (use --help)"
        exit 1
      fi
      ;;
  esac
done

# IDs conhecidos do lab (fallback se list falhar). Atualize se recrear machines.
# Apenas apps que permanecem no inventário 3-VM (+ worker on-demand).
# Legados (portal/catalogo/estoque/chatbot/n8n/site monólito) foram removidos —
# não listar IDs mortos aqui (evita start em machines inexistentes).
# app2037: sem fallback estático — use `fly machine list -a app2037`.
# Chaves com aspas: com set -u, [suite-pg] é parseado como aritmética (suite - pg).
declare -A FALLBACK_ID=(
  ["suite-pg"]=d8946d2f320de8
  ["evolution2037"]=7847926f5d1758
  ["motor2037"]=0807560c916d68
)

machine_ids() {
  local app="$1"
  local ids
  ids=$("$FLY" machine list -a "$app" --json 2>/dev/null \
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
' 2>/dev/null || true)
  if [ -z "$ids" ] && [ -n "${FALLBACK_ID[$app]:-}" ]; then
    ids="${FALLBACK_ID[$app]}"
  fi
  echo "$ids"
}

start_app() {
  local app="$1"
  local ids
  ids=$(machine_ids "$app")
  if [ -z "$ids" ]; then
    echo "  -- $app: nenhuma machine"
    return 1
  fi
  local ok=0
  for id in $ids; do
    if "$FLY" machine start "$id" -a "$app" >/dev/null 2>&1; then
      echo "  up    $app/$id"
      ok=1
    else
      # já started ou capacity
      state=$("$FLY" machine status "$id" -a "$app" 2>/dev/null | awk '/^State:/{print $2; exit}')
      if [ "$state" = "started" ]; then
        echo "  already $app/$id"
        ok=1
      else
        echo "  FAIL  $app/$id (state=${state:-?}) — capacity/overcommit?"
      fi
    fi
  done
  return $((1 - ok))
}

# Reaplica opção A nos backends (idempotente; não muda RAM).
ensure_backend_always_on() {
  local app="$1"
  local id
  for id in $(machine_ids "$app"); do
    if "$FLY" machine update "$id" -a "$app" --autostop=off --autostart=true --yes >/dev/null 2>&1; then
      echo "  always-on $app/$id (autostop=off)"
    else
      echo "  warn  $app/$id: não deu para reaplicar autostop=off (machine started? capacity?)"
    fi
  done
}

wait_started() {
  local app="$1"
  local tries="${2:-20}"
  local i state
  for i in $(seq 1 "$tries"); do
    state=$("$FLY" machine list -a "$app" --json 2>/dev/null \
      | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print("?"); sys.exit(0)
if not data:
    print("none"); sys.exit(0)
# qualquer started conta
for m in data:
    if m.get("state") == "started":
        print("started"); sys.exit(0)
print(data[0].get("state") or "?")
' 2>/dev/null || echo "?")
    if [ "$state" = "started" ]; then
      echo "  ok   $app started"
      return 0
    fi
    sleep 3
  done
  echo "  warn $app ainda não started (state=$state)"
  return 1
}

print_machine_summary() {
  local app
  for app in "$@"; do
    info=$("$FLY" machine list -a "$app" --json 2>/dev/null \
      | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print("?"); sys.exit(0)
if not data:
    print("none"); sys.exit(0)
parts=[]
for m in data:
    st=m.get("state") or "?"
    mem=(m.get("config") or {}).get("guest",{}).get("memory_mb")
    auto="?"
    svcs=(m.get("config") or {}).get("services") or []
    if svcs:
        a=svcs[0].get("autostop")
        auto = "off" if a is False else ("on" if a is True else str(a))
    parts.append(f"{st} mem={mem} autostop={auto}")
print(" | ".join(parts))
' 2>/dev/null || echo "?")
    printf '  %-16s %s\n' "$app" "$info"
  done
}

if [ "$MODE_3VM" -eq 1 ]; then
  # ---------------------------------------------------------------------------
  # Arquitetura 3-VM (deploy/fly/3vm/): suite-pg + evolution2037 + app2037
  # motor2037 (Playwright) fica stopped — sobe on-demand por job.
  # ---------------------------------------------------------------------------
  echo ">> up-all --3vm (always-on: suite-pg, evolution2037, app2037)"
  echo "   motor2037 workers: NÃO iniciados (on-demand / idle stopped)"
  echo "   keepalive_min=$MINUTES"
  echo ""

  echo "=== 1/3 Postgres ==="
  start_app suite-pg || true
  wait_started suite-pg 15 || true
  sleep 3

  echo ""
  echo "=== 2/3 Evolution (canal WhatsApp) ==="
  start_app evolution2037 || true
  wait_started evolution2037 20 || true
  ensure_backend_always_on evolution2037

  echo ""
  echo "=== 3/3 app2037 (n8n + chatbot + estoque + portal + catálogo + site + motor-api) ==="
  start_app app2037 || true
  wait_started app2037 30 || true
  ensure_backend_always_on app2037

  echo ""
  echo "  (motor2037: workers deixados stopped — Playwright sobe só sob demanda)"

  echo ""
  echo ">> resumo"
  print_machine_summary suite-pg evolution2037 app2037 motor2037

  echo ""
  echo "URLs: App https://app2037.fly.dev  |  Evolution https://evolution2037.fly.dev/manager"
  echo "      Site https://site2037.fly.dev/health (se host apontar para app2037)"
  echo "Down quando acabar:  bash deploy/fly/down-all.sh --3vm --yes"

  if [ "$MINUTES" -gt 0 ] 2>/dev/null; then
    end=$(( $(date +%s) + MINUTES * 60 ))
    echo ""
    echo ">> keepalive ${MINUTES} min (re-start a cada 2 min; Ctrl+C para parar)"
    while [ "$(date +%s)" -lt "$end" ]; do
      sleep 120
      echo ">> keepalive $(date +%H:%M:%S)"
      start_app suite-pg || true
      start_app evolution2037 || true
      start_app app2037 || true
    done
    echo ">> keepalive esgotado (always-on com autostop=off devem continuar)."
  fi

  echo ">> pronto."
  exit 0
fi

# ---------------------------------------------------------------------------
# Legado: apps monólito por serviço (sem --3vm)
# Apps legados foram removidos do Fly — este path só permanece por compat de CLI.
# Prefira sempre: bash deploy/fly/up-all.sh --3vm
# ---------------------------------------------------------------------------
echo ">> up-all legado (apps monólito — provavelmente destruídos; use --3vm)"
echo "   tip: bash deploy/fly/up-all.sh --3vm  (suite-pg + evolution2037 + app2037)"
echo "   portal=$WITH_PORTAL  catalogo=$WITH_CATALOGO  keepalive_min=$MINUTES"
echo ""

# 1) Postgres primeiro
echo "=== 1/4 Postgres ==="
start_app suite-pg || true
wait_started suite-pg 15 || true
sleep 3

# 2) Backends (always-on)
echo ""
echo "=== 2/4 Backends (motor, estoque, chatbot) ==="
for app in motor2037 estoque2037 chatbot2037; do
  start_app "$app" || true
done
for app in motor2037 estoque2037 chatbot2037; do
  wait_started "$app" 20 || true
done
echo "  reaplicando autostop=off nos backends..."
for app in motor2037 estoque2037 chatbot2037; do
  ensure_backend_always_on "$app"
done

# 3) Canal WhatsApp
echo ""
echo "=== 3/4 Evolution + n8n ==="
start_app evolution2037 || true
start_app n8n2037 || true
wait_started evolution2037 20 || true
wait_started n8n2037 25 || true
ensure_backend_always_on evolution2037
ensure_backend_always_on n8n2037

# 4) Front (Portal/Catálogo/Site always-on)
echo ""
echo "=== 4/4 Front ==="
if [ "$WITH_PORTAL" -eq 1 ]; then
  start_app portal2037 || true
  wait_started portal2037 20 || true
  ensure_backend_always_on portal2037
else
  echo "  (portal pulado: --no-portal)"
fi

if [ "$WITH_CATALOGO" -eq 1 ]; then
  echo "  tentando catálogo..."
  if start_app catalogo2037; then
    wait_started catalogo2037 15 || true
    ensure_backend_always_on catalogo2037
  else
    echo "  tip: se overcommit, use sem --catalogo ou: fly machine stop <portal> && up só catálogo"
  fi
else
  echo "  (catálogo não subiu de propósito — evita teto de RAM; use --catalogo se precisar)"
fi

# Site marketing always-on
start_app site2037 || true
wait_started site2037 15 || true
ensure_backend_always_on site2037

echo ""
echo ">> resumo"
print_machine_summary suite-pg motor2037 estoque2037 chatbot2037 evolution2037 n8n2037 portal2037 catalogo2037

echo ""
echo "URLs: Portal https://portal2037.fly.dev  |  Catálogo https://catalogo2037.fly.dev"
echo "      n8n https://n8n2037.fly.dev  |  Evolution https://evolution2037.fly.dev/manager"
echo "Down quando acabar:  bash deploy/fly/down-all.sh --yes"
echo "(3-VM: bash deploy/fly/up-all.sh --3vm  /  bash deploy/fly/down-all.sh --3vm)"

if [ "$MINUTES" -gt 0 ] 2>/dev/null; then
  end=$(( $(date +%s) + MINUTES * 60 ))
  echo ""
  echo ">> keepalive ${MINUTES} min (re-start a cada 2 min; Ctrl+C para parar)"
  while [ "$(date +%s)" -lt "$end" ]; do
    sleep 120
    echo ">> keepalive $(date +%H:%M:%S)"
    start_app suite-pg || true
    for app in motor2037 estoque2037 chatbot2037 evolution2037 n8n2037; do
      start_app "$app" || true
    done
    [ "$WITH_PORTAL" -eq 1 ] && start_app portal2037 || true
    [ "$WITH_CATALOGO" -eq 1 ] && start_app catalogo2037 || true
  done
  echo ">> keepalive esgotado (backends com autostop=off devem continuar; front pode dormir)."
fi

echo ">> pronto."
