#!/bin/bash
# SELECT rapido no banco do chatbot via console do app2037 (oraculo dos asserts).
# Uso: ./dbq.sh "SELECT ..."  (so SELECT; imprime JSON)
set -u
E2E_DIR="$(cd "$(dirname "$0")" && pwd)"
SQL="${1:?passe o SELECT}"
case "$SQL" in
  [Ss][Ee][Ll][Ee][Cc][Tt]* ) ;;
  * ) echo "ERRO: so SELECT"; exit 2;;
esac
fly auth whoami >/dev/null 2>&1 || { echo "ERRO: fly sem login (conta Revy)"; exit 2; }
SQL_B64="$(printf '%s' "$SQL" | base64)"
fly ssh console -a app2037 2>/dev/null <<EOF | tr -d '\r' | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | grep -oE '^\[.*\]$' | tail -n 1
cd /srv/chatbot
echo "$SQL_B64" | base64 -d > /tmp/q.sql
DATABASE_URL="\$CHATBOT_DATABASE_URL" python -c "
import os, json, psycopg
url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
sql = open('/tmp/q.sql').read()
with psycopg.connect(url, connect_timeout=15, options='-c default_transaction_read_only=on') as c:
    with c.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description or []]
        print(json.dumps([dict(zip(cols, r)) for r in cur.fetchall()[:20]], default=str))
"
rm -f /tmp/q.sql
exit
EOF
