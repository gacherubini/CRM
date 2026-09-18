#!/bin/bash
# Provisiona UMA credencial de loja para o loop e salva o token em .token (600).
# Uso: ./provisionar.sh   (precisa `fly auth login` da conta Revy; roda uma vez)
set -u
E2E_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./config.sh disable=SC1091
CHIP_FAKE=1 CHIP="+55000000000000" . "$E2E_DIR/config.sh" 2>/dev/null || true
E2E_DIR="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="$E2E_DIR/.token"

fly auth whoami >/dev/null 2>&1 || { echo "ERRO: fly sem login. Rode: fly auth login (conta Revy)"; exit 2; }
fly status -a app2037 >/dev/null 2>&1 || { echo "ERRO: conta fly atual nao enxerga o app2037"; exit 2; }

OUT="$(fly ssh console -a app2037 <<'EOF'
cd /srv/chatbot
DATABASE_URL="$CHATBOT_DATABASE_URL" python -m app.cli criar-credencial-loja --slug teste 2>/dev/null | grep -o 'TOKEN.*' || true
exit
EOF
)"
TOKEN="$(printf '%s' "$OUT" | tr -d '\r' | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | grep -o 'TOKEN.*' | awk '{print $NF}' | grep -oE '^[A-Za-z0-9_-]{32}$' | tail -n 1)"
[ -n "$TOKEN" ] || { echo "ERRO: nao achei o token na saida:"; printf '%s\n' "$OUT"; exit 1; }
printf '%s' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo "token salvo em $TOKEN_FILE (mostrado uma vez pela API, agora so aqui)"
