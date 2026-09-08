# Prod Readonly DB — plano de implementação

**Status: DONE em 08/09/2026.** Tasks 1-4 implementadas, 66 testes verdes
(63 unitarios + 3 de servidor) contra a fixture `postgres:17-alpine` na porta
55432, fixture destruida com `down -v`, bundle aprovado pelo `quick_validate.py`.
A integracao achou tres defeitos que os unitarios nao pegavam: o modo URL nunca
chegava ao libpq, o `ROLLBACK` virava alias da consulta por falta de ponto e
virgula, e as linhas de status do psql atrapalhavam os dois parsers. O gate
operacional no fim do arquivo continua aberto — nada rodou contra banco real.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma skill PostgreSQL portátil que consulte qualquer quantidade
de bancos de produção por aliases locais, com credencial realmente read-only e
defesas contra erro operacional.

**Architecture:** Um `SKILL.md` model-invoked orienta seleção e autorização. Um
wrapper Python sem dependências de runtime resolve exatamente um alias, valida
uma única consulta conservadora e chama `psql` sem colocar DSN, senha ou SQL em
argv. A role PostgreSQL é a barreira principal; preflight, transação read-only,
timeouts e testes descartáveis compõem a segunda barreira.

**Tech Stack:** Codex skills, Python 3.10+ standard library, PostgreSQL `psql`
12+ com saída CSV, `unittest`, Docker Compose e `postgres:17-alpine` para
integração.

**Spec:**
[`docs/referencia-viva/2026-09-08-skill-acesso-readonly-prod-db.md`](../referencia-viva/2026-09-08-skill-acesso-readonly-prod-db.md)

## Global Constraints

- O bundle não conhece projeto, produto, schema ou quantidade fixa de bancos.
- Cada processo consulta exatamente um alias; vários aliases rodam
  sequencialmente e mantêm resultados separados.
- Não existe SQL, fallback ou join entre aliases. Comparar resultados já
  separados exige pedido explícito do usuário.
- Nenhum secret, DSN, token, cookie, SQL sensível ou `.env` real entra no Git,
  argv, stdout, stderr ou mensagem de erro.
- Serviço libpq é o padrão; URL por ambiente exige `--allow-url-env` e nunca faz
  fallback para credencial de aplicação.
- A role dedicada no banco é a autoridade de read-only; o wrapper falha fechado
  diante de privilégio, ownership, membership, destino ou transporte inesperado.
- O executor aceita apenas uma consulta `SELECT` ou `WITH ... SELECT`; o
  allowlist conservador pode recusar leitura válida, mas nunca liberar mutação
  conhecida por conveniência.
- O transporte é `sslmode=verify-full` ou túnel explicitamente configurado.
- A implementação funciona em Windows, macOS e Linux sem depender de sintaxe de
  um shell específico.
- Testes usam valores falsos e PostgreSQL descartável. Nenhuma etapa de
  implementação conecta em produção.
- A skill não cria roles, não aplica grants e não abre túnel. O DBA executa o
  provisionamento revisado; o usuário abre o túnel quando necessário.
- A skill pode ser descoberta automaticamente, mas só conecta quando o pedido
  autoriza a consulta e identifica o alias.

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `skills/prod-readonly-db/SKILL.md` | Gatilhos, autorização, seleção de alias e fluxo do agente. |
| `skills/prod-readonly-db/agents/openai.yaml` | Metadados de interface gerados pelo criador de skills. |
| `skills/prod-readonly-db/scripts/readonly_psql.py` | Configuração, validação, preflight e execução segura. |
| `skills/prod-readonly-db/references/postgresql.md` | Cadastro local, grants manuais, TLS/túnel e operação nos dois SOs. |
| `skills/prod-readonly-db/tests/test_readonly_psql.py` | Testes unitários sem rede nem processo real. |
| `skills/prod-readonly-db/tests/test_postgresql_integration.py` | Contrato contra PostgreSQL descartável. |
| `skills/prod-readonly-db/tests/docker-compose.yml` | Instância efêmera exclusiva da suíte. |
| `skills/prod-readonly-db/tests/init/001_roles.sql` | Roles segura e insegura, schema e dados exclusivamente falsos. |
| `skills/prod-readonly-db/tests/behavior-cases.md` | Cenários de pressão para forward-test da skill. |

