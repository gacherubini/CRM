---
gatilho: configurar acesso read-only ao banco de producao numa maquina nova, ou psql responde "definition of service not found"
produto: deploy
fonte: infra
verificado_em: 2026-09-15
---
# Acesso read-only a producao: Fly e a fonte de verdade, e o Windows pede `.pg_service.conf`

O `suite-pg` (flycast, privado) nao tem chave para perder: qualquer maquina com
`fly auth login` alcanca tudo. O bootstrap `deploy/fly/3vm/setup-prod-readonly.ps1`
(Windows) / `.sh` (macOS/Linux) le a senha das roles reader do secret
`PROD_READONLY_DB_PASSWORD` no `app2037`, grava `pg_service.conf`/`pgpass.conf` e
exporta os `PROD_READONLY_DB_*`. Nao ha segredo no git.

Armadilhas desta tarefa:

- **Windows:** a libpq procura o service file em
  `%APPDATA%\postgresql\.pg_service.conf` — **com ponto**. Sem o ponto, o psql diz
  `definition of service "x" not found` mesmo com o arquivo ali. O `pgpass.conf` e
  **sem** ponto. A referencia da skill `prod-readonly-db` escreve os dois sem ponto.
- **Preflight da skill recusa qualquer coisa maior que SELECT.** Foi preciso
  `REVOKE CONNECT, TEMPORARY ON DATABASE ... FROM PUBLIC` em todos os bancos (senao
  acusa `unexpected-connect`/`forbidden-privileges`), e `allowed_schemas` tem que
  incluir `public` (o PUBLIC tem USAGE no schema public).
- **Superusuario so para provisionar:** dentro do `suite-pg`,
  `PGPASSWORD=$OPERATOR_PASSWORD /usr/lib/postgresql/18/bin/psql -h localhost -p 5433 -U postgres`.
  O `SU_PASSWORD` **nao** autentica `postgres`. `fly pg connect -c` e `--config`, nao
  `--command`.
- **Windows:** as variaveis de usuario (`PROD_READONLY_DB_*`, `PGSERVICEFILE`) so
  entram num shell **novo** — reabra o terminal/agente depois do bootstrap.
- `fly secrets import` reinicia o app; no `app2037` isso e um rolling normal, mas
  evite fazer em cima de deploy de codigo.
