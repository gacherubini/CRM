---
gatilho: mergear branch longa que tem migration
produto: todos
fonte: repo
verificado_em: 2026-08-24
---
# Zero conflito textual nao significa que o merge esta bom

Analisando o merge de uma branch de 69 commits em 16/08/2026, o conflito textual do git
era **zero** — e o merge estava quebrado. Portal e Control tinham ganhado migrations
irmas: duas migrations diferentes com o mesmo `down_revision` em cada produto. O git nao
ve conflito nenhum (arquivos novos, nomes diferentes), e o `alembic upgrade head` morre
com **"Multiple head revisions are present"**. Seis testes de migration quebravam so no
merge: passavam na main pura e na branch pura.

Antes de declarar um merge assim seguro, rode `alembic heads` em **cada produto** e confira
que ha uma cabeca so. A correcao e religar a cadeia: renumerar a migration da branch e
apontar o `down_revision` dela para a ultima migration da main — se as tabelas nao se
sobrepoem e nenhum codigo referencia os IDs, e so isso.

Falso positivo conhecido para nao perseguir: o `chatbot-api` falha `upgrade head` em SQLite
na `0017_canal_id_conversas_msg`. E identico na main pura e o chatbot roda Postgres.