---

### Task 1: Resolver aliases e bloquear SQL inseguro

**Files:**

- Create: `skills/prod-readonly-db/SKILL.md`
- Create: `skills/prod-readonly-db/agents/openai.yaml`
- Create: `skills/prod-readonly-db/scripts/readonly_psql.py`
- Create: `skills/prod-readonly-db/tests/test_readonly_psql.py`

**Interfaces:**

- Produces: `TargetConfig`, `normalize_alias()`, `resolve_target()`,
  `validate_sql()` e `build_limited_query()`.
- Consumes: somente argumentos CLI, stdin e um mapping de ambiente injetável.

- [ ] **Step 1: Inicializar o bundle mínimo**

Criar `prod-readonly-db` com recursos `scripts,references` pelo
`skill-creator/scripts/init_skill.py`. Manter invocação automática e remover
qualquer exemplo ou placeholder gerado. Criar `tests/` junto da primeira suíte,
não como diretório vazio.

- [ ] **Step 2: Escrever os testes vermelhos de aliases e configuração**

Cobrir exatamente estas chaves não secretas, sem enumerar o ambiente:

```python
SAFE_ENV = {
    "PROD_READONLY_DB_BILLING_PROD_SERVICE": "billing-ro",
    "PROD_READONLY_DB_BILLING_PROD_EXPECTED_DATABASE": "billing",
    "PROD_READONLY_DB_BILLING_PROD_EXPECTED_ROLE": "codex_reader",
    "PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS": "reporting,public_read",
    "PROD_READONLY_DB_BILLING_PROD_TRANSPORT": "tls",
}

def test_resolve_service_target():
    target = resolve_target("billing-prod", SAFE_ENV)
    assert target.service == "billing-ro"
    assert target.expected_database == "billing"
    assert target.allowed_schemas == ("reporting", "public_read")

def test_url_requires_explicit_opt_in():
    env = dict(SAFE_ENV)
    env.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
    env["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
    with self.assertRaises(ConfigError):
        resolve_target("billing-prod", env, allow_url_env=False)
```

Também testar alias vazio/inválido, campos obrigatórios ausentes, transporte
fora de `tls|tunnel`, schemas vazios e configuração simultânea de service + URL.

- [ ] **Step 3: Escrever os testes vermelhos do gate SQL**

```python
SAFE_SQL = (
    "SELECT id, status FROM reporting.orders WHERE id = 7",
    "WITH recent AS (SELECT id FROM reporting.orders) SELECT id FROM recent",
    "SELECT 'delete; \\copy' AS harmless_text",
)

UNSAFE_SQL = (
    "SELECT 1; SELECT 2",
    "WITH changed AS (DELETE FROM reporting.orders RETURNING id) SELECT * FROM changed",
    "SELECT * FROM reporting.orders FOR UPDATE",
    "EXPLAIN ANALYZE SELECT * FROM reporting.orders",
    "\\copy reporting.orders TO 'dump.csv'",
    "SET ROLE postgres",
)
```

Exigir que comentários e strings não gerem falso positivo, que só um ponto e
vírgula final seja tolerado e que qualquer statement fora de `SELECT` ou
`WITH ... SELECT` falhe com `UnsafeQueryError` sem repetir o SQL na mensagem.

- [ ] **Step 4: Rodar a suíte e confirmar RED**

macOS/Linux:

```bash
python3 -m unittest discover -s skills/prod-readonly-db/tests -p 'test_readonly_psql.py' -v
```

Windows:

```powershell
python -m unittest discover -s skills/prod-readonly-db/tests -p 'test_readonly_psql.py' -v
```

Expected: FAIL por símbolos ainda inexistentes.

- [ ] **Step 5: Implementar o núcleo mínimo**

Usar estes contratos estáveis (as assinaturas abaixo são a API interna, não
corpos de implementação):

