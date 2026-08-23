---
gatilho: portal e motor caindo juntos com conexao recusada no banco
produto: deploy
---
# "server closed the connection unexpectedly" nos dois = OOM do `suite-pg`

O `suite-pg` (flyio/postgres-flex, regiao gru, sempre-ligado) serve o suite inteiro.
Em 20/07/2026 ele morreu por **OOM rodando com 256 MB**: porta 5433 recusando conexao,
3/3 health checks criticos, e portal + motor caindo junto com "server closed the
connection unexpectedly". Recuperado com `fly machine restart`.

256 MB e apertado demais para postgres-flex (postgres + repmgr + exporter) somado a
blobs de screenshot no banco. Subimos para **512 MB** e e onde esta hoje. Se voltar a
dar OOM sob carga normal, o proximo degrau e 1 GB — decisao de custo, pergunte ao dono.

Antes de culpar o codigo do portal ou do motor, confira a maquina do banco.
