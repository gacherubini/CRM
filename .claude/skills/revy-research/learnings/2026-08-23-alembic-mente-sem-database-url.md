---
gatilho: rodar alembic, conferir migration de producao, ou rodar script do chatbot contra o banco de producao
produto: chatbot-api
custo: 1h30
fonte: infra
verificado_em: 2026-08-24 (parte do SQLite local reconferida contra o repo)
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
nao registre como fato. (Uma versao anterior deste arquivo dizia que Portal e Control
"sao SQLite mesmo" e por isso respondem certo: **falso desde o corte de 16/08** — ver
[[2026-08-23-engine-do-produto-se-confere-no-db-py]].)

## E `alembic upgrade head` local nao roda, ponto

Conferido em 24/08 contra um banco limpo: a cadeia do chatbot **para na 0017**
(`0017_canal_id_conversas_msg.py:25`, `add_column` NOT NULL) com
`NotImplementedError: No support for ALTER of constraints in SQLite dialect`. Nao e
o seu banco de dev fora de sincronia — e a cadeia inteira, do zero.

Consequencia pratica: o passo "Migration: `alembic upgrade head` no produto certo"
do `AGENTS.md` §6 **nao e executavel** para o chatbot sem uma URL de Postgres. O
substituto honesto, que nao conecta em lugar nenhum e mostra o SQL do dialeto de
producao:

    DATABASE_URL="postgresql+psycopg://u:p@localhost/x"       .venv/Scripts/python.exe -m alembic upgrade <anterior>:<nova> --sql

Isso tambem desarma a escolha batch × alter_column: `batch_alter_table` so existe
para o SQLite que esta cadeia ja nao atende, e no PG ele e o que estoura quando ha
FK dependendo do indice da PK.

    fly ssh console -a app2037 -C "/bin/sh -c 'cd /srv/chatbot && DATABASE_URL=\$CHATBOT_DATABASE_URL alembic current 2>&1'"

Aspas duplas por fora, simples por dentro. Um `-c` mal fechado pega so o `export` e o
comando **despeja o ambiente inteiro, com secrets, no log**.