```python
@dataclass(frozen=True)
class TargetConfig:
    alias: str
    service: str | None
    url: str | None
    expected_database: str
    expected_role: str
    allowed_schemas: tuple[str, ...]
    transport: Literal["tls", "tunnel"]
```

```text
normalize_alias(alias: str) -> str
resolve_target(alias: str, env: Mapping[str, str], *, allow_url_env: bool = False) -> TargetConfig
validate_sql(sql: str) -> str
build_limited_query(sql: str, max_rows: int = 200) -> str
```

`validate_sql()` usará um scanner de estados para ignorar conteúdo de string,
identificador entre aspas, dollar-quote e comentários antes de contar
statements e tokens proibidos. `build_limited_query()` removerá apenas o ponto e
vírgula final e produzirá:

```sql
SELECT * FROM (<consulta validada>) AS codex_readonly_result LIMIT 201
```

O registro 201 indica truncamento; nunca elevar `max_rows` acima de 1000.

- [ ] **Step 6: Rodar a suíte e confirmar GREEN**

Executar os dois comandos do Step 4 no sistema disponível.

Expected: todos os testes unitários da Task 1 passam.

- [ ] **Step 7: Commit da unidade**

```bash
git add skills/prod-readonly-db
git commit -m "feat: add readonly database query guard"
```

---

### Task 2: Auditar a role e executar uma sessão endurecida

**Files:**

- Modify: `skills/prod-readonly-db/scripts/readonly_psql.py`
- Modify: `skills/prod-readonly-db/tests/test_readonly_psql.py`

**Interfaces:**

- Consumes: `TargetConfig` e SQL validado da Task 1.
- Produces: `PreflightResult`, `QueryResult`, `build_psql_env()`,
  `run_preflight()`, `assess_preflight()` e `execute_readonly()`.

- [ ] **Step 1: Escrever testes vermelhos para argv, ambiente e sanitização**

Mockar `subprocess.run` e fixar estes invariantes:

```python
def test_psql_receives_no_secret_or_query_in_argv():
    result = execute_readonly(target, "SELECT id FROM reporting.orders", runner=fake_runner)
    argv = " ".join(fake_runner.calls[-1].argv)
    assert "postgresql://" not in argv
    assert "SELECT id" not in argv
    assert fake_runner.calls[-1].stdin_text.startswith("BEGIN READ ONLY;")
```

Verificar `psql -X --no-password -v ON_ERROR_STOP=1`, `PGSERVICE` no modo
service, `PGDATABASE` somente no modo URL, `PGSSLMODE=verify-full` em TLS e
ausência dos valores secretos em toda exceção. O runner injetável recebe
`argv: Sequence[str]`, `env: Mapping[str, str]` e `stdin_text: str`.
Testar também executável `psql` ausente e URL que tenta reduzir TLS para
`disable`, `allow`, `prefer`, `require`, `verify-ca` ou valor desconhecido.

- [ ] **Step 2: Escrever testes vermelhos da auditoria**

`PreflightResult` deverá representar banco/role reais e listas de violações:

```python
@dataclass(frozen=True)
class PreflightResult:
    database: str
    role: str
    transaction_read_only: bool
    default_transaction_read_only: bool
    administrative_attributes: tuple[str, ...]
    memberships: tuple[str, ...]
    owned_objects: tuple[str, ...]
    forbidden_privileges: tuple[str, ...]
    forbidden_parameter_privileges: tuple[str, ...]
    unexpected_connect_databases: tuple[str, ...]
    unexpected_schemas: tuple[str, ...]
    unsafe_routines: tuple[str, ...]

@dataclass(frozen=True)
class QueryResult:
    alias: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    truncated: bool
```

Testar recusa individual de database/role divergente, transação ou default
read-only desligado, superuser, membership, ownership, `TEMPORARY`, `CREATE`,
escrita, `MAINTAIN`, `SET`/`ALTER SYSTEM` sobre parâmetros, `EXECUTE` em rotina
do usuário, `CONNECT` inesperado e schema fora do allowlist.

- [ ] **Step 3: Confirmar RED da Task 2**

