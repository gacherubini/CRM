---
gatilho: procurar o banco de um produto, escolher dialeto de migration ou cruzar dados entre produtos
produto: todos
custo: migration escrita para o dialeto errado, que estoura no deploy
---
# A engine de cada produto se confere no `db.py`, nao na memoria

**Conferido em 23/08/2026 contra o repo.** Este arquivo ja esteve errado: ate
23/08 ele afirmava "Portal e Control rodam SQLite no volume do app2037".

- **Portal: Postgres, schema `portal`** — `portal-gestao/app/db.py:1` e `:8`.
- **Control: Postgres, schema `control`** — `revy-trafego/app/db.py:1` e `:8`.
- **SQLite sobrou so em teste e dev.**
- `suite-pg` tem `chatbot`, `estoque`, `motor` e `evolution`.
- `PORTAL_DATABASE_URL` e `REVY_TRAFEGO_DATABASE_URL` sairam do `[env]` no corte
  de 16/08 porque a URL tem senha e o toml esta no git
  (`deploy/fly/3vm/fly.app.toml:16-18` e `:34`). Vem **so de secret**, com
  fail-fast: `${VAR:?}` em `run-portal.sh:3` e `run-revy-trafego.sh:4`.
  Nao achar a URL no toml **nao** significa que o produto usa o default.

## A armadilha que a versao errada armava

`batch_alter_table(recreate="always")` e o caminho do SQLite, que nao sabe fazer
ALTER de constraint. **No Postgres a copia estoura** quando ha FK dependendo do
indice da PK (`DependentObjectsStillExist`). O caso real esta documentado em
`revy-trafego/alembic/versions/0019_financeiro_modulo.py:35-42`.

Num ensaio de 23/08 um agente leu a versao errada deste arquivo e ia escrever a
migration com `batch_alter_table` "porque e SQLite". O que o salvou foi abrir o
`db.py` — uma linha — em vez de acreditar no learning.

## Por que este arquivo apodreceu

Ele foi levantado da infra em 16/08 e a migracao aconteceu **no mesmo dia**; o
texto ate linkava o plano dela como futuro. A data do arquivo (23/08) fazia
parecer recente um retrato de antes do corte.

**Como aplicar:** learning que descreve *infra* envelhece sem aviso, diferente de
learning que descreve *codigo*. Antes de afirmar engine, banco ou secret, abra o
`db.py` do produto e o `run-*.sh` do deploy. Sao duas linhas, e este arquivo ja
custou o preco de nao terem sido lidas.

Ver [[2026-08-23-flags-de-rollout-sao-secrets]] e
[[2026-08-23-alembic-mente-sem-database-url]].
