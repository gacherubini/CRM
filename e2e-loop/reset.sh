#!/bin/bash
# Reset da loja teste via console do app2037 (precisa `fly auth login` da conta Revy).
# Uso: ./reset.sh [--print-only]
set -u
E2E_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--print-only" ]; then
  cat "$E2E_DIR/reset.sql"
  exit 0
fi

fly auth whoami >/dev/null 2>&1 || { echo "ERRO: fly sem login. Rode: fly auth login (conta Revy)"; exit 2; }
fly status -a app2037 >/dev/null 2>&1 || { echo "ERRO: conta fly atual nao enxerga o app2037. Troque com: fly auth login"; exit 2; }

# Comando complexo vai via stdin (aprendizado fly-ssh-console-comando-complexo-via-stdin).
SQL_B64="$(base64 < "$E2E_DIR/reset.sql")"
fly ssh console -a app2037 <<EOF
cd /srv/chatbot
echo "$SQL_B64" | base64 -d > /tmp/reset_e2e.sql
DATABASE_URL="\$CHATBOT_DATABASE_URL" python -c "
import os, psycopg
url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
sql = open('/tmp/reset_e2e.sql').read()
with psycopg.connect(url, connect_timeout=15) as c:
    with c.cursor() as cur:
        cur.execute(sql)
    c.commit()
print('reset aplicado')
"
rm -f /tmp/reset_e2e.sql
exit
EOF