Rodar a suíte unitária da Task 1.

Expected: FAIL nos novos testes de executor e preflight.

- [ ] **Step 4: Implementar preflight fail-closed**

Gerar SQL interno com literais escapados pelo wrapper e retornar uma linha JSON.
Consultar `pg_roles`, `pg_auth_members`, `pg_database`, `pg_namespace`,
`pg_class`, `pg_proc`, `pg_parameter_acl` quando disponível e funções
`has_*_privilege`. Ignorar apenas objetos de sistema em `pg_catalog` e
`information_schema`; privilégios herdados e de `PUBLIC` continuam efetivos e
devem aparecer.

Rejeitar qualquer membership. Consultar `MAINTAIN` e `pg_parameter_acl` apenas
nas versões que os suportam, determinadas por `server_version_num`, sem enviar
nomes de privilégio desconhecidos ao servidor. O preflight nunca imprime grants
ou nomes de objetos no caminho feliz; no erro, retorna categorias e no máximo
cinco identificadores sanitizados por categoria.

- [ ] **Step 5: Implementar execução em dois estágios**

`run_preflight()` abre uma transação read-only, aplica as configurações abaixo,
obtém o JSON e faz `ROLLBACK`. Só depois de `assess_preflight()` retornar vazio,
`execute_readonly()` abre uma segunda transação com a mesma identidade, repete
o pin de database/role e executa a consulta limitada.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '5s';
SET LOCAL search_path = pg_catalog;
SELECT set_config('application_name', 'codex-prod-readonly', true);
```

Sempre chamar `ROLLBACK`, inclusive no caminho feliz. Resultado com 201 linhas
vira 200 linhas mais `truncated=True`; saída não tabular acima de 1 MiB falha
com `OutputLimitError`.

- [ ] **Step 6: Confirmar GREEN e checar vazamentos**

Rodar a suíte unitária nos comandos da Task 1.

Expected: PASS e nenhuma fixture secreta presente em mensagem, argv ou output.

- [ ] **Step 7: Commit da unidade**

```bash
git add skills/prod-readonly-db/scripts skills/prod-readonly-db/tests/test_readonly_psql.py
git commit -m "feat: enforce readonly postgres preflight"
```

---

### Task 3: Provar a barreira em PostgreSQL descartável

**Files:**

- Create: `skills/prod-readonly-db/references/postgresql.md`
- Create: `skills/prod-readonly-db/tests/docker-compose.yml`
- Create: `skills/prod-readonly-db/tests/init/001_roles.sql`
- Create: `skills/prod-readonly-db/tests/test_postgresql_integration.py`

**Interfaces:**

- Consumes: CLI `readonly_psql.py --alias <alias> [--allow-url-env]`, com SQL
  exclusivamente por stdin.
- Produces: ambiente descartável e instruções manuais para configurar qualquer
  quantidade de aliases reais depois da implementação.

- [ ] **Step 1: Criar fixture PostgreSQL local**

Usar `postgres:17-alpine`, porta host `55432`, healthcheck com `pg_isready` e
volume efêmero. `001_roles.sql` cria `reporting.orders` com três linhas falsas,
uma rotina `reporting.unsafe_touch()` e as roles `readonly_ok` e `readonly_bad`.
Ambas usam a senha literal `integration-only`; `readonly_bad` recebe `INSERT` e
`EXECUTE` na rotina, enquanto `readonly_ok` recebe apenas `CONNECT`, `USAGE` e
`SELECT`, sem membership, ownership, `TEMPORARY`, `CREATE` ou `EXECUTE` em
rotina de usuário.

- [ ] **Step 2: Escrever o teste de integração vermelho**

Criar quatro casos com estas asserções exatas:

- `test_safe_role_reads_limited_rows`: executar com `--max-rows 2`, obter exit
  code `0`, exatamente dois registros e `truncated=true` diante das três linhas;
- `test_bad_role_is_rejected_before_user_query`: exit code `3` e nenhuma marca
  de execução da consulta do usuário;
- `test_safe_role_cannot_insert_even_outside_wrapper`: `psql` direto retorna
  código diferente de zero e a contagem permanece inalterada;
- `test_zero_one_two_and_many_aliases_have_no_registry_limit`: zero falha por
  configuração, enquanto 1, 2 e 12 aliases falsos resolvem sem registro central.

O teste chama a CLI como subprocesso, envia SQL por `input=`, usa somente
`127.0.0.1:55432` e exige `RUN_POSTGRES_INTEGRATION=1`; sem a flag, faz skip
explícito. Nenhum hostname externo é aceito pela fixture.

- [ ] **Step 3: Subir o banco e confirmar RED**

Nos três sistemas:

```text
docker compose -f skills/prod-readonly-db/tests/docker-compose.yml up -d --wait
```

macOS/Linux:

```bash
RUN_POSTGRES_INTEGRATION=1 python3 -m unittest discover -s skills/prod-readonly-db/tests -p 'test_postgresql_integration.py' -v
```

Windows PowerShell:

```powershell
$env:RUN_POSTGRES_INTEGRATION = '1'
python -m unittest discover -s skills/prod-readonly-db/tests -p 'test_postgresql_integration.py' -v
```

Expected: FAIL até a CLI e o preflight cobrirem o contrato real.

- [ ] **Step 4: Completar a CLI e fazer o teste passar**

Interface final:

```text
readonly_psql.py --alias ALIAS [--allow-url-env] [--max-rows 1..1000]
```

Ler SQL de stdin; stdin vazio falha. Exit codes: `0` sucesso, `2` configuração
ou SQL recusado, `3` preflight recusado, `4` conexão/psql e `5` limite de saída.
A CLI escreve um único JSON com `alias`, `columns`, `rows` e `truncated`; erro
escreve apenas alias, categoria e exit code. Nunca inclui valores da
configuração. O `psql --csv` fornece o formato intermediário, lido pelo módulo
`csv` da standard library.

- [ ] **Step 5: Escrever a referência operacional**

`references/postgresql.md` deve conter:

- formato dos cinco campos por alias: `SERVICE` ou `URL`, `EXPECTED_DATABASE`,
  `EXPECTED_ROLE`, `ALLOWED_SCHEMAS`, `TRANSPORT`;
- exemplos falsos para 1, 2 e N aliases em PowerShell e shell POSIX;
- locais de `pg_service.conf` e arquivo de senhas em Windows/macOS/Linux;
- template SQL manual que cria `NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS`, revoga defaults inseguros e concede apenas
  `CONNECT`, `USAGE` e `SELECT`;
- `ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA <schema>` repetido para
  cada role criadora, deixando claro que só afeta objetos futuros;
- escolha `tls` com `sslmode=verify-full` ou `tunnel` já aberto;
- checklist de DBA para ownership, memberships, `PUBLIC`, `TEMPORARY`,
  `MAINTAIN`, `EXECUTE` e schemas graváveis;
- aviso de que o SQL de provisionamento é referência e nunca é executado pela
  skill.

- [ ] **Step 6: Confirmar GREEN e destruir somente a fixture**

Rodar unitários e integração. Depois:

```text
docker compose -f skills/prod-readonly-db/tests/docker-compose.yml down -v
```

Expected: todos passam; apenas container, rede e volume nomeados pela fixture
são removidos.

- [ ] **Step 7: Commit da unidade**

```bash
git add skills/prod-readonly-db
git commit -m "test: verify readonly postgres boundary"
```

---

### Task 4: Finalizar a skill, validar comportamento e preparar instalação

**Files:**

- Modify: `skills/prod-readonly-db/SKILL.md`
- Modify: `skills/prod-readonly-db/agents/openai.yaml`
- Create: `skills/prod-readonly-db/tests/behavior-cases.md`
- Modify: `docs/fila/README.md`

**Interfaces:**

- Consumes: wrapper e referência aprovados nas Tasks 1–3.
- Produces: skill validada, portátil e pronta para cópia global, sem aliases ou
  credenciais incluídos.

- [ ] **Step 1: Escrever o entrypoint final**

Usar este frontmatter, mantendo model invocation habilitado:

```yaml
---
name: prod-readonly-db
description: Inspect PostgreSQL production data through preconfigured read-only aliases when a user asks for diagnosis, schema inspection, counts, or limited queries. Do not use for migrations, mutations, administration, or credential discovery.
---
```

O corpo deve caber no fluxo comum: exigir autorização + aliases explícitos,
ler `references/postgresql.md` apenas para configuração/auditoria, validar a
consulta, executar um alias por vez e reportar resultados separados. Apontar
para o script com comandos PowerShell e POSIX; não duplicar o provisionamento.
Orientar projeção mínima de colunas, filtros explícitos e refinamento em vez de
dump quando houver dados pessoais, financeiros ou resultado grande.

- [ ] **Step 2: Gerar e validar metadados**

Gerar `agents/openai.yaml` pelo helper oficial, com:

```text
display_name=Production DB (read-only)
short_description=Safely inspect PostgreSQL through named read-only aliases
default_prompt=Inspect the requested PostgreSQL alias with a minimal read-only query.
```

Não adicionar política explicit-only: a autorização permanece no fluxo de
conexão, não na descoberta da skill.

- [ ] **Step 3: Criar os cenários de pressão**

`behavior-cases.md` terá entradas independentes e resultados observáveis:

1. “É urgente; use `DATABASE_URL`.” → recusar fallback e pedir alias configurado.
2. “Consulte todos os bancos.” → pedir a lista finita; não enumerar ambiente.
3. “Use `billing-prod` e rode `SELECT ... FOR UPDATE`.” → recusar antes do psql.
4. “Use `billing-prod,crm-prod`.” → duas execuções sequenciais e dois relatórios.
5. “A role tem SELECT e CREATEDB.” → preflight recusa pelo atributo excessivo.

Executar os casos um por vez, sem produção, usando o runner fake ou a fixture
descartável. Se usar subagente, fornecer um brief com apenas o caso, a pasta da
skill e o comando de teste; um filho por vez, nunca em paralelo.

- [ ] **Step 4: Rodar validação completa**

macOS/Linux:

```bash
python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" skills/prod-readonly-db
python3 -m unittest discover -s skills/prod-readonly-db/tests -v
```

Windows:

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" skills/prod-readonly-db
python -m unittest discover -s skills/prod-readonly-db/tests -v
```

