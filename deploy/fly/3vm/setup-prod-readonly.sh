#!/usr/bin/env bash
# Recria o acesso read-only de produção (skill prod-readonly-db) no macOS/Linux.
#
# Fonte de verdade é o Fly (org crm-419): a senha das roles *_reader vem do
# secret PROD_READONLY_DB_PASSWORD no app2037. Nada de segredo toca o git.
#
# O banco (suite-pg) é privado: abra o túnel com `-t` (ou em outro terminal,
# `fly proxy 15432:5432 -a suite-pg`) antes de consultar.
set -euo pipefail

FLY_APP="app2037"
PG_APP="suite-pg"
LOCAL_PORT="15432"
REMOTE_PORT="5432"
START_TUNNEL=0
[[ "${1:-}" == "-t" || "${1:-}" == "--tunnel" ]] && START_TUNNEL=1

ALIASES=(
  "revy-chatbot chatbot chatbot_reader public"
  "revy-estoque estoque estoque_reader public"
  "revy-motor motor motor_reader public"
  "revy-revy revy revy_reader portal,control,public"
  "revy-evolution evolution evolution_reader public"
)

echo "conferindo login do Fly..."
fly auth whoami >/dev/null || { echo "Fly não autenticado. Rode: fly auth login"; exit 1; }

echo "lendo senha do reader de ${FLY_APP}..."
PW="$(fly ssh console -a "$FLY_APP" -C "sh -lc 'printenv PROD_READONLY_DB_PASSWORD'" 2>/dev/null \
  | grep -v 'Connecting to' | tail -n1 | tr -d '\r' | xargs)"
[[ -n "$PW" ]] || { echo "não achei PROD_READONLY_DB_PASSWORD nos secrets de ${FLY_APP}"; exit 1; }

SVC_FILE="$HOME/.pg_service.conf"
PASS_FILE="$HOME/.pgpass"
: > "$SVC_FILE"
: > "$PASS_FILE"
for row in "${ALIASES[@]}"; do
  read -r alias db role schemas <<<"$row"
  {
    echo "[$alias]"
    echo "host=127.0.0.1"
    echo "port=$LOCAL_PORT"
    echo "dbname=$db"
    echo "user=$role"
    echo "sslmode=disable"
    echo
  } >> "$SVC_FILE"
  echo "127.0.0.1:${LOCAL_PORT}:${db}:${role}:${PW}" >> "$PASS_FILE"
done
chmod 600 "$SVC_FILE" "$PASS_FILE"
echo "escrito: $SVC_FILE"
echo "escrito: $PASS_FILE"

# Bloco de variáveis não-secretas, com marcador para não duplicar.
MARK_BEGIN="# >>> revy prod-readonly-db >>>"
MARK_END="# <<< revy prod-readonly-db <<<"
BLOCK="$MARK_BEGIN
export PGSERVICEFILE=\"$SVC_FILE\""
for row in "${ALIASES[@]}"; do
  read -r alias db role schemas <<<"$row"
  key="$(echo "$alias" | tr '[:lower:]-' '[:upper:]_')"
  BLOCK="$BLOCK
export PROD_READONLY_DB_${key}_SERVICE=$alias
export PROD_READONLY_DB_${key}_EXPECTED_DATABASE=$db
export PROD_READONLY_DB_${key}_EXPECTED_ROLE=$role
export PROD_READONLY_DB_${key}_ALLOWED_SCHEMAS=\"$schemas\"
export PROD_READONLY_DB_${key}_TRANSPORT=tunnel"
done
BLOCK="$BLOCK
$MARK_END"

for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  [[ -f "$rc" ]] || touch "$rc"
  if grep -qF "$MARK_BEGIN" "$rc"; then
    tmp="$(mktemp)"
    awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
      $0==b {skip=1} !skip {print} $0==e {skip=0}' "$rc" > "$tmp" && mv "$tmp" "$rc"
  fi
  printf '%s\n' "$BLOCK" >> "$rc"
done
echo "aliases exportados em ~/.zshrc e ~/.bashrc"

if [[ "$START_TUNNEL" == "1" ]]; then
  echo "abrindo túnel local ${LOCAL_PORT} -> ${PG_APP}:${REMOTE_PORT}..."
  nohup fly proxy "${LOCAL_PORT}:${REMOTE_PORT}" -a "$PG_APP" >/tmp/revy-pg-proxy.log 2>&1 &
  sleep 6
  echo "túnel ativo em 127.0.0.1:${LOCAL_PORT} (kill $(pgrep -f "fly proxy" | head -n1) encerra)"
else
  echo "abra o túnel em outro terminal: fly proxy ${LOCAL_PORT}:${REMOTE_PORT} -a ${PG_APP}"
fi

echo
echo "teste:"
echo "  echo 'SELECT current_database(), current_user' | python3 skills/prod-readonly-db/scripts/readonly_psql.py --alias revy-motor"
