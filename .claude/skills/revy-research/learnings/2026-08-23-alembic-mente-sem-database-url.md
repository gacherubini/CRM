---
gatilho: rodar alembic ou conferir migration de producao
produto: chatbot-api
custo: 1h30
---
# `alembic current` responde SQLite e mente

Sem `CHATBOT_DATABASE_URL` no ambiente, o `alembic current` do chatbot responde a
partir do SQLite local (`chatbot-api/app/db.py` le `DATABASE_URL` com fallback
`sqlite:///./chatbot.db`) e devolve uma revisao errada com cara de sucesso. Voce
conclui que producao esta na head e nao esta. O mapeamento so acontece dentro do
entrypoint, nao no shell do `fly ssh`. As migrations sao fail-fast no boot do bundle
(`deploy/fly/3vm/entrypoint-app.sh`), entao o erro so aparece no deploy — e derruba
os cinco servicos juntos.

So aceite a resposta se ela disser `Context impl PostgresqlImpl`. `SQLiteImpl` e lixo,
nao registre como fato. Portal e Control respondem certo direto (eles sao SQLite mesmo).

    fly ssh console -a app2037 -C "/bin/sh -c 'cd /srv/chatbot && DATABASE_URL=\$CHATBOT_DATABASE_URL alembic current 2>&1'"

Aspas duplas por fora, simples por dentro. Um `-c` mal fechado pega so o `export` e o
comando **despeja o ambiente inteiro, com secrets, no log**.