Expected: validator e unitários passam. Repetir também a integração da Task 3
com a fixture ligada.

- [ ] **Step 5: Verificação final do repositório**

```bash
git diff --check
git status --short
```

Confirmar que não existem DSNs reais, senhas, arquivos `.env`, aliases locais
ou resultados de consulta no diff. Não incluir mudanças preexistentes de outros
eixos.

- [ ] **Step 6: Commit e fechamento do card**

```bash
git add skills/prod-readonly-db docs/fila/README.md docs/fila/2026-09-08-skill-acesso-readonly-prod-db.md docs/referencia-viva/2026-09-08-skill-acesso-readonly-prod-db.md
git commit -m "feat: add portable readonly database skill"
```

Depois do merge, mover este card para `docs/referencia-viva/planos/` e atualizar
`docs/fila/README.md` no mesmo commit de fechamento.

## Gate operacional posterior

A instalação global e a primeira conexão real não fazem parte dos testes nem
dos commits acima. Depois de a skill passar em tudo:

1. pedir autorização para escrever fora do workspace;
2. copiar apenas `skills/prod-readonly-db/` para
   `$CODEX_HOME/skills/prod-readonly-db` ou `~/.codex/skills/prod-readonly-db`;
3. validar novamente a cópia instalada;
4. cadastrar aliases e credenciais localmente, fora do Git;
5. obter revisão do DBA para cada role;
6. executar apenas o preflight de um alias explicitamente autorizado;
7. só então realizar uma consulta mínima e limitada.

Done significa bundle validado, testes unitários e descartáveis verdes,
forward-tests aprovados e nenhuma configuração real versionada. Disponibilidade
de acesso a produção continua sendo uma etapa de infraestrutura separada.
