#!/usr/bin/env bash
# Sobe a suíte no Fly no setup lab opção A:
#   - Postgres, backends (motor/estoque/chatbot), Evolution, n8n → always-on
#   - Portal sobe agora; Catálogo opcional (teto de RAM da org)
#   - Portal/Catálogo mantêm autostop=stop (podem dormir depois)
#   - Backends reaplicam autostop=off a cada up (idempotente)
#
# Uso:
#   bash deploy/fly/up-all.sh              # suite de teste (sem catálogo)
#   bash deploy/fly/up-all.sh --catalogo   # tenta Portal + Catálogo (pode falhar por RAM)
#   bash deploy/fly/up-all.sh --no-portal  # só infra + backends + WA (sem front)
#   bash deploy/fly/up-all.sh 45           # sobe e keepalive 45 min (re-start a cada 2 min)
#   bash deploy/fly/up-all.sh --catalogo 30
#
# Par: bash deploy/fly/down-all.sh
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
MINUTES=0

for arg in "$@"; do
  case "$arg" in
    --catalogo|--with-catalogo) WITH_CATALOGO=1 ;;
    --no-portal) WITH_PORTAL=0 ;;
    --no-catalogo) WITH_CATALOGO=0 ;;
    -h|--help)
      sed -n '2,22p' "$0" | sed 's/^# \?//'
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
declare -A FALLBACK_ID=(
  [suite-pg]=d8946d2f320de8
  [motor2037]=0807560c916d68
  [estoque2037]=287e35dbd147e8
  [chatbot2037]=d8d1375a42e578
  [portal2037]=6837936c0d73d8
  [catalogo2037]=0807560c916768
  [n8n2037]=0807564f9034e8
  [evolution2037]=7847926f5d1758
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

echo ">> up-all (opção A: backends always-on; front pode dormir)"
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

# 4) Front (Portal prioritário; Catálogo opcional por teto de RAM)
echo ""
echo "=== 4/4 Front ==="
if [ "$WITH_PORTAL" -eq 1 ]; then
  start_app portal2037 || true
  wait_started portal2037 20 || true
  # Portal deve poder dormir depois (não forçamos always-on)
  for id in $(machine_ids portal2037); do
    "$FLY" machine update "$id" -a portal2037 --autostop=stop --autostart=true --yes >/dev/null 2>&1 \
      && echo "  portal autostop=stop (front dorme quando ocioso)" \
      || echo "  warn portal: não reaplicou autostop=stop"
  done
else
  echo "  (portal pulado: --no-portal)"
fi

if [ "$WITH_CATALOGO" -eq 1 ]; then
  echo "  tentando catálogo (pode falhar por mem_overcommit com portal+backends on)..."
  if start_app catalogo2037; then
    wait_started catalogo2037 15 || true
    for id in $(machine_ids catalogo2037); do
      "$FLY" machine update "$id" -a catalogo2037 --autostop=stop --autostart=true --yes >/dev/null 2>&1 || true
    done
  else
    echo "  tip: se overcommit, use sem --catalogo ou: fly machine stop <portal> && up só catálogo"
  fi
else
  echo "  (catálogo não subiu de propósito — evita teto de RAM; use --catalogo se precisar)"
fi

echo ""
echo ">> resumo"
for app in suite-pg motor2037 estoque2037 chatbot2037 evolution2037 n8n2037 portal2037 catalogo2037; do
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

echo ""
echo "URLs: Portal https://portal2037.fly.dev  |  Catálogo https://catalogo2037.fly.dev"
echo "      n8n https://n8n2037.fly.dev  |  Evolution https://evolution2037.fly.dev/manager"
echo "Down quando acabar:  bash deploy/fly/down-all.sh --yes"

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
