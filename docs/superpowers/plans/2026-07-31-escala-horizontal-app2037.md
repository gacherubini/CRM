# Escala horizontal do `app2037` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir `fly scale count N` no `app2037` sem divergência de dados nem trabalho duplicado, tirando estado do volume local e garantindo que cada job periódico rode em exatamente uma machine.

**Architecture:** Três fases independentes e testáveis. **Fase A** move todo estado durável do volume `app_data` para o `suite-pg` (Portal, Tráfego, Catálogo) e para object storage (mídia do Estoque), deixando o container sem estado. **Fase B** transforma os 8 loops de worker que hoje rodam dentro do processo web em ticks coordenados por `pg_try_advisory_lock`, para que N réplicas produzam 1 execução por intervalo. **Fase C** remove o `[[mounts]]`, define limites de concorrência e escala, tratando o `suite-pg` como o próximo gargalo.

**Tech Stack:** Fly Machines + Volumes, `flyio/postgres-flex:18.1`, Tigris (object storage S3-compatível da Fly), SQLAlchemy 2.x, Alembic 1.14, `psycopg[binary]` 3.x, `boto3`, supervisord, nginx, pytest.

---

## Global Constraints

- **O `app2037` continua sendo um bundle único.** Separar os 6 serviços em apps Fly próprios desfaria a consolidação 3-VM, que existe por custo (`deploy/fly/3vm/README.md:18-31`; a migração para `iad` derrubou o custo de ~US$36,80 para ~US$20,28/mês). **Não-escopo declarado.** Escala horizontal aqui significa N cópias do mesmo bundle.
- **Cada produto tem banco e migrations próprios.** É **proibido** criar import Python entre produtos (`CLAUDE.md`, "Fluxos que atravessam servicos"). Toda integração continua por contrato HTTP/evento versionado. Isso implica: cada produto ganha a sua própria cópia do helper de advisory lock; não existe módulo compartilhado entre `portal-gestao/` e `revy-trafego/`.
- **Testes rodam a partir da pasta do produto**, para não importar o pacote `app` errado:
  - `cd portal-gestao && .venv/bin/python -m pytest -q` → **471 passed** (baseline)
  - `cd revy-trafego && .venv/bin/python -m pytest -q` → **361 passed, 1 failed** (baseline)
  - `cd chatbot-api && python -m pytest -q` → **246 passed**
  - `cd catalogo-publico && python -m pytest -q` → **53 passed**
- **Falha pré-existente e fora de escopo:** `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts` (linha 165) falha desde o commit `573348e`. **Não é regressão desta fase e não deve ser "consertada de passagem"** — mas **deve ser corrigida** em trabalho próprio, porque é exatamente o teste que cobre o caminho de falha do outbox de provisionamento que a Fase B toca. Qualquer task que rode a suíte do Revy aceita `361 passed, 1 failed` e **nada além disso**.
- **Migração de dados só acontece com backup verificável e rollback escrito.** Nenhum `.db` de origem é apagado nesta implementação; o cutover é por variável de ambiente, e reverter é reverter a variável.
- **Nunca imprimir segredo** em terminal, log, commit ou documento. `fly secrets list` só mostra nomes.
- **`fly apps destroy` e destroy de volumes continuam proibidos sem pedido explícito do owner** (`deploy/fly/3vm/README.md:426`). Este plano destrói **um** volume (`app_data`), e só na Task C3, depois de todos os gates.
- Toda evidência de execução vai para `$SCRATCH/escala-app2037/`, fora do repo.

---

## Inventário congelado (verificado 2026-07-31)

| Recurso | Valor real |
|---|---|
| `app2037` machine | `48e1e6ea557558` · `iad` · `shared-cpu-1x:1024MB` · started · 1/1 checks |
| `app2037` volume | `vol_vdeg231ez2xnq234` (`app_data`, 1GB, `iad`) |
| `suite-pg` machine | `48ee5d4ad12768` · `iad` · `shared-cpu-1x:512MB` · primary · 3/3 checks |
| `suite-pg` volume | `vol_4m39jng3n3k6qxgv` |
| DBs no `suite-pg` | `chatbot`, `estoque`, `evolution`, `motor`, `postgres`, `repmgr` |
| Secrets de DB no `app2037` | `CHATBOT_DATABASE_URL`, `ESTOQUE_DATABASE_URL`, `MOTOR_DATABASE_URL` |
| Secrets de DB **ausentes** | `PORTAL_DATABASE_URL`, `REVY_TRAFEGO_DATABASE_URL`, `CATALOGO_DATABASE_PATH` |

**Divergência achada:** `deploy/fly/3vm/fly.app.toml:100` declara `memory = "1536"`, mas a machine real está com **1024MB**. O toml não é a fonte de verdade do tamanho atual. Registrar; não corrigir agora (a Task C3 fixa isso ao redeployar).

---

## Bloqueador 1 — estado durável no volume local

`deploy/fly/3vm/fly.app.toml` e `deploy/fly/3vm/entrypoint-app.sh` colocam três bancos e a mídia dentro de `/data`:

| Env | Valor atual | Onde |
|---|---|---|
| `PORTAL_DATABASE_URL` | `sqlite:////data/portal/portal.db` | `fly.app.toml:16`, `entrypoint-app.sh:27`, `run-portal.sh:3` |
| `REVY_TRAFEGO_DATABASE_URL` | `sqlite:////data/revy-trafego/revy_trafego.db` | `fly.app.toml:31`, `entrypoint-app.sh:34`, `run-revy-trafego.sh:3` |
| `CATALOGO_DATABASE_PATH` | `/data/catalogo/catalogo.db` | `fly.app.toml:17`, `entrypoint-app.sh:28`, `run-catalogo.sh:3` |
| `ESTOQUE_MEDIA_STORAGE_DIR` | `/data/estoque/media` | `fly.app.toml:63`, `entrypoint-app.sh:35` |
| `MOTOR_SCREENSHOT_DIR` / `MOTOR_STORAGE_STATE_DIR` | `/data/motor/*` | `entrypoint-app.sh:36-37` |

Volume Fly é disco local **single-attach**. `fly scale count 2` faz a Fly provisionar um `app_data` novo e **vazio** para a segunda machine: dois Portais, dois Tráfegos e dois Catálogos com bancos divergentes, **em silêncio**. E o lock do SQLite é POSIX de arquivo — não coordena entre hosts nem se o volume fosse compartilhado.

**Facilita:** Portal e Revy Tráfego usam SQLAlchemy com a URL vinda de `settings.database_url` (`portal-gestao/app/db.py:13`, `revy-trafego/app/db.py:13`), já têm Alembic (16 e 14 migrations) e já têm `psycopg[binary]==3.*` no `requirements.txt`. Para esses dois, migrar é **config + cópia de dados**, não reescrita.

**Complica — achado que contraria a premissa inicial:** o **Catálogo não usa SQLAlchemy**. `catalogo-publico/app/events.py` e `catalogo-publico/app/provisioning.py` usam `sqlite3` cru, com `PRAGMA table_info` fazendo migration em código (`events.py:60-72`), placeholders `?` e `INSERT OR IGNORE`. O `catalogo-publico/requirements.txt` **não tem** `sqlalchemy`, `alembic` nem `psycopg`. Trocar `CATALOGO_DATABASE_PATH` por uma URL de Postgres **não funciona** — é port de código. São 3 tabelas (`interest_events`, `event_outbox`, `loja_operacional_projecao`) e ~350 linhas, com 53 testes cobrindo o comportamento. Fica em duas tasks próprias (A5 e A6).

**Mídia do Estoque:** confinada em `estoque-api/app/media.py` (`salvar`, `resolver_publica`, `caminho_seguro`, `remover_por_url`) + dois call sites em `estoque-api/app/main.py:368,569`. A `storage_key` já é content-addressed (`{loja}/{veiculo}/{sha256[:32]}.{ext}`), então mapeia 1:1 para uma key de object storage. Precisa de código: um backend S3.

---

## Bloqueador 2 — 8 loops de worker dentro do processo web

`portal-gestao/app/main.py:281-296` (`_lifespan`) e `revy-trafego/app/main.py:82-135` (`_lifespan`) sobem threads daemon que fazem `while not stop: run_once(); wait(interval)`. Todos os 8 `_run` são byte-idênticos nessa forma.

Com N machines viram N cópias de cada loop. Idempotência **verificada arquivo por arquivo**:

| Worker | Arquivo | Duplicação segura? | Evidência |
|---|---|---|---|
| Portal · outbox Portal→Revy | `portal-gestao/app/revy_trafego_outbox_job.py` | **Sim** | claim por compare-and-swap em `status`+`atualizada_em` (`portal-gestao/app/revy_trafego_outbox.py:189-202`) |
| Portal · CAPI retry | `portal-gestao/app/meta_capi_job.py` | **Sim, mas desligado** | `PORTAL_CAPI_RETRY_ENABLED=0` em `fly.app.toml:43` |
| Portal · Meta spend sync | `portal-gestao/app/meta_ads_spend_job.py` | **Sim, mas desligado** | `PORTAL_META_SPEND_SYNC_ENABLED=0` em `fly.app.toml:44` |
| Revy · CAPI retry | `revy-trafego/app/meta_capi_job.py` | **Sim** | claim CAS + lease em `_reivindicar_outbox` (`revy-trafego/app/meta_capi.py:459-480`); o loop conta `concorrentes` explicitamente |
| Revy · Meta spend sync | `revy-trafego/app/meta_ads_spend_job.py` | **Não** | `sincronizar_gastos_meta` (`revy-trafego/app/meta_ads_spend.py:172`) chama a Marketing API e grava `CampanhaGasto` sem claim; N cópias = N chamadas pagas à Meta e corrida de escrita |
| Revy · provisioning outbox | `revy-trafego/app/control/provisioning_job.py` | **NÃO** | `process_pending` (`revy-trafego/app/control/provisioning_outbox.py:142-162`) lê `pending`/`failed`, chama `poster(...)` e só então grava `delivered`. **Zero claim.** Duas machines entregam o mesmo provisionamento duas vezes ao Chatbot/Estoque/Portal |
| Revy · Google conversions outbox | `revy-trafego/app/control/google_ads_conversions_job.py` | **Sim, no destino** | `process_outbox_once` (`google_ads_conversions.py:369-400`) também não tem claim local, mas `transaction_id` é determinístico (`build_transaction_id`, `google_ads_conversions.py:117-122`) e o Google deduplica. Custa `attempts` inflado, não conversão dupla |
| Revy · Google Ads metrics sync | `revy-trafego/app/control/google_ads_metrics_job.py` | **Sim** | é pull + `_upsert_metric_rows` (`google_ads_metrics.py:606`); rodar duas vezes converge no mesmo estado |

**Nono worker, não listado no briefing:** `catalogo-publico/app/main.py:60-71` sobe um `OutboxWorker` (`catalogo-publico/app/outbox.py:25`). Ele posta com `Idempotency-Key: event_id` e o consumidor (`chatbot-api/app/main.py:621-632`) valida e deduplica por `event_id`. **Duplicação é segura no destino.** Mas com o Catálogo em Postgres (Task A6) duas machines passam a competir pela mesma fila, então ele entra no escopo da Fase B junto com os outros.

**Escape hatch que já existe** (confirmado, com os paths exatos):

| Endpoint | Arquivo | Auth |
|---|---|---|
| `POST /internal/jobs/meta-spend-sync` (Portal) | `portal-gestao/app/web/trafego.py:905` | `X-Job-Token` vs `PORTAL_META_SPEND_JOB_SECRET` |
| `POST /internal/jobs/meta-spend-sync` (Revy) | `revy-trafego/app/main.py:1316` | `X-Job-Token` vs `REVY_TRAFEGO_JOB_SECRET`, fallback `PORTAL_META_SPEND_JOB_SECRET` |
| `POST /internal/jobs/google-conversions-outbox` | `revy-trafego/app/main.py:1337` | idem |
| `POST /internal/jobs/google-ads-metrics-sync` | `revy-trafego/app/main.py:1360` | idem |

**Não existe** endpoint para o CAPI retry, para o outbox de provisionamento nem para o outbox Portal→Revy. Isso é o que torna a opção "disparo externo" incompleta hoje — ver a análise na Fase B.

---

## Não é bloqueador (verificado, para ninguém reabrir)

- **Sessão HTTP.** `portal-gestao/app/main.py:303` usa `SessionMiddleware` do Starlette com `secret_key=settings.session_secret`. É cookie assinado, **stateless**: qualquer machine valida a sessão emitida por qualquer outra, desde que `PORTAL_SESSION_SECRET` (secret já existente no app) seja o mesmo — e é, porque secrets são app-scoped. Idem `REVY_TRAFEGO_SESSION_SECRET`. **Nenhuma sticky session é necessária.**
- **Índices parciais.** `revy-trafego` usa `sqlite_where` em 5 lugares no `models.py` e 5 nas migrations — e **todos os 5 têm `postgresql_where` gêmeo** (verificado: 5/5 nos dois). Os índices únicos parciais sobrevivem à troca de dialeto com a mesma semântica.
- **Sequences.** Portal e Revy usam `String(36)` com `default=novo_id` em todas as PKs. Não há `SERIAL`/`IDENTITY`, então não há sequence para reajustar depois de copiar dados.
- **Alembic.** `portal-gestao/alembic/env.py:11` e `revy-trafego/alembic/env.py:14` leem `settings.database_url` — ou seja, `PORTAL_DATABASE_URL` / `REVY_TRAFEGO_DATABASE_URL`, não `DATABASE_URL`. O `entrypoint-app.sh` exporta as duas, então funciona hoje e continua funcionando.
- **Uma origem de uvicorn por serviço.** `run-portal.sh` e `run-revy-trafego.sh` chamam `uvicorn` sem `--workers`: 1 processo por serviço por machine. Isso importa para o cálculo de conexões na Task C1.

---

## Lacuna

`deploy/fly/3vm/fly.app.toml:84-89` tem `[http_service]` **sem** bloco `[http_service.concurrency]`. Sem `soft_limit`/`hard_limit` o proxy da Fly não tem sinal de saturação: distribui round-robin sem saber quando parar de empurrar para uma machine. Fechado na Task C2.

---

## Riscos e decisões

**R1 — O Catálogo é um port, não uma troca de config.** Detalhado no Bloqueador 1. **Decisão:** portar `InterestStore` e `ProvisioningStore` para SQLAlchemy Core + Alembic, **preservando a assinatura pública das duas classes** (elas já são um seam: `catalogo-publico/app/main.py:78-80` só toca `app.state.interest_store` / `app.state.provisioning_store`). Os 53 testes existentes são o contrato de aceite. Alternativa rejeitada: manter SQL cru e trocar só o driver para psycopg — economiza pouco (ainda precisa converter `?`→`%s`, `INSERT OR IGNORE`→`ON CONFLICT DO NOTHING` e substituir o `PRAGMA table_info`) e deixa o Catálogo como o único produto sem Alembic, o que quebra o padrão do repositório e a regra de "migration head por produto".

**R2 — `suite-pg` é nó único de 512MB e vira o gargalo real.** Escalar o `app2037` para N multiplica conexões: cada machine roda 5 processos que falam com Postgres (chatbot, estoque, portal, revy, motor), e o `create_engine` default do SQLAlchemy é `pool_size=5, max_overflow=10` = até **15 conexões por processo**. Com N=2 isso é até **150 conexões**, contra um `max_connections` de um Postgres de 512MB que ninguém mediu. **Decisão:** a Task C1 é um Gate obrigatório que mede `max_connections` e fixa `pool_size`/`max_overflow` explícitos **antes** de qualquer `fly scale count`. Escalar sem isso troca "SQLite divergente" por "`FATAL: sorry, too many clients already`".

**R3 — advisory lock não protege os endpoints `/internal/jobs/*`.** A Fase B coloca o lock no laço `_run`, não em `run_once`. Isso é deliberado: um disparo manual de ops precisa rodar mesmo que o tick periódico esteja em outra machine. A consequência é que um `curl` no endpoint concorrente com um tick pode duplicar trabalho nos dois workers sem claim (spend sync e provisioning outbox). **Mitigação:** os endpoints são autenticados por `X-Job-Token` e chamados por humano/cron único; documentar no README que não devem ser postos em cron paralelo. Se isso virar problema, a saída é o claim CAS no `provisioning_outbox.process_pending` — que **não** está neste plano.

**R4 — janela de escrita durante a migração de dados.** O copiador da Task A2 lê um `.db` que pode estar recebendo escrita. **Decisão:** cada cutover (A3, A4, A6) para o processo alvo via `supervisorctl stop` antes de copiar e o religa depois da troca de env. A janela de indisponibilidade é de um serviço só, por ~1 minuto, não do bundle inteiro — o nginx do edge devolve 502 apenas nas rotas daquele serviço.

**R5 — Tigris é um serviço externo novo no caminho quente da vitrine.** Toda foto do Catálogo passa a depender de um GET no Tigris. **Decisão:** manter a URL pública inalterada (`https://app2037.fly.dev/public/v1/media/...`) e o Estoque continua servindo a foto, apenas lendo os bytes do Tigris em vez do disco. Isso (a) preserva as URLs já gravadas nas linhas de veículo, (b) preserva `ESTOQUE_MEDIA_ALLOWED_HOSTS`, (c) mantém o `Cache-Control: immutable` que já existe em `estoque-api/app/main.py:571-575`. Servir direto do Tigris exigiria reescrever URLs no banco e é não-escopo.

**R6 — o `motor2037` continua em `gru` e não escala aqui.** Este plano toca **apenas** o `app2037`. Os workers Playwright são outro app, on-demand, com o próprio mecanismo de slots (`worker_slots`). `MOTOR_ORCHESTRATOR_ONLY=1` no bundle significa que o processo `motor` do `app2037` só orquestra — mas o fan-out que acorda machines **também** é um loop, e N machines poderiam acordar workers em duplicata. **Gate na Task B3** decide se ele precisa de lock.

---

## Fase A — tirar estado do volume

### Task A1: Congelar backup verificável e criar os bancos no `suite-pg`

**Files:**
- Create: `$SCRATCH/escala-app2037/00-inventario.txt`
- Create: `$SCRATCH/escala-app2037/portal.db`, `revy_trafego.db`, `catalogo.db`, `media.tar.gz`

**Interfaces:**
- Produces: `PG_BASE` — a URL base do Postgres sem o nome do banco, no formato `postgresql://<user>:<senha>@suite-pg.flycast:5432`, extraída do secret já existente `CHATBOT_DATABASE_URL`. Consumida por A3, A4, A6 e C1.

- [ ] **Step 1: Criar o diretório de evidência**

```bash
export SCRATCH=/private/tmp/claude-501/-Users-gabrielabreucherubini-Documents-codigo-CRM/246546f6-14b2-4a2b-bc7b-96ceac8201bf/scratchpad
mkdir -p "$SCRATCH/escala-app2037" && cd "$SCRATCH/escala-app2037"
```

Reexportar `$SCRATCH` em cada sessão nova. Nada aqui entra no repo.

- [ ] **Step 2: Snapshot do volume antes de qualquer coisa**

```bash
fly volumes snapshots create vol_vdeg231ez2xnq234 -a app2037
fly volumes snapshots list vol_vdeg231ez2xnq234 -a app2037 | tail -3
```

Esperado: `Scheduled to snapshot volume ...` e, na listagem, um snapshot de hoje. A retenção da Fly é de 5 dias — **a janela de rollback por snapshot é de 5 dias**, não indefinida.

- [ ] **Step 3: Congelar o inventário**

```bash
fly machines list -a app2037   > 00-inventario.txt 2>&1
fly volumes  list -a app2037  >> 00-inventario.txt 2>&1
fly secrets  list -a app2037  >> 00-inventario.txt 2>&1
fly machines list -a suite-pg >> 00-inventario.txt 2>&1
```

`fly secrets list` nunca imprime valor, só nome. Conferir que `PORTAL_DATABASE_URL` e `REVY_TRAFEGO_DATABASE_URL` continuam **ausentes** — se apareceram, alguém migrou fora deste plano e o plano precisa ser revisto antes de seguir.

- [ ] **Step 4: Baixar os três bancos e a mídia para fora da Fly**

```bash
fly ssh sftp get /data/portal/portal.db              "$SCRATCH/escala-app2037/portal.db"        -a app2037
fly ssh sftp get /data/revy-trafego/revy_trafego.db  "$SCRATCH/escala-app2037/revy_trafego.db"  -a app2037
fly ssh sftp get /data/catalogo/catalogo.db          "$SCRATCH/escala-app2037/catalogo.db"      -a app2037
fly ssh console -a app2037 -C "tar czf /tmp/media.tar.gz -C /data/estoque media"
fly ssh sftp get /tmp/media.tar.gz "$SCRATCH/escala-app2037/media.tar.gz" -a app2037
ls -la "$SCRATCH/escala-app2037"
```

- [ ] **Step 5: Verificar que os backups são utilizáveis, não só grandes**

```bash
for f in portal.db revy_trafego.db catalogo.db; do
  echo -n "$f: "; sqlite3 "$SCRATCH/escala-app2037/$f" "PRAGMA integrity_check;"
  sqlite3 "$SCRATCH/escala-app2037/$f" \
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" | tr '\n' ' '; echo
done
tar tzf "$SCRATCH/escala-app2037/media.tar.gz" | wc -l
```

Esperado: `ok` nos três `integrity_check`; lista de tabelas não vazia; contagem de arquivos de mídia registrada (pode ser `1` se só houver o diretório — isso significa **zero fotos**, e simplifica a Task A7).

- [ ] **Step 6: Descobrir `PG_BASE` sem imprimir a senha**

```bash
fly ssh console -a app2037 -C \
  "python3 -c \"import os,urllib.parse as u; p=u.urlparse(os.environ['CHATBOT_DATABASE_URL']); print(p.scheme, p.hostname, p.port, p.username, 'senha_len=', len(p.password or ''))\""
```

Esperado: algo como `postgresql suite-pg.flycast 5432 postgres senha_len= 32`. **Não** ecoar a URL inteira. O valor completo só será usado dentro do container, via `$CHATBOT_DATABASE_URL`, nos steps que criam os bancos.

- [ ] **Step 7: Criar os três bancos novos no `suite-pg`**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
url = os.environ[\"CHATBOT_DATABASE_URL\"]
with psycopg.connect(url, autocommit=True) as c:
    for nome in (\"portal\", \"revy_trafego\", \"catalogo\"):
        try:
            c.execute(f\"CREATE DATABASE {nome}\")
            print(\"criado:\", nome)
        except psycopg.errors.DuplicateDatabase:
            print(\"ja existia:\", nome)
"'
```

- [ ] **Step 8: Provar que os bancos existem**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"CHATBOT_DATABASE_URL\"]) as c:
    print(sorted(r[0] for r in c.execute(\"SELECT datname FROM pg_database WHERE datistemplate=false\")))
"'
```

Esperado: `['catalogo', 'chatbot', 'estoque', 'evolution', 'motor', 'portal', 'postgres', 'repmgr', 'revy_trafego']`.

**Gate:** nenhuma task seguinte começa sem (a) snapshot de hoje confirmado, (b) `integrity_check = ok` nos três `.db`, (c) os três bancos novos listados no Step 8.

---

### Task A2: Ferramenta de migração SQLite → Postgres

Uma ferramenta só, usada por A3, A4 e A6. Ela lê a **metadata declarada do produto** (não uma reflexão crua do SQLite), o que resolve de graça o problema de tipos: um `Boolean` gravado como `0`/`1` no SQLite volta como `False`/`True` porque a coluna é `Boolean` na metadata, e um `Numeric(12,2)` volta como `Decimal`.

**Files:**
- Create: `deploy/fly/3vm/migrar_sqlite_para_postgres.py`
- Test: `deploy/fly/3vm/tests/test_migrar_sqlite_para_postgres.py`

**Interfaces:**
- Produces: `copiar(metadata, origem_url, destino_url, *, lote=500) -> dict[str, int]` — devolve `{nome_da_tabela: linhas_copiadas}`. Consumida por A3, A4, A6.

- [ ] **Step 1: Escrever o teste que falha**

```python
# deploy/fly/3vm/tests/test_migrar_sqlite_para_postgres.py
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Column, MetaData, Numeric, String, Table, create_engine, select

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migrar_sqlite_para_postgres import copiar  # noqa: E402


def _metadata() -> MetaData:
    md = MetaData()
    Table(
        "vendas",
        md,
        Column("id", String(36), primary_key=True),
        Column("confirmada", Boolean, nullable=False),
        Column("valor", Numeric(12, 2), nullable=False),
    )
    return md


def test_copiar_preserva_tipos_e_conta_linhas(tmp_path):
    md = _metadata()
    origem = f"sqlite:///{tmp_path/'origem.db'}"
    destino = f"sqlite:///{tmp_path/'destino.db'}"

    e_origem = create_engine(origem)
    md.create_all(e_origem)
    with e_origem.begin() as c:
        c.execute(
            md.tables["vendas"].insert(),
            [
                {"id": "a", "confirmada": True, "valor": Decimal("1234.56")},
                {"id": "b", "confirmada": False, "valor": Decimal("0.10")},
            ],
        )

    e_destino = create_engine(destino)
    md.create_all(e_destino)

    assert copiar(md, origem, destino) == {"vendas": 2}

    with e_destino.connect() as c:
        linhas = sorted(c.execute(select(md.tables["vendas"])).all())
    assert linhas[0].confirmada is True
    assert linhas[1].confirmada is False
    assert linhas[0].valor == Decimal("1234.56")


def test_copiar_recusa_destino_com_linhas(tmp_path):
    md = _metadata()
    origem = f"sqlite:///{tmp_path/'origem.db'}"
    destino = f"sqlite:///{tmp_path/'destino.db'}"
    for url in (origem, destino):
        md.create_all(create_engine(url))
    with create_engine(destino).begin() as c:
        c.execute(md.tables["vendas"].insert(), {"id": "z", "confirmada": True, "valor": Decimal("1")})

    with pytest.raises(RuntimeError, match="destino já tem linhas em vendas"):
        copiar(md, origem, destino)


def test_copiar_ignora_tabela_ausente_na_origem(tmp_path):
    md = _metadata()
    origem = f"sqlite:///{tmp_path/'origem.db'}"
    destino = f"sqlite:///{tmp_path/'destino.db'}"
    create_engine(origem).connect().close()  # origem vazia, sem a tabela
    md.create_all(create_engine(destino))

    assert copiar(md, origem, destino) == {"vendas": 0}
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest ../deploy/fly/3vm/tests/test_migrar_sqlite_para_postgres.py -q
```

Esperado: `ModuleNotFoundError: No module named 'migrar_sqlite_para_postgres'`.

- [ ] **Step 3: Implementar**

```python
# deploy/fly/3vm/migrar_sqlite_para_postgres.py
"""Copia dados de um SQLite para um Postgres usando a metadata do produto.

Usar a metadata **declarada** (e não uma reflexão do SQLite) é o que faz os
tipos atravessarem: Boolean volta bool em vez de 0/1, Numeric volta Decimal
em vez de float, DateTime volta datetime em vez de string ISO.

O schema do destino NÃO é criado aqui — quem cria é o `alembic upgrade head`
do produto, para que a migration head continue sendo a fonte de verdade.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, inspect, select


def copiar(
    metadata: MetaData,
    origem_url: str,
    destino_url: str,
    *,
    lote: int = 500,
) -> dict[str, int]:
    """Copia todas as tabelas da metadata, em ordem de dependência.

    Recusa destino não vazio: reexecutar por engano duplicaria linhas em
    tabelas sem unique key natural. Tabela ausente na origem conta 0.
    """
    e_origem = create_engine(origem_url)
    e_destino = create_engine(destino_url)
    tabelas_origem = set(inspect(e_origem).get_table_names())
    resultado: dict[str, int] = {}

    with e_origem.connect() as origem, e_destino.begin() as destino:
        for tabela in metadata.sorted_tables:
            existentes = destino.execute(select(func.count()).select_from(tabela)).scalar_one()
            if existentes:
                raise RuntimeError(f"destino já tem linhas em {tabela.name} ({existentes})")

        for tabela in metadata.sorted_tables:
            if tabela.name not in tabelas_origem:
                resultado[tabela.name] = 0
                continue
            copiadas = 0
            cursor = origem.execution_options(stream_results=True).execute(select(tabela))
            while True:
                linhas = cursor.fetchmany(lote)
                if not linhas:
                    break
                destino.execute(tabela.insert(), [dict(l._mapping) for l in linhas])
                copiadas += len(linhas)
            resultado[tabela.name] = copiadas

    return resultado


def _metadata_do_produto(produto: Path) -> MetaData:
    """Importa app.db:Base e app.models a partir da pasta do produto."""
    sys.path.insert(0, str(produto))
    importlib.import_module("app.models")
    return importlib.import_module("app.db").Base.metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--produto", required=True, help="pasta do produto (ex.: portal-gestao)")
    parser.add_argument("--origem", required=True, help="URL SQLAlchemy do SQLite de origem")
    parser.add_argument("--destino", required=True, help="URL SQLAlchemy do Postgres de destino")
    args = parser.parse_args()

    metadata = _metadata_do_produto(Path(args.produto).resolve())
    resultado = copiar(metadata, args.origem, args.destino)
    total = 0
    for nome in sorted(resultado):
        print(f"{nome}: {resultado[nome]}")
        total += resultado[nome]
    print(f"TOTAL: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest ../deploy/fly/3vm/tests/test_migrar_sqlite_para_postgres.py -q
```

Esperado: `3 passed`.

- [ ] **Step 5: Garantir que a ferramenta entra na imagem do bundle**

`deploy/fly/3vm/Dockerfile.app` já copia `deploy/fly/3vm/` (README linha 255: "**Não** exclui o que o `Dockerfile.app` copia"). Confirmar:

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
rg -n "deploy/fly/3vm" deploy/fly/3vm/Dockerfile.app
```

Se a cópia for seletiva por arquivo, adicionar `migrar_sqlite_para_postgres.py` à lista. A pasta `tests/` nova **não** precisa ir para a imagem — o `.dockerignore` já exclui `tests/` (README linha 252).

- [ ] **Step 6: Commit**

```bash
git add deploy/fly/3vm/migrar_sqlite_para_postgres.py deploy/fly/3vm/tests/
git commit -m "feat(deploy): ferramenta de migracao sqlite->postgres por metadata do produto"
```

---

### Task A3: Portal → Postgres

**Files:**
- Modify: `deploy/fly/3vm/fly.app.toml:16` (remover `PORTAL_DATABASE_URL` do `[env]`)
- Modify: `deploy/fly/3vm/entrypoint-app.sh:27`
- Modify: `deploy/fly/3vm/run-portal.sh:3`
- Modify: `deploy/fly/3vm/run-revy-trafego.sh:5`

**Interfaces:**
- Consumes: `copiar(...)` da Task A2; `PG_BASE` da Task A1.

- [ ] **Step 1: Provar que as migrations do Portal sobem num Postgres limpo**

```bash
fly ssh console -a app2037 -C \
  "env DATABASE_URL=\"\${CHATBOT_DATABASE_URL%/*}/portal\" PORTAL_DATABASE_URL=\"\${CHATBOT_DATABASE_URL%/*}/portal\" sh -c 'cd /srv/portal && alembic upgrade head && alembic current'"
```

Esperado: as 16 migrations aplicam e `alembic current` imprime a head. **Se qualquer migration falhar aqui, pare** — é o sinal de que existe SQL SQLite-only não detectado na leitura estática, e o plano precisa de uma task de correção de migration antes de continuar.

- [ ] **Step 2: Parar só o processo do Portal**

```bash
fly ssh console -a app2037 -C "supervisorctl -c /etc/supervisord.conf stop portal revy-trafego"
```

O `revy-trafego` para junto porque `run-revy-trafego.sh:5` também exporta `PORTAL_DATABASE_URL` e ele será reapontado na Task A4. Chatbot, Estoque, Catálogo e nginx continuam no ar.

- [ ] **Step 3: Copiar os dados**

```bash
fly ssh console -a app2037 -C \
  "python3 /srv/scripts/migrar_sqlite_para_postgres.py \
     --produto /srv/portal \
     --origem sqlite:////data/portal/portal.db \
     --destino \"\${CHATBOT_DATABASE_URL%/*}/portal\""
```

Esperado: uma linha por tabela e um `TOTAL:`. Anotar o total — ele é o critério de aceite do Step 5.

- [ ] **Step 4: Fixar o secret e limpar os defaults SQLite do repo**

```bash
fly secrets set PORTAL_DATABASE_URL="postgresql://<user>:<senha>@suite-pg.flycast:5432/portal" -a app2037 --stage
```

`--stage` grava sem redeployar; o redeploy vem no Step 6 junto com as edições de arquivo. Montar a URL a partir do que o Step 6 da Task A1 revelou — **digitar no terminal local, nunca colar em arquivo versionado**.

Edições no repo:

`deploy/fly/3vm/fly.app.toml:16` — remover a linha inteira:

```toml
  PORTAL_DATABASE_URL = "sqlite:////data/portal/portal.db"
```

`deploy/fly/3vm/entrypoint-app.sh:27` — trocar por fail-fast:

```bash
if [ -z "${PORTAL_DATABASE_URL:-}" ]; then
  echo ">> ERRO: PORTAL_DATABASE_URL ausente. O Portal não roda mais em SQLite no volume." >&2
  exit 1
fi
```

`deploy/fly/3vm/run-portal.sh:3` — trocar por:

```sh
: "${PORTAL_DATABASE_URL:?PORTAL_DATABASE_URL ausente}"
```

`deploy/fly/3vm/run-revy-trafego.sh:5` — mesma troca:

```sh
: "${PORTAL_DATABASE_URL:?PORTAL_DATABASE_URL ausente}"
```

O ponto do fail-fast: com um default SQLite, uma machine que perca o secret sobe **funcionando** com um banco vazio e ninguém percebe. Sem default, ela morre no boot e o health check reprova — que é o comportamento correto.

- [ ] **Step 5: Deploy e conferir contagem no destino**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"PORTAL_DATABASE_URL\"]) as c:
    tabelas = [r[0] for r in c.execute(\"SELECT tablename FROM pg_tables WHERE schemaname=\x27public\x27 ORDER BY 1\")]
    total = 0
    for t in tabelas:
        n = c.execute(f\"SELECT count(*) FROM {t}\").fetchone()[0]
        total += n
        print(t, n)
    print(\"TOTAL:\", total)
"'
```

Esperado: `TOTAL` **igual** ao do Step 3, mais as linhas de `alembic_version`.

- [ ] **Step 6: Smoke funcional do Portal**

```bash
curl -sS -o /dev/null -w "healthz=%{http_code}\n" https://app2037.fly.dev/healthz
curl -sS -o /dev/null -w "login=%{http_code}\n"  https://app2037.fly.dev/login
```

Esperado: `healthz=200` (o health agregado exige 2xx de Chatbot, Estoque, Portal e Revy — README linha 51) e `login=200`. Depois, login manual pela UI e conferência de que a listagem de vendas mostra os mesmos registros de antes.

- [ ] **Step 7: Rodar a suíte do Portal**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest -q
```

Esperado: `471 passed`. Os testes usam SQLite em memória via conftest; esta task não deve mexer nisso.

- [ ] **Step 8: Commit**

```bash
git add deploy/fly/3vm/fly.app.toml deploy/fly/3vm/entrypoint-app.sh \
        deploy/fly/3vm/run-portal.sh deploy/fly/3vm/run-revy-trafego.sh
git commit -m "feat(deploy): portal sai do sqlite do volume para o suite-pg"
```

**Rollback:** `fly secrets unset PORTAL_DATABASE_URL -a app2037` + `git revert` do commit. O `/data/portal/portal.db` **não foi apagado** e volta a ser usado pelo default restaurado. O Postgres `portal` fica lá, inerte.

**Gate:** não seguir para A4 sem o `TOTAL` do Step 5 batendo com o do Step 3 e o `healthz=200`.

---

### Task A4: Revy Tráfego → Postgres

**Files:**
- Modify: `deploy/fly/3vm/fly.app.toml:31` (remover `REVY_TRAFEGO_DATABASE_URL` do `[env]`)
- Modify: `deploy/fly/3vm/entrypoint-app.sh:34`
- Modify: `deploy/fly/3vm/run-revy-trafego.sh:3`

**Interfaces:**
- Consumes: `copiar(...)` da Task A2; `PG_BASE` da Task A1.

- [ ] **Step 1: Provar as 14 migrations do Revy num Postgres limpo**

```bash
fly ssh console -a app2037 -C \
  "env REVY_TRAFEGO_DATABASE_URL=\"\${CHATBOT_DATABASE_URL%/*}/revy_trafego\" sh -c 'cd /srv/revy-trafego && alembic upgrade head && alembic current'"
```

Esperado: head aplicada. **Ponto de atenção específico:** as migrations `0002_revy_control_lojas_rbac.py:87,95`, `0003_revy_control_pessoas_cargos.py:77,85` e `0007_revy_control_portfolio.py:172` criam índices únicos **parciais**. Elas têm `postgresql_where` além do `sqlite_where`, então devem virar `CREATE UNIQUE INDEX ... WHERE ...` de verdade. Confirmar:

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
url = os.environ[\"CHATBOT_DATABASE_URL\"].rsplit(\"/\",1)[0] + \"/revy_trafego\"
with psycopg.connect(url) as c:
    for r in c.execute(\"SELECT indexname, indexdef FROM pg_indexes WHERE indexdef ILIKE \x27%WHERE%\x27 ORDER BY 1\"):
        print(r[0], \"|\", r[1])
"'
```

Esperado: **5** índices com cláusula `WHERE`. Se vierem menos de 5, um `postgresql_where` está faltando e a unicidade ficou mais restritiva do que o domínio permite — parar e corrigir a migration antes de copiar dados.

- [ ] **Step 2: Parar o processo do Revy**

```bash
fly ssh console -a app2037 -C "supervisorctl -c /etc/supervisord.conf stop revy-trafego"
```

- [ ] **Step 3: Copiar os dados**

```bash
fly ssh console -a app2037 -C \
  "python3 /srv/scripts/migrar_sqlite_para_postgres.py \
     --produto /srv/revy-trafego \
     --origem sqlite:////data/revy-trafego/revy_trafego.db \
     --destino \"\${CHATBOT_DATABASE_URL%/*}/revy_trafego\""
```

Anotar o `TOTAL:`.

- [ ] **Step 4: Secret e limpeza dos defaults**

```bash
fly secrets set REVY_TRAFEGO_DATABASE_URL="postgresql://<user>:<senha>@suite-pg.flycast:5432/revy_trafego" -a app2037 --stage
```

`deploy/fly/3vm/fly.app.toml:31` — remover a linha:

```toml
  REVY_TRAFEGO_DATABASE_URL = "sqlite:////data/revy-trafego/revy_trafego.db"
```

`deploy/fly/3vm/entrypoint-app.sh:34` — trocar por:

```bash
if [ -z "${REVY_TRAFEGO_DATABASE_URL:-}" ]; then
  echo ">> ERRO: REVY_TRAFEGO_DATABASE_URL ausente. O Revy Tráfego não roda mais em SQLite no volume." >&2
  exit 1
fi
```

`deploy/fly/3vm/run-revy-trafego.sh:3` — trocar por:

```sh
: "${REVY_TRAFEGO_DATABASE_URL:?REVY_TRAFEGO_DATABASE_URL ausente}"
```

- [ ] **Step 5: Deploy e conferir contagem**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"REVY_TRAFEGO_DATABASE_URL\"]) as c:
    total = 0
    for (t,) in c.execute(\"SELECT tablename FROM pg_tables WHERE schemaname=\x27public\x27 ORDER BY 1\").fetchall():
        n = c.execute(f\"SELECT count(*) FROM {t}\").fetchone()[0]
        total += n
        print(t, n)
    print(\"TOTAL:\", total)
"'
```

Esperado: `TOTAL` igual ao do Step 3 + `alembic_version_revy_trafego`.

- [ ] **Step 6: Smoke do Revy e do fluxo Portal→Revy**

```bash
curl -sS -o /dev/null -w "revy_ready=%{http_code}\n" https://app2037.fly.dev/trafego/health/ready
curl -sS -o /dev/null -w "healthz=%{http_code}\n"    https://app2037.fly.dev/healthz
```

Esperado: `200` nos dois. Depois, na UI: `/trafego` lista as campanhas e o ROI da loja `moto-center` com os mesmos números de antes da migração.

- [ ] **Step 7: Rodar a suíte do Revy**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/revy-trafego
.venv/bin/python -m pytest -q
```

Esperado: `361 passed, 1 failed` — e o único `failed` é `test_process_pending_falha_marca_failed_e_incrementa_attempts`. Qualquer outra falha é regressão desta task.

- [ ] **Step 8: Commit**

```bash
git add deploy/fly/3vm/fly.app.toml deploy/fly/3vm/entrypoint-app.sh deploy/fly/3vm/run-revy-trafego.sh
git commit -m "feat(deploy): revy trafego sai do sqlite do volume para o suite-pg"
```

**Rollback:** idêntico ao da A3, trocando o nome do secret. O `/data/revy-trafego/revy_trafego.db` permanece intacto.

---

### Task A5: Catálogo — trocar `sqlite3` cru por SQLAlchemy + Alembic

Esta task **não muda comportamento nem banco**: ao terminar, o Catálogo continua rodando em SQLite, no mesmo arquivo, com os mesmos 53 testes verdes. Ela só troca a camada de acesso, para que a Task A6 vire uma troca de URL. Separar as duas é o que torna o port revisável: se A5 quebrar algo, dá para revisar sem a migração de dados no caminho.

**Files:**
- Create: `catalogo-publico/app/db.py`
- Create: `catalogo-publico/app/models.py`
- Create: `catalogo-publico/alembic.ini`, `catalogo-publico/alembic/env.py`, `catalogo-publico/alembic/script.py.mako`, `catalogo-publico/alembic/versions/0001_schema_inicial.py`
- Modify: `catalogo-publico/app/events.py` (substitui `sqlite3` por SQLAlchemy Core, preservando a API pública de `InterestStore`)
- Modify: `catalogo-publico/app/provisioning.py` (idem para `ProvisioningStore`)
- Modify: `catalogo-publico/app/config.py:14,18`
- Modify: `catalogo-publico/requirements.txt`
- Test: `catalogo-publico/tests/test_provisioning.py`, `catalogo-publico/tests/test_outbox.py` (existentes — são o contrato)

**Interfaces:**
- Produces: `catalogo-publico/app/db.py` expondo `engine`, `Base`, `SessionLocal`, `criar_engine(url: str)`; `app.config.settings.database_url: str` (nova, derivada de `CATALOGO_DATABASE_URL` com fallback para `CATALOGO_DATABASE_PATH`). Consumidas pela Task A6 e pela Task B3.
- A API pública de `InterestStore` e `ProvisioningStore` **não muda**: `initialize()`, `pending_outbox(now=...)`, `mark_delivered(event_id, status, instant)`, `get_interest(event_id)`, `count()`, e os métodos de `ProvisioningStore` usados em `catalogo-publico/app/main.py`.

- [ ] **Step 1: Registrar a superfície exata que precisa sobreviver**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
rg -n "interest_store\.|provisioning_store\." catalogo-publico/app/ catalogo-publico/tests/ | sort -u
```

Colar a saída em `$SCRATCH/escala-app2037/catalogo-api.txt`. Cada método listado ali precisa existir com a mesma assinatura no fim da task. Este arquivo é o critério de "não quebrei nada".

- [ ] **Step 2: Adicionar as dependências**

`catalogo-publico/requirements.txt` — acrescentar, alinhado com os outros produtos:

```
sqlalchemy==2.*
alembic==1.14.*
psycopg[binary]==3.*
```

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Criar o venv aqui é intencional: os outros produtos já têm, e sem ele não dá para rodar a suíte de forma reprodutível.

- [ ] **Step 3: Rodar a suíte antes de tocar em qualquer coisa (baseline)**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
.venv/bin/python -m pytest -q
```

Esperado: `53 passed`. Se não der 53, parar — a baseline mudou e o critério de aceite desta task é inválido.

- [ ] **Step 4: Criar `app/db.py`**

```python
# catalogo-publico/app/db.py
"""Engine único do Catálogo. URL vem do ambiente; SQLite continua suportado."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

Base = declarative_base()


def criar_engine(url: str):
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    return create_engine(url, future=True, **kwargs)


engine = criar_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

- [ ] **Step 5: Criar `app/models.py` com as 3 tabelas atuais**

Transcrição literal do DDL vigente: `catalogo-publico/app/events.py:43-108` e `catalogo-publico/app/provisioning.py:41-56`. Duas armadilhas: (a) `interest_events` tem quatro colunas que **não** estão no `CREATE TABLE` — `fbclid`, `gclid`, `gbraid`, `wbraid` entram por `ALTER TABLE` em `events.py:62-72` e precisam estar no modelo; (b) `event_id` e `public_ref` também aparecem naquela lista de `ALTER TABLE`, o que significa que existem bancos antigos onde elas são `NULL` — tratado no Step 5b.

Todo timestamp é `TEXT` no SQLite (ISO 8601 gravado como string). **Manter `Text`, não converter para `DateTime`** — converter mudaria o formato de serialização e quebraria comparações como `next_attempt_at <= ?`, que hoje são lexicográficas sobre ISO. Trocar de tipo é refactor de comportamento e não cabe nesta task.

```python
# catalogo-publico/app/models.py
"""Tabelas do Catálogo. Nomes, tipos e índices iguais ao DDL sqlite3 anterior.

Timestamps continuam TEXT/ISO: a comparação lexicográfica sobre ISO 8601 é o
que `pending_outbox` já usa. Converter para DateTime aqui mudaria semântica.
"""
from __future__ import annotations

from sqlalchemy import Column, Index, Integer, Text

from app.db import Base


class InterestEvent(Base):
    __tablename__ = "interest_events"

    id = Column(Text, primary_key=True)
    event_id = Column(Text, nullable=False, unique=True)
    public_ref = Column(Text, nullable=False, unique=True)
    loja_slug = Column(Text, nullable=False)
    veiculo_id = Column(Text, nullable=False)
    ocorrido_em = Column(Text, nullable=False)
    origem = Column(Text)
    utm_source = Column(Text)
    utm_medium = Column(Text)
    utm_campaign = Column(Text)
    utm_content = Column(Text)
    utm_term = Column(Text)
    visitante_id = Column(Text, nullable=False)
    # Adicionadas por ALTER TABLE em events.py:62-72 — nullable por origem.
    fbclid = Column(Text)
    gclid = Column(Text)
    gbraid = Column(Text)
    wbraid = Column(Text)

    __table_args__ = (
        Index("uq_interest_event_id", "event_id", unique=True),
        Index("uq_interest_public_ref", "public_ref", unique=True),
        Index("ix_interest_store_time", "loja_slug", "ocorrido_em"),
    )


class EventOutbox(Base):
    __tablename__ = "event_outbox"

    event_id = Column(Text, primary_key=True)
    event_type = Column(Text, nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    next_attempt_at = Column(Text)
    last_error = Column(Text)
    last_http_status = Column(Integer)
    delivered_at = Column(Text)
    created_at = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_event_outbox_pending", "status", "next_attempt_at", "created_at"),
    )


class LojaOperacionalProjecao(Base):
    __tablename__ = "loja_operacional_projecao"

    loja_slug = Column(Text, primary_key=True)
    aggregate = Column(Text, primary_key=True)
    version = Column(Integer, nullable=False)
    state = Column(Text, nullable=False)
    event_id = Column(Text, nullable=False, server_default="")
    atualizado_em = Column(Text, nullable=False)

    __table_args__ = (Index("ix_proj_slug", "loja_slug"),)
```

Os cinco nomes de índice (`uq_interest_event_id`, `uq_interest_public_ref`, `ix_interest_store_time`, `ix_event_outbox_pending`, `ix_proj_slug`) são exatamente os que já existem no SQLite — mantê-los evita que o Alembic proponha recriar tudo e mantém a comparação do Step 7 limpa.

- [ ] **Step 5b: Preservar o backfill de linhas legadas**

`events.py:73-80` faz, a cada `initialize()`, um backfill: linhas com `event_id IS NULL` ou `public_ref IS NULL` ganham um UUID e uma referência pública novos. Com o schema virando responsabilidade do Alembic, esse backfill some do código — e a migration `0001` declara as duas colunas `NOT NULL UNIQUE`, então um banco legado com nulos **falharia** ao migrar.

Acrescentar à migration `0001_schema_inicial.py`, **antes** dos `create_index` únicos:

```python
def upgrade() -> None:
    # ... op.create_table(...) gerado pelo autogenerate ...

    # Bancos anteriores ao event_id/public_ref têm linhas com esses campos
    # nulos (o backfill vivia em events.py:73-80, que esta migration substitui).
    conexao = op.get_bind()
    legado = conexao.execute(
        sa.text("SELECT id FROM interest_events WHERE event_id IS NULL OR public_ref IS NULL")
    ).fetchall()
    for (identificador,) in legado:
        conexao.execute(
            sa.text("UPDATE interest_events SET event_id = :e, public_ref = :p WHERE id = :i"),
            {"e": str(uuid.uuid4()), "p": _public_reference(), "i": identificador},
        )

    # ... op.create_index(...) dos índices únicos ...
```

`_public_reference` é a função já existente em `catalogo-publico/app/events.py` — importá-la na migration (`from app.events import _public_reference`) mantém o formato da referência idêntico ao histórico.

- [ ] **Step 6: Criar o tree do Alembic**

Copiar a estrutura do produto vizinho como referência de estilo e adaptar:

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
.venv/bin/python -m alembic init alembic
```

`catalogo-publico/alembic/env.py` — reescrever seguindo `revy-trafego/alembic/env.py`, com `version_table` próprio para o Catálogo não colidir se um dia dividir schema:

```python
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base
from app import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
VERSION_TABLE = "alembic_version_catalogo"


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Gerar a migration inicial e conferir que ela reproduz o schema atual:

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
CATALOGO_DATABASE_PATH=/tmp/catalogo-vazio.db .venv/bin/python -m alembic revision --autogenerate -m "schema inicial"
mv alembic/versions/*_schema_inicial.py alembic/versions/0001_schema_inicial.py
```

- [ ] **Step 7: Provar que a migration reproduz o schema legado, byte a byte**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
rm -f /tmp/cat-legado.db /tmp/cat-novo.db
CATALOGO_DATABASE_PATH=/tmp/cat-legado.db .venv/bin/python -c \
  "from app.events import InterestStore; from app.provisioning import ProvisioningStore; \
   InterestStore('/tmp/cat-legado.db').initialize(); ProvisioningStore('/tmp/cat-legado.db').initialize()"
CATALOGO_DATABASE_PATH=/tmp/cat-novo.db .venv/bin/python -m alembic upgrade head
for db in /tmp/cat-legado.db /tmp/cat-novo.db; do
  echo "== $db"
  sqlite3 "$db" "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%' ORDER BY name;"
done
```

Rodar **antes** de mexer em `events.py`/`provisioning.py` — é o Gate que diz se `models.py` foi transcrito certo. Diferenças de espaçamento em `sql` são aceitáveis; diferença em nome de coluna, tipo, nullability ou índice **não é**.

- [ ] **Step 8: Reescrever `events.py` mantendo a API pública**

Substituir cada `db.execute("SELECT ... WHERE x = ?", (v,))` pela consulta SQLAlchemy Core equivalente sobre `models.InterestEvent` / `models.EventOutbox`, com `SessionLocal()` ou `engine.begin()`. Regras de tradução:

| Padrão sqlite3 | Substituto |
|---|---|
| `sqlite3.connect(path, timeout=5)` | `db.engine.begin()` (escrita) / `db.engine.connect()` (leitura) |
| `?` posicional | parâmetros nomeados do Core |
| `INSERT INTO t (...) VALUES (?, ...)` (3 ocorrências: `events.py:166`, `events.py:194`, `provisioning.py:155`) | `insert(T).values(...)` — são inserts simples, sem `OR IGNORE`/`ON CONFLICT`, então a tradução é direta e neutra de dialeto |
| `PRAGMA table_info(interest_events)` + `ALTER TABLE` (`events.py:60-72`) | **remover**. O schema passa a ser responsabilidade da migration `0001` |
| `sqlite3.Row` no retorno de `get_interest` | `Row` do SQLAlchemy — acesso por atributo funciona igual; conferir se algum call site usa `row["chave"]` e ajustar |
| `except sqlite3.Error` (`events.py:118`) | `except SQLAlchemyError` |

`initialize()` continua existindo e vira idempotente sem DDL: só valida a conexão (`engine.connect()`), porque quem cria tabela agora é o Alembic.

- [ ] **Step 9: Reescrever `provisioning.py` com as mesmas regras**

`provisioning.py` tem 6 `execute` (linhas 40, 53, 62, 130, 143, 155) e 5 placeholders `?`. O `_connect()` (linhas 31-36) some; `initialize()` (linha 39) deixa de emitir `CREATE TABLE`/`CREATE INDEX` e passa a só validar a conexão.

**Manter a semântica de `apply` intacta.** `provisioning.py:130-160` é um read-then-write: `SELECT version, state` → decide entre `stale`, `idempotent`, `UPDATE` ou `INSERT`. Traduzir para `session.get(LojaOperacionalProjecao, (loja_slug, aggregate))` seguido do mesmo `if`, dentro de **uma** transação. Os três retornos (`"stale"`, `"idempotent"`, `"applied"`) são contrato com `catalogo-publico/app/main.py` e com `tests/test_provisioning.py` — não mudar nenhum.

**Anotar, não corrigir aqui:** esse read-then-write é uma corrida se duas entregas do mesmo agregado chegarem em paralelo. Hoje isso não acontece porque o outbox de provisionamento do Control entrega em série, e a Task B2 põe esse outbox sob advisory lock. Registrar em `$SCRATCH/escala-app2037/pendencias.txt` como candidato a `SELECT ... FOR UPDATE`; **não é escopo desta task** e mexer nele aqui misturaria refactor com mudança de comportamento.

- [ ] **Step 10: Rodar a suíte inteira**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
.venv/bin/python -m pytest -q
```

Esperado: `53 passed`. Se algum teste precisar de mudança, a mudança permitida é **só** de setup (criar o schema via `Base.metadata.create_all` ou `alembic upgrade head` em vez de `initialize()`); mudar uma asserção de comportamento significa que o port alterou semântica e precisa voltar.

- [ ] **Step 11: Conferir que a superfície do Step 1 continua completa**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
rg -n "interest_store\.|provisioning_store\." catalogo-publico/app/ catalogo-publico/tests/ | sort -u > /tmp/catalogo-api-depois.txt
diff "$SCRATCH/escala-app2037/catalogo-api.txt" /tmp/catalogo-api-depois.txt && echo "API preservada"
```

- [ ] **Step 12: Commit**

```bash
git add catalogo-publico/
git commit -m "refactor(catalogo): troca sqlite3 cru por sqlalchemy + alembic sem mudar comportamento"
```

---

### Task A6: Catálogo → Postgres

**Files:**
- Modify: `catalogo-publico/app/config.py` (adicionar `CATALOGO_DATABASE_URL`)
- Modify: `deploy/fly/3vm/fly.app.toml:17` (remover `CATALOGO_DATABASE_PATH`)
- Modify: `deploy/fly/3vm/entrypoint-app.sh:28` e o bloco de `run_alembic`
- Modify: `deploy/fly/3vm/run-catalogo.sh:3,11`

**Interfaces:**
- Consumes: `copiar(...)` da Task A2; `app.db.Base.metadata` da Task A5.

- [ ] **Step 1: Aceitar uma URL completa na config**

`catalogo-publico/app/config.py` — substituir o par `database_path` por uma URL, mantendo compatibilidade com o path antigo para que os 53 testes e o dev local não quebrem:

```python
def _database_url() -> str:
    url = (os.getenv("CATALOGO_DATABASE_URL") or "").strip()
    if url:
        return url
    caminho = os.getenv("CATALOGO_DATABASE_PATH", "data/catalogo.db")
    return f"sqlite:///{caminho}"
```

e expor `database_url: str = _database_url()` no `settings`. Manter `database_path` como está para não quebrar chamador algum ainda não migrado.

- [ ] **Step 2: Rodar a suíte para provar que a compatibilidade se sustenta**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
.venv/bin/python -m pytest -q
```

Esperado: `53 passed`.

- [ ] **Step 3: Adicionar o Catálogo ao Alembic do entrypoint**

`deploy/fly/3vm/entrypoint-app.sh` — depois do bloco do Revy (linha 66-69), acrescentar:

```bash
if [ -z "${CATALOGO_DATABASE_URL:-}" ]; then
  echo ">> ERRO: CATALOGO_DATABASE_URL ausente. O Catálogo não roda mais em SQLite no volume." >&2
  exit 1
fi
export DATABASE_URL="$CATALOGO_DATABASE_URL"
run_alembic /srv/catalogo
```

`run_alembic` exige `alembic.ini` na pasta (linha 41) — a Task A5 criou. Conferir que o `Dockerfile.app` copia `catalogo-publico/alembic/` para `/srv/catalogo`:

```bash
rg -n "catalogo" deploy/fly/3vm/Dockerfile.app
```

Se copiar só `catalogo-publico/app`, adicionar `alembic/` e `alembic.ini` — sem isso o boot falha em `>> ERRO: alembic.ini ausente`.

- [ ] **Step 4: Parar o Catálogo e migrar o schema**

```bash
fly ssh console -a app2037 -C "supervisorctl -c /etc/supervisord.conf stop catalogo"
fly ssh console -a app2037 -C \
  "env CATALOGO_DATABASE_URL=\"\${CHATBOT_DATABASE_URL%/*}/catalogo\" sh -c 'cd /srv/catalogo && alembic upgrade head && alembic current'"
```

- [ ] **Step 5: Copiar os dados**

```bash
fly ssh console -a app2037 -C \
  "python3 /srv/scripts/migrar_sqlite_para_postgres.py \
     --produto /srv/catalogo \
     --origem sqlite:////data/catalogo/catalogo.db \
     --destino \"\${CHATBOT_DATABASE_URL%/*}/catalogo\""
```

Esperado: `interest_events`, `event_outbox` e `loja_operacional_projecao` com as contagens do SQLite. Comparar com a origem:

```bash
for t in interest_events event_outbox loja_operacional_projecao; do
  echo -n "$t origem: "; sqlite3 "$SCRATCH/escala-app2037/catalogo.db" "SELECT count(*) FROM $t;"
done
```

- [ ] **Step 6: Secret, env e cutover**

```bash
fly secrets set CATALOGO_DATABASE_URL="postgresql://<user>:<senha>@suite-pg.flycast:5432/catalogo" -a app2037 --stage
```

`deploy/fly/3vm/fly.app.toml:17` — remover:

```toml
  CATALOGO_DATABASE_PATH = "/data/catalogo/catalogo.db"
```

`deploy/fly/3vm/run-catalogo.sh` — trocar a linha 3 e remover o `mkdir` da linha 11:

```sh
: "${CATALOGO_DATABASE_URL:?CATALOGO_DATABASE_URL ausente}"
```

`deploy/fly/3vm/entrypoint-app.sh:28` — remover o `export CATALOGO_DATABASE_PATH`, já substituído no Step 3.

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

- [ ] **Step 7: Smoke da vitrine**

```bash
curl -sS -o /dev/null -w "vitrine=%{http_code}\n" https://app2037.fly.dev/loja/
curl -sS -o /dev/null -w "healthz=%{http_code}\n" https://app2037.fly.dev/healthz
```

Esperado: `200` nos dois, e a vitrine listando os veículos publicados com o Pixel resolvido (o Pixel vem do Revy Tráfego por HTTP, não do banco do Catálogo — não deve ter regredido).

- [ ] **Step 8: Commit**

```bash
git add catalogo-publico/app/config.py deploy/fly/3vm/
git commit -m "feat(catalogo): banco vai para o suite-pg e sai do volume local"
```

**Rollback:** `fly secrets unset CATALOGO_DATABASE_URL -a app2037` + `git revert`. O `/data/catalogo/catalogo.db` continua no volume e volta a valer pelo fallback `CATALOGO_DATABASE_PATH`.

---

### Task A7: Mídia do Estoque → Tigris

**Files:**
- Modify: `estoque-api/app/config.py:37-38`
- Modify: `estoque-api/app/media.py` (backend plugável)
- Modify: `estoque-api/app/main.py:569-577` (servir bytes em vez de `FileResponse`)
- Modify: `estoque-api/requirements.txt`, `deploy/fly/3vm/requirements-app.txt`
- Modify: `deploy/fly/3vm/fly.app.toml:63`, `deploy/fly/3vm/entrypoint-app.sh:35`
- Test: `estoque-api/tests/test_media.py`

**Interfaces:**
- Produces: `media.salvar(storage_key, conteudo) -> tuple[str, bool]` — a assinatura muda de `tuple[Path, bool]` para `tuple[str, bool]` (a storage key em vez do caminho local). `media.remover_se_novo(chave: str, criado: bool)` e `media.ler(storage_key) -> tuple[bytes, str]` substituem `resolver_publica`. Consumidas por `estoque-api/app/main.py`.

- [ ] **Step 1: Decidir se a mídia existe**

```bash
tar tzf "$SCRATCH/escala-app2037/media.tar.gz" | grep -c '\.\(jpg\|png\|webp\)$' || true
```

Se der `0`, a migração de arquivos do Step 8 é um no-op e a task encurta — mas o código do backend continua necessário, porque uma foto nova enviada depois do `scale count` iria para o disco de uma machine só.

- [ ] **Step 2: Criar o bucket Tigris**

```bash
fly storage create --name revy-estoque-media -a app2037
fly secrets list -a app2037 | grep -E "AWS_|BUCKET_NAME"
```

Esperado: `fly storage create` cria o bucket e injeta como secrets no app: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_ENDPOINT_URL_S3`, `BUCKET_NAME`. **Gate:** se `fly storage create` não existir nesta versão do flyctl ou a extensão Tigris não estiver disponível no org, parar e reportar — a alternativa (um bucket S3/R2 externo com as mesmas 5 variáveis) muda só a origem dos secrets, não o código, mas é decisão do owner.

- [ ] **Step 3: Escrever o teste do backend antes do backend**

```python
# estoque-api/tests/test_media.py  (acrescentar)
import pytest

from app import config, media


def test_backend_local_salva_le_e_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(media, "_backend", media.BackendLocal(tmp_path))

    chave = "moto-center/veic-1/" + "a" * 32 + ".jpg"
    devolvida, criado = media.salvar(chave, b"\xff\xd8\xffconteudo")
    assert (devolvida, criado) == (chave, True)

    devolvida, criado = media.salvar(chave, b"\xff\xd8\xffconteudo")
    assert criado is False

    conteudo, mime = media.ler(chave)
    assert conteudo == b"\xff\xd8\xffconteudo"
    assert mime == "image/jpeg"


def test_salvar_mesma_chave_com_conteudo_diferente_da_409(tmp_path, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(config, "MEDIA_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(media, "_backend", media.BackendLocal(tmp_path))

    chave = "moto-center/veic-1/" + "b" * 32 + ".jpg"
    media.salvar(chave, b"\xff\xd8\xffum")
    with pytest.raises(HTTPException) as erro:
        media.salvar(chave, b"\xff\xd8\xffoutro")
    assert erro.value.status_code == 409


def test_ler_chave_inexistente_da_404():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as erro:
        media.ler("moto-center/veic-1/" + "c" * 32 + ".jpg")
    assert erro.value.status_code == 404
```

- [ ] **Step 4: Rodar e ver falhar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/estoque-api
python -m pytest tests/test_media.py -q
```

Esperado: `AttributeError: module 'app.media' has no attribute 'BackendLocal'`.

- [ ] **Step 5: Implementar os dois backends em `media.py`**

Manter `gerar_storage_key`, `normalizar_mime_imagem`, `validar_assinatura` e a validação de `caminho_seguro` (que passa a validar **formato de chave**, não caminho de disco). Acrescentar:

```python
class BackendLocal:
    """Disco local. Continua sendo o default em dev e nos testes."""

    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)

    def _caminho(self, storage_key: str) -> Path:
        validar_storage_key(storage_key)
        return self.raiz.joinpath(*storage_key.split("/"))

    def ler(self, storage_key: str) -> bytes | None:
        caminho = self._caminho(storage_key)
        return caminho.read_bytes() if caminho.is_file() else None

    def gravar_se_novo(self, storage_key: str, conteudo: bytes) -> bool:
        destino = self._caminho(storage_key)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".upload-", delete=False) as arquivo:
                temporario = arquivo.name
                arquivo.write(conteudo)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.chmod(temporario, 0o640)
            try:
                os.link(temporario, destino)
            except FileExistsError:
                return False
        finally:
            if temporario and os.path.exists(temporario):
                os.unlink(temporario)
        return True

    def remover(self, storage_key: str) -> None:
        self._caminho(storage_key).unlink(missing_ok=True)


class BackendS3:
    """Tigris (ou qualquer S3). Compartilhado entre todas as machines."""

    def __init__(self, bucket: str, endpoint: str, region: str):
        import boto3

        self.bucket = bucket
        self.cliente = boto3.client("s3", endpoint_url=endpoint, region_name=region)

    def ler(self, storage_key: str) -> bytes | None:
        validar_storage_key(storage_key)
        try:
            return self.cliente.get_object(Bucket=self.bucket, Key=storage_key)["Body"].read()
        except self.cliente.exceptions.NoSuchKey:
            return None

    def gravar_se_novo(self, storage_key: str, conteudo: bytes) -> bool:
        validar_storage_key(storage_key)
        # IfNoneMatch="*" faz o próprio S3 recusar sobrescrita concorrente,
        # que é o papel que o os.link tinha no backend local.
        try:
            self.cliente.put_object(
                Bucket=self.bucket, Key=storage_key, Body=conteudo, IfNoneMatch="*"
            )
        except self.cliente.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] in ("PreconditionFailed", "412"):
                return False
            raise
        return True

    def remover(self, storage_key: str) -> None:
        validar_storage_key(storage_key)
        self.cliente.delete_object(Bucket=self.bucket, Key=storage_key)


def _escolher_backend():
    if config.MEDIA_BUCKET:
        return BackendS3(config.MEDIA_BUCKET, config.MEDIA_S3_ENDPOINT, config.MEDIA_S3_REGION)
    return BackendLocal(config.MEDIA_STORAGE_DIR)


_backend = _escolher_backend()


def salvar(storage_key: str, conteudo: bytes) -> tuple[str, bool]:
    """Grava se novo. Se a chave já existe com conteúdo diferente, 409."""
    if _backend.gravar_se_novo(storage_key, conteudo):
        return storage_key, True
    existente = _backend.ler(storage_key)
    if existente != conteudo:
        raise HTTPException(status_code=409, detail="chave de mídia já utilizada")
    return storage_key, False


def ler(storage_key: str) -> tuple[bytes, str]:
    conteudo = _backend.ler(storage_key)
    if conteudo is None:
        raise HTTPException(status_code=404, detail="mídia não encontrada")
    extensao = storage_key.rsplit(".", 1)[-1]
    return conteudo, _MIME_POR_EXTENSAO[extensao]


def remover_se_novo(storage_key: str, criado: bool) -> None:
    if criado:
        _backend.remover(storage_key)
```

`validar_storage_key(chave)` é o `caminho_seguro` atual (`media.py:70-84`) sem a parte de `Path`: mantém os três `re.fullmatch` e levanta 404 se a chave não casar. Isso preserva a defesa contra path traversal — que continua importando, porque a chave vira Key do S3.

`config.py` — acrescentar ao lado de `MEDIA_STORAGE_DIR`:

```python
MEDIA_BUCKET = os.getenv("BUCKET_NAME", "").strip()
MEDIA_S3_ENDPOINT = os.getenv("AWS_ENDPOINT_URL_S3", "").strip()
MEDIA_S3_REGION = os.getenv("AWS_REGION", "auto").strip()
```

- [ ] **Step 6: Ajustar os dois call sites em `main.py`**

`estoque-api/app/main.py:368,384` — `caminho, criado = media.salvar(...)` vira `chave, criado = media.salvar(...)`, e `media.remover_se_novo(caminho, criado)` vira `media.remover_se_novo(chave, criado)`.

`estoque-api/app/main.py:567-577` — trocar `FileResponse` por `Response`, preservando os headers atuais:

```python
@app.get("/public/v1/media/{loja_id}/{veiculo_id}/{arquivo}")
def media_publica(loja_id: str, veiculo_id: str, arquivo: str):
    conteudo, content_type = media.ler(f"{loja_id}/{veiculo_id}/{arquivo}")
    return Response(
        content=conteudo,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
```

A URL pública **não muda** — é o que preserva as URLs já gravadas nas linhas de veículo e o `ESTOQUE_MEDIA_ALLOWED_HOSTS` do `fly.app.toml:66`.

- [ ] **Step 7: Rodar as suítes do Estoque e do Chatbot**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/estoque-api && python -m pytest -q
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/chatbot-api && python -m pytest -q
```

Esperado: Estoque verde; Chatbot `246 passed` — ele é o consumidor que envia fotos do WhatsApp (`chatbot-api/app/vehicle_photo.py:199`) e não deve ter regredido.

- [ ] **Step 8: Adicionar `boto3` e subir os arquivos existentes**

`estoque-api/requirements.txt` e `deploy/fly/3vm/requirements-app.txt` — acrescentar `boto3==1.35.*`.

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C 'python3 -c "
import os, boto3
from pathlib import Path
cliente = boto3.client(\"s3\", endpoint_url=os.environ[\"AWS_ENDPOINT_URL_S3\"], region_name=os.environ.get(\"AWS_REGION\",\"auto\"))
raiz = Path(\"/data/estoque/media\")
n = 0
for arquivo in raiz.rglob(\"*\"):
    if arquivo.is_file():
        cliente.upload_file(str(arquivo), os.environ[\"BUCKET_NAME\"], str(arquivo.relative_to(raiz)))
        n += 1
print(\"enviados:\", n)
"'
```

- [ ] **Step 9: Provar que o bucket tem o mesmo número de objetos**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, boto3
cliente = boto3.client(\"s3\", endpoint_url=os.environ[\"AWS_ENDPOINT_URL_S3\"], region_name=os.environ.get(\"AWS_REGION\",\"auto\"))
p = cliente.get_paginator(\"list_objects_v2\")
print(\"objetos:\", sum(len(pg.get(\"Contents\", [])) for pg in p.paginate(Bucket=os.environ[\"BUCKET_NAME\"])))
"'
fly ssh console -a app2037 -C "find /data/estoque/media -type f | wc -l"
```

Esperado: os dois números iguais.

- [ ] **Step 10: Smoke de uma foto real pela URL pública**

Pegar uma URL de foto de um veículo publicado na vitrine e:

```bash
curl -sS -o /dev/null -w "%{http_code} %{size_download} %{content_type}\n" \
  "https://app2037.fly.dev/public/v1/media/<loja>/<veiculo>/<arquivo>.jpg"
```

Esperado: `200`, tamanho > 0, `image/jpeg`. Esta é a prova de que o backend S3 está no caminho — o `BUCKET_NAME` já está setado, então `_escolher_backend()` devolveu `BackendS3`.

- [ ] **Step 11: Remover o diretório do volume da config**

`deploy/fly/3vm/fly.app.toml:63` — remover `ESTOQUE_MEDIA_STORAGE_DIR = "/data/estoque/media"`.
`deploy/fly/3vm/entrypoint-app.sh:35` — remover o `export ESTOQUE_MEDIA_STORAGE_DIR`.

Não apagar os arquivos de `/data/estoque/media` — eles são o rollback até o volume ser destruído na Task C3.

- [ ] **Step 12: Commit**

```bash
git add estoque-api/ deploy/fly/3vm/
git commit -m "feat(estoque): midia vai para object storage compartilhado (Tigris)"
```

**Rollback:** `fly secrets unset BUCKET_NAME -a app2037` faz `_escolher_backend()` voltar para `BackendLocal` e os arquivos do volume voltam a ser servidos, sem mudar código.

---

### Task A8: Provar que o container não escreve mais no volume

Fecha a Fase A: se algum caminho de escrita sobreviveu, é aqui que aparece — **antes** de o volume sumir.

**Files:**
- Modify: `deploy/fly/3vm/entrypoint-app.sh:5-11` (o `mkdir -p`)

- [ ] **Step 1: Decidir o destino dos diretórios do motor**

```bash
fly ssh console -a app2037 -C "ls -la /data/motor/screenshots /data/motor/storage_state; find /data/motor -type f | wc -l"
```

Esperado: `0` arquivos. Razão: `fly.app.toml:69-70` roda o motor com `MOTOR_ORCHESTRATOR_ONLY=1` e `MOTOR_WORKER_TIPOS=api,mock` — quem tira screenshot é o Playwright, que roda no `motor2037` e escreve em `/srv/data/screenshots` (`deploy/fly/3vm/fly.worker.toml:48-49`), disco efêmero de outro app.

**Gate:** se aparecer arquivo, **parar**. Significa que o orquestrador escreve prints e a Fase A precisa de mais uma task (mandar screenshot para o Tigris também, ou para a coluna `screenshot_conteudo` que `motor-simulacao/app/main.py:309` já lê). Se der `0`, seguir.

- [ ] **Step 2: Enxugar o `mkdir` do entrypoint**

`deploy/fly/3vm/entrypoint-app.sh:5-11` — substituir o bloco inteiro por nada. Nenhum dos seis diretórios tem mais dono: `portal`, `revy-trafego` e `catalogo` foram para o Postgres (A3/A4/A6); `estoque/media` foi para o Tigris (A7); `motor/*` é comprovadamente vazio (Step 1). Remover também `MOTOR_SCREENSHOT_DIR` e `MOTOR_STORAGE_STATE_DIR` (linhas 36-37) — mantê-los apontando para `/data` depois que `/data` sumir só produziria erro tardio.

- [ ] **Step 3: Deploy e observar escrita em `/data` por uma janela real**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C "find /data -newermt '-10 minutes' -type f 2>/dev/null | head -20; echo '--- fim'"
```

Rodar depois de exercitar a UI por alguns minutos: login no Portal, abrir `/trafego`, abrir a vitrine `/loja/`, cadastrar um veículo com foto. Esperado: nenhuma linha antes de `--- fim`.

- [ ] **Step 4: Conferir que nenhum processo mantém arquivo aberto em `/data`**

```bash
fly ssh console -a app2037 -C "ls -l /proc/*/fd 2>/dev/null | grep '/data' || echo 'nenhum fd em /data'"
```

Esperado: `nenhum fd em /data`.

- [ ] **Step 5: Health completo**

```bash
curl -sS -o /dev/null -w "healthz=%{http_code}\n"    https://app2037.fly.dev/healthz
curl -sS -o /dev/null -w "revy=%{http_code}\n"       https://app2037.fly.dev/trafego/health/ready
curl -sS -o /dev/null -w "vitrine=%{http_code}\n"    https://app2037.fly.dev/loja/
```

Esperado: `200` nos três.

- [ ] **Step 6: Commit**

```bash
git add deploy/fly/3vm/entrypoint-app.sh
git commit -m "chore(deploy): container do bundle deixa de escrever no volume"
```

**Gate da Fase A:** Fase B não começa sem os Steps 3 e 4 limpos. Enquanto houver escrita em `/data`, escalar continua produzindo divergência silenciosa.

---

## Fase B — tirar os jobs do processo web

### As três opções, e a escolhida

**Opção 1 — advisory lock no Postgres (`pg_try_advisory_lock`).** Cada tick tenta pegar um lock nomeado antes de rodar; quem não pega, dorme até o próximo intervalo.

- Custo: ~40 linhas por produto, zero infraestrutura nova, zero custo mensal.
- Escala para qualquer N sem reconfiguração.
- Advisory locks do Postgres são **escopados por banco** (o locktag inclui o OID do banco), então Portal e Revy não colidem mesmo compartilhando o cluster `suite-pg` — o que casa com a regra de "banco próprio por produto". Ainda assim os nomes são prefixados por produto, por clareza.
- Se a machine dona morre, a sessão cai e o Postgres libera o lock automaticamente: failover em um intervalo, sem heartbeat, sem lock órfão.
- Depende da Fase A (não existe advisory lock em SQLite). Por isso é Fase B, não Fase A.
- Limitação honesta: os workers continuam compartilhando CPU e memória com o processo web. Não separa envelopes de recurso.

**Opção 2 — process group `web`/`worker` separado no `fly.app.toml`.** A Fly já suporta `[processes]` com comandos distintos, e `fly scale count web=N worker=1`.

- É a resposta arquiteturalmente "certa" e a única que dá aos workers CPU/memória próprias.
- Mas custa uma machine inteira sempre ligada (~US$5/mês em `iad` a 512MB — ~25% do custo total do lab hoje, que é US$20,28/mês) só para rodar loops que hoje ocupam poucos milissegundos por minuto.
- E custa código de deploy: o bundle é um supervisord com 8 programas (`deploy/fly/3vm/supervisord.conf`); um process group `worker` precisaria de um segundo `supervisord.conf`, um segundo entrypoint, e uma decisão sobre quais dos 8 programas sobem em qual grupo — com o detalhe de que os workers vivem **dentro** dos processos `portal` e `revy-trafego`, então não dá para separá-los sem antes ter um modo "só worker" nesses apps, que não existe.
- Rejeitada **agora**, recomendada **depois**: é para onde ir quando um job passar a consumir CPU de forma que atrapalhe o request path.

**Opção 3 — disparo externo pelos endpoints `/internal/jobs/*`.** Desligar os loops e chamar os endpoints por cron.

- Aproveita o que já existe — mas só em parte. Dos 9 workers, **4** têm endpoint (`meta-spend-sync` no Portal e no Revy, `google-conversions-outbox`, `google-ads-metrics-sync`). Não há endpoint para o CAPI retry, para o outbox de provisionamento, para o outbox Portal→Revy nem para o outbox do Catálogo. Cinco endpoints novos, com teste, antes de a opção sequer funcionar.
- Exige um agendador que **não existe** no stack: nada no `deploy/fly/` configura cron, e o n8n é o orquestrador de WhatsApp, não de ops. Meter jobs de ops no n8n acopla o data plane ao workflow de conversa.
- E troca a semântica: hoje o retry de outbox tem cadência de 60s com backoff próprio; via cron externo a cadência passa a ser a do cron, e uma falha do agendador é silenciosa.
- Fica como **escape hatch manual**, que é o papel que já cumpre. Não vira o mecanismo principal.

**RECOMENDAÇÃO: Opção 1.** Menor superfície, custo zero, resolve o problema para qualquer N, e é reversível (remover a chamada devolve o comportamento atual). A Opção 2 é o caminho de saída documentado para quando os workers precisarem de recurso próprio; a Opção 3 continua disponível para disparo manual de ops.

---

### Task B1: Advisory lock no Portal

**Files:**
- Create: `portal-gestao/app/advisory_lock.py`
- Modify: `portal-gestao/app/revy_trafego_outbox_job.py:78` (dentro de `_run`)
- Modify: `portal-gestao/app/meta_capi_job.py:114` (dentro de `_run`)
- Modify: `portal-gestao/app/meta_ads_spend_job.py:140` (dentro de `_run`)
- Test: `portal-gestao/tests/test_advisory_lock.py`

**Interfaces:**
- Produces: `lock_exclusivo(nome: str) -> ContextManager[bool]` e `tick_com_lock(nome: str, fn: Callable[[], T]) -> T | None`, em `portal-gestao/app/advisory_lock.py`. A Task B2 replica a mesma interface em `revy-trafego/app/advisory_lock.py` — **por cópia, não por import**, porque import entre produtos é proibido.

- [ ] **Step 1: Escrever o teste que falha**

```python
# portal-gestao/tests/test_advisory_lock.py
import os

import pytest

from app.advisory_lock import chave_lock, lock_exclusivo, tick_com_lock


def test_chave_lock_e_deterministica_e_cabe_em_bigint():
    a = chave_lock("meta-capi")
    assert a == chave_lock("meta-capi")
    assert a != chave_lock("meta-spend")
    assert -(2**63) <= a < 2**63


def test_no_sqlite_o_lock_sempre_cede_o_tick():
    with lock_exclusivo("meta-capi") as dono:
        assert dono is True


def test_tick_com_lock_executa_e_devolve_o_resultado():
    assert tick_com_lock("meta-capi", lambda: {"processados": 3}) == {"processados": 3}


@pytest.mark.skipif(
    not os.getenv("PORTAL_TEST_POSTGRES_URL"),
    reason="exige um Postgres real; define PORTAL_TEST_POSTGRES_URL para rodar",
)
def test_em_postgres_o_segundo_processo_nao_pega_o_lock(monkeypatch):
    from sqlalchemy import create_engine

    from app import advisory_lock

    url = os.environ["PORTAL_TEST_POSTGRES_URL"]
    monkeypatch.setattr(advisory_lock, "engine", create_engine(url))

    with advisory_lock.lock_exclusivo("teste-concorrencia") as primeiro:
        assert primeiro is True
        # Segunda conexão, mesmo processo: simula a outra machine.
        outro = create_engine(url)
        monkeypatch.setattr(advisory_lock, "engine", outro)
        with advisory_lock.lock_exclusivo("teste-concorrencia") as segundo:
            assert segundo is False
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest tests/test_advisory_lock.py -q
```

Esperado: `ModuleNotFoundError: No module named 'app.advisory_lock'`.

- [ ] **Step 3: Implementar**

```python
# portal-gestao/app/advisory_lock.py
"""Um tick por vez entre N machines, usando lock cooperativo do Postgres.

Advisory lock do Postgres é escopado ao banco (o locktag inclui o OID do
banco), então a chave do Portal nunca colide com a do Revy Tráfego mesmo
compartilhando o cluster `suite-pg`. O prefixo de namespace existe só para
tornar isso legível em `pg_locks`.

Em SQLite (dev e testes) vira no-op que sempre cede o tick.
"""
from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

from sqlalchemy import text

from app.db import engine

logger = logging.getLogger(__name__)

_NAMESPACE = "portal-gestao"
T = TypeVar("T")


def chave_lock(nome: str) -> int:
    """bigint determinístico e estável entre deploys, para pg_try_advisory_lock."""
    digest = hashlib.blake2b(f"{_NAMESPACE}:{nome}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


@contextmanager
def lock_exclusivo(nome: str) -> Iterator[bool]:
    """Cede True se este processo é o dono do tick; False se outra machine é.

    A conexão fica reservada enquanto o lock existe: devolvê-la ao pool antes
    do unlock deixaria o lock preso a uma conexão reutilizável. AUTOCOMMIT
    evita uma sessão `idle in transaction` segurando conexão de um Postgres
    de 512MB. Se o processo morrer, a sessão cai e o lock é liberado pelo
    próprio Postgres — que é o failover desejado.
    """
    if engine.dialect.name != "postgresql":
        yield True
        return

    chave = chave_lock(nome)
    conexao = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    obtido = False
    try:
        obtido = bool(
            conexao.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": chave}).scalar()
        )
        yield obtido
    finally:
        if obtido:
            try:
                conexao.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": chave})
            except Exception:
                logger.warning("advisory_lock: unlock de %s falhou; a sessão libera ao fechar", nome)
        conexao.close()


def tick_com_lock(nome: str, fn: Callable[[], T]) -> T | None:
    """Roda `fn` só se este processo tiver o lock. Devolve None se não tiver."""
    with lock_exclusivo(nome) as dono:
        if not dono:
            logger.debug("advisory_lock: tick de %s pertence a outra machine", nome)
            return None
        return fn()
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest tests/test_advisory_lock.py -q
```

Esperado: `3 passed, 1 skipped`.

- [ ] **Step 5: Rodar o teste de concorrência contra um Postgres de verdade**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
docker run -d --rm --name pg-lock-teste -e POSTGRES_PASSWORD=teste -p 55432:5432 postgres:18
sleep 5
PORTAL_TEST_POSTGRES_URL="postgresql://postgres:teste@127.0.0.1:55432/postgres" \
  .venv/bin/python -m pytest tests/test_advisory_lock.py -q
docker rm -f pg-lock-teste
```

Esperado: `4 passed`. **Gate:** este é o único passo que prova que a exclusão mútua funciona de fato. Sem ele, a Fase B é uma hipótese.

- [ ] **Step 6: Aplicar aos três workers**

`portal-gestao/app/revy_trafego_outbox_job.py` — importar e trocar a chamada dentro de `_run` (linha 78):

```python
from app.advisory_lock import tick_com_lock
```

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("revy-trafego-outbox", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`portal-gestao/app/meta_capi_job.py` — mesma troca em `_run` (linha 114), com a chave `"meta-capi-retry"`:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("meta-capi-retry", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`portal-gestao/app/meta_ads_spend_job.py` — mesma troca em `_run` (linha 140), com a chave `"meta-spend-sync"`:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("meta-spend-sync", self.run_once)
            if self._stop.wait(self.interval):
                break
```

O lock fica em `_run`, **não** em `run_once`, de propósito: os endpoints `/internal/jobs/*` chamam `run_once` diretamente e devem continuar funcionando como disparo manual de ops (R3).

- [ ] **Step 7: Rodar a suíte inteira do Portal**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao
.venv/bin/python -m pytest -q
```

Esperado: `471 passed`. Nenhum teste deve precisar de ajuste: em SQLite `tick_com_lock` sempre executa `fn`.

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/advisory_lock.py portal-gestao/app/revy_trafego_outbox_job.py \
        portal-gestao/app/meta_capi_job.py portal-gestao/app/meta_ads_spend_job.py \
        portal-gestao/tests/test_advisory_lock.py
git commit -m "feat(portal): workers periodicos rodam em uma machine so via advisory lock"
```

---

### Task B2: Advisory lock no Revy Tráfego e no Catálogo

Cinco workers no Revy e um no Catálogo. O módulo é **copiado**, não importado — a regra do `CLAUDE.md` proíbe import entre produtos, e a duplicação de 40 linhas é o preço correto por manter os produtos desacoplados.

**Files:**
- Create: `revy-trafego/app/advisory_lock.py`
- Create: `catalogo-publico/app/advisory_lock.py`
- Modify: `revy-trafego/app/meta_capi_job.py:114`, `revy-trafego/app/meta_ads_spend_job.py:140`, `revy-trafego/app/control/provisioning_job.py:131`, `revy-trafego/app/control/google_ads_conversions_job.py:186`, `revy-trafego/app/control/google_ads_metrics_job.py:277`
- Modify: `catalogo-publico/app/outbox.py` (o `OutboxWorker`)
- Test: `revy-trafego/tests/test_advisory_lock.py`, `catalogo-publico/tests/test_advisory_lock.py`

**Interfaces:**
- Consumes: nada de outro produto.
- Produces: `lock_exclusivo` / `tick_com_lock` / `chave_lock` em cada um dos dois produtos, com a mesma assinatura da Task B1.

- [ ] **Step 1: Escrever o teste do Revy**

```python
# revy-trafego/tests/test_advisory_lock.py
import os

import pytest

from app.advisory_lock import chave_lock, lock_exclusivo, tick_com_lock


def test_chave_lock_e_deterministica_e_cabe_em_bigint():
    a = chave_lock("provisioning-outbox")
    assert a == chave_lock("provisioning-outbox")
    assert a != chave_lock("google-conversions-outbox")
    assert -(2**63) <= a < 2**63


def test_no_sqlite_o_lock_sempre_cede_o_tick():
    with lock_exclusivo("provisioning-outbox") as dono:
        assert dono is True


def test_tick_com_lock_executa_e_devolve_o_resultado():
    assert tick_com_lock("provisioning-outbox", lambda: {"delivered": 2}) == {"delivered": 2}


def test_namespace_do_revy_difere_do_namespace_do_portal():
    # Blindagem contra alguém "unificar" os dois módulos com um copiar-colar.
    from app import advisory_lock

    assert advisory_lock._NAMESPACE == "revy-trafego"


@pytest.mark.skipif(
    not os.getenv("REVY_TEST_POSTGRES_URL"),
    reason="exige um Postgres real; define REVY_TEST_POSTGRES_URL para rodar",
)
def test_em_postgres_o_segundo_processo_nao_pega_o_lock(monkeypatch):
    from sqlalchemy import create_engine

    from app import advisory_lock

    url = os.environ["REVY_TEST_POSTGRES_URL"]
    monkeypatch.setattr(advisory_lock, "engine", create_engine(url))
    with advisory_lock.lock_exclusivo("teste-concorrencia") as primeiro:
        assert primeiro is True
        monkeypatch.setattr(advisory_lock, "engine", create_engine(url))
        with advisory_lock.lock_exclusivo("teste-concorrencia") as segundo:
            assert segundo is False
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/revy-trafego
.venv/bin/python -m pytest tests/test_advisory_lock.py -q
```

Esperado: `ModuleNotFoundError: No module named 'app.advisory_lock'`.

- [ ] **Step 3: Criar `revy-trafego/app/advisory_lock.py`**

Conteúdo idêntico ao de `portal-gestao/app/advisory_lock.py` (Task B1, Step 3), com **duas** diferenças, ambas obrigatórias:

```python
_NAMESPACE = "revy-trafego"
```

e o docstring do módulo trocando "Portal" por "Revy Tráfego" na frase sobre escopo de banco. O `from app.db import engine` resolve para `revy-trafego/app/db.py`, que é outro engine e outro banco.

- [ ] **Step 4: Rodar e ver passar, inclusive contra Postgres**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/revy-trafego
docker run -d --rm --name pg-lock-revy -e POSTGRES_PASSWORD=teste -p 55433:5432 postgres:18
sleep 5
REVY_TEST_POSTGRES_URL="postgresql://postgres:teste@127.0.0.1:55433/postgres" \
  .venv/bin/python -m pytest tests/test_advisory_lock.py -q
docker rm -f pg-lock-revy
```

Esperado: `5 passed`.

- [ ] **Step 5: Aplicar aos cinco workers do Revy**

Em cada arquivo, acrescentar o import e trocar `self.run_once()` por `tick_com_lock("<chave>", self.run_once)` dentro de `_run`.

`revy-trafego/app/meta_capi_job.py` (`_run` na linha 110):

```python
from app.advisory_lock import tick_com_lock
```

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("meta-capi-retry", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`revy-trafego/app/meta_ads_spend_job.py` (`_run` na linha 136), chave `"meta-spend-sync"`:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("meta-spend-sync", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`revy-trafego/app/control/provisioning_job.py` (`_run` na linha 127), chave `"provisioning-outbox"` — **este é o mais crítico**: é o único worker sem nenhuma proteção de duplicação (`provisioning_outbox.process_pending` não faz claim), então o lock é a única coisa entre N machines e uma entrega duplicada ao Chatbot/Estoque/Portal:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("provisioning-outbox", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`revy-trafego/app/control/google_ads_conversions_job.py` (`_run` na linha 182), chave `"google-conversions-outbox"`:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("google-conversions-outbox", self.run_once)
            if self._stop.wait(self.interval):
                break
```

`revy-trafego/app/control/google_ads_metrics_job.py` (`_run` na linha 273), chave `"google-ads-metrics-sync"`:

```python
    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            tick_com_lock("google-ads-metrics-sync", self.run_once)
            if self._stop.wait(self.interval):
                break
```

Os dois módulos em `app/control/` importam com o mesmo caminho absoluto (`from app.advisory_lock import tick_com_lock`), porque `PYTHONPATH=/srv/revy-trafego`.

- [ ] **Step 6: Rodar a suíte do Revy**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/revy-trafego
.venv/bin/python -m pytest -q
```

Esperado: `366 passed, 1 failed` (361 + os 5 novos do lock; o `failed` continua sendo só o `test_process_pending_falha_marca_failed_e_incrementa_attempts`).

- [ ] **Step 7: Criar `catalogo-publico/app/advisory_lock.py` e o teste**

Mesmo módulo, `_NAMESPACE = "catalogo-publico"`, importando `from app.db import engine` (criado na Task A5). O teste é o de `revy-trafego/tests/test_advisory_lock.py` com as chaves trocadas para `"catalogo-outbox"` e a asserção de namespace ajustada para `"catalogo-publico"`.

- [ ] **Step 8: Aplicar ao `OutboxWorker` do Catálogo**

`catalogo-publico/app/outbox.py` — envolver a chamada periódica do worker com `tick_com_lock("catalogo-outbox", ...)`. O Catálogo já é idempotente no destino (`Idempotency-Key: event_id`, deduplicado em `chatbot-api/app/main.py:629-631`), então o lock aqui é economia de chamadas HTTP e de `attempts` inflado, não correção de bug.

- [ ] **Step 9: Rodar a suíte do Catálogo**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico
.venv/bin/python -m pytest -q
```

Esperado: `53 passed` + os testes novos do lock.

- [ ] **Step 10: Commit**

```bash
git add revy-trafego/app/advisory_lock.py revy-trafego/app/meta_capi_job.py \
        revy-trafego/app/meta_ads_spend_job.py revy-trafego/app/control/ \
        revy-trafego/tests/test_advisory_lock.py \
        catalogo-publico/app/advisory_lock.py catalogo-publico/app/outbox.py \
        catalogo-publico/tests/test_advisory_lock.py
git commit -m "feat(revy,catalogo): workers periodicos coordenados por advisory lock"
```

---

### Task B3: Provar a exclusão mútua em produção e fechar as pontas

**Files:**
- Modify: `deploy/fly/3vm/README.md` (seção nova sobre workers e locks)

- [ ] **Step 1: Deploy**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
curl -sS -o /dev/null -w "healthz=%{http_code}\n" https://app2037.fly.dev/healthz
```

- [ ] **Step 2: Ver os locks existirem de fato, com uma machine**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
for rotulo, var in ((\"portal\", \"PORTAL_DATABASE_URL\"), (\"revy\", \"REVY_TRAFEGO_DATABASE_URL\")):
    with psycopg.connect(os.environ[var]) as c:
        locks = c.execute(\"SELECT objid, classid FROM pg_locks WHERE locktype=\x27advisory\x27\").fetchall()
        print(rotulo, \"advisory locks ativos:\", len(locks))
"'
```

Rodar durante alguns segundos seguidos. Esperado: contagens oscilando entre 0 e o número de workers ligados — os locks são tomados e liberados a cada tick, não mantidos. Se um lock ficar preso indefinidamente, é sinal de `run_once` travado e vale investigar antes de escalar.

- [ ] **Step 3: GATE — subir uma segunda machine temporária e medir**

Este é o teste que só a execução responde.

```bash
fly scale count 2 -a app2037 --yes
fly machines list -a app2037
```

Escolher um worker com log identificável (o de provisionamento loga `revy-trafego: provisioning delivery worker ON` no boot) e observar dois intervalos completos:

```bash
fly logs -a app2037 --no-tail | grep -iE "provisioning|advisory_lock|outbox" | tail -40
```

**Critério de aceite:** o número de execuções efetivas por intervalo é **1**, não 2, com as duas machines no ar. Se aparecerem duas execuções por intervalo, o lock não está no caminho — parar e corrigir antes de qualquer coisa da Fase C.

```bash
fly scale count 1 -a app2037 --yes
```

Voltar para 1 ao final: a Fase C é quem decide o N definitivo, depois do gate de conexões.

- [ ] **Step 4: Confirmar se o fan-out do Motor precisa de lock (R6)**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
rg -n "MOTOR_FANOUT_ENABLED|MOTOR_FLY_AUTOSCALE_ENABLED" motor-simulacao/app/ | head
rg -n "threading.Thread|while True|start_worker" motor-simulacao/app/main.py | head
```

Se o fan-out for reativo (disparado por requisição de simulação), N machines não duplicam nada: cada job entra por uma requisição só. Se houver um loop periódico acordando machines, ele precisa da mesma coordenação — e vira uma task nova, com `motor-simulacao/app/advisory_lock.py` sobre `MOTOR_DATABASE_URL`. Registrar o veredito em `$SCRATCH/escala-app2037/veredito-motor-fanout.txt`.

- [ ] **Step 5: Documentar no README**

`deploy/fly/3vm/README.md` — seção nova, depois de "Revy Control (`revy-trafego`) — data plane da Fase 3":

- tabela dos 9 workers com produto, chave de lock e se são idempotentes por conta própria (copiar do Bloqueador 2 deste plano);
- a regra: o lock protege o **laço periódico**, não os endpoints `/internal/jobs/*`; esses são disparo manual de ops e **não devem ser postos em cron paralelo**;
- como inspecionar: a consulta a `pg_locks` do Step 2;
- a saída futura documentada: process group `worker` separado (Opção 2), quando os jobs precisarem de CPU/memória própria.

- [ ] **Step 6: Commit**

```bash
git add deploy/fly/3vm/README.md
git commit -m "docs(deploy): workers periodicos, chaves de lock e limites do disparo manual"
```

**Gate da Fase B:** Fase C não começa sem o Step 3 provando 1 execução por intervalo com 2 machines.

---

## Fase C — escalar de verdade

### Task C1: GATE — medir o teto do `suite-pg` e limitar os pools

Esta task existe porque escalar sem ela troca um problema por outro. Cada machine roda 5 processos que falam com Postgres (chatbot, estoque, portal, revy-trafego, motor). O `create_engine` de `portal-gestao/app/db.py:13` e `revy-trafego/app/db.py:13` não passa `pool_size` nem `max_overflow`, então vale o default do SQLAlchemy: **5 + 10 = até 15 conexões por processo**. Com N=2 machines isso chega a **150 conexões** contra um Postgres de 512MB cujo `max_connections` ninguém mediu.

**Files:**
- Modify: `portal-gestao/app/db.py`
- Modify: `revy-trafego/app/db.py`
- Modify: `catalogo-publico/app/db.py`

- [ ] **Step 1: Medir o teto real**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"PORTAL_DATABASE_URL\"]) as c:
    for nome in (\"max_connections\", \"superuser_reserved_connections\", \"shared_buffers\", \"work_mem\"):
        print(nome, c.execute(f\"SHOW {nome}\").fetchone()[0])
    print(\"em uso agora:\", c.execute(\"SELECT count(*) FROM pg_stat_activity\").fetchone()[0])
    print(\"por banco:\", c.execute(\"SELECT datname, count(*) FROM pg_stat_activity GROUP BY 1 ORDER BY 2 DESC\").fetchall())
"'
```

Registrar a saída em `$SCRATCH/escala-app2037/pg-limites.txt`. **É este número que define o N máximo**, não a memória do `app2037`.

- [ ] **Step 2: Calcular o orçamento de conexões**

Fórmula, com os números do Step 1:

```
orcamento_por_processo = (max_connections - superuser_reserved_connections - 10) / (5 processos * N machines)
```

O `- 10` é folga para `fly ssh console`, migrations no boot e o `motor2037` (que fala com o mesmo cluster a partir de `gru`). Escolher `pool_size` e `max_overflow` tais que `pool_size + max_overflow <= orcamento_por_processo`. Se `max_connections` for 300 e N=2, isso dá 28 por processo — folgado. Se for 100, dá 9, e `pool_size=5, max_overflow=4` é o teto.

- [ ] **Step 3: Fixar os pools explicitamente**

`portal-gestao/app/db.py` — substituir a criação do engine por:

```python
_kwargs = {}
if settings.database_url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.database_url:
        _kwargs["poolclass"] = StaticPool
else:
    # Teto explícito: com N machines o suite-pg é o recurso escasso, não o app.
    # Ver docs/superpowers/plans/2026-07-31-escala-horizontal-app2037.md, Task C1.
    _kwargs["pool_size"] = int(os.getenv("PORTAL_DB_POOL_SIZE", "5"))
    _kwargs["max_overflow"] = int(os.getenv("PORTAL_DB_MAX_OVERFLOW", "5"))
    _kwargs["pool_pre_ping"] = True
    _kwargs["pool_recycle"] = 900

engine = create_engine(settings.database_url, future=True, **_kwargs)
```

`pool_pre_ping` importa porque o `app2037` (`iad`) fala com o `suite-pg` por `flycast`, e conexão ociosa derrubada pela rede vira `OperationalError` no primeiro uso sem ele. `pool_recycle=900` evita segurar conexão por horas.

`revy-trafego/app/db.py` — mesmo bloco, com `REVY_TRAFEGO_DB_POOL_SIZE` / `REVY_TRAFEGO_DB_MAX_OVERFLOW`.
`catalogo-publico/app/db.py` — mesmo bloco dentro de `criar_engine`, com `CATALOGO_DB_POOL_SIZE` / `CATALOGO_DB_MAX_OVERFLOW`.

Não esquecer `import os` no topo de `catalogo-publico/app/db.py`.

- [ ] **Step 4: Rodar as três suítes**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/portal-gestao   && .venv/bin/python -m pytest -q
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/revy-trafego    && .venv/bin/python -m pytest -q
cd /Users/gabrielabreucherubini/Documents/codigo/CRM/catalogo-publico && .venv/bin/python -m pytest -q
```

Esperado: `471 passed`; `366 passed, 1 failed`; `53 passed` + os do lock. Os testes usam SQLite, então o ramo novo não é exercitado por eles — o que o exercita é o Step 5.

- [ ] **Step 5: Deploy e conferir o consumo real**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"PORTAL_DATABASE_URL\"]) as c:
    print(c.execute(\"SELECT datname, state, count(*) FROM pg_stat_activity GROUP BY 1,2 ORDER BY 3 DESC\").fetchall())
"'
```

Esperado: total bem abaixo do `max_connections` do Step 1, com poucas `idle in transaction` (idealmente zero — o AUTOCOMMIT do advisory lock foi escolhido exatamente para isso).

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/db.py revy-trafego/app/db.py catalogo-publico/app/db.py
git commit -m "perf(db): pools explicitos e pre-ping antes de escalar horizontalmente"
```

**Gate:** `fly scale count` só acontece depois que o orçamento do Step 2 estiver calculado e escrito em `$SCRATCH/escala-app2037/pg-limites.txt`.

---

### Task C2: Concorrência declarada no `fly.app.toml`

**Files:**
- Modify: `deploy/fly/3vm/fly.app.toml:84-89`

- [ ] **Step 1: Medir a concorrência real antes de inventar o número**

```bash
fly ssh console -a app2037 -C "cat /proc/loadavg; free -m"
fly logs -a app2037 --no-tail | tail -50
```

E, na aba de métricas da Fly, olhar `fly_app_concurrency` na última semana:

```bash
open https://fly.io/apps/app2037/metrics
```

Registrar o pico observado em `$SCRATCH/escala-app2037/concorrencia.txt`. Sem esse número, `soft_limit` vira chute.

- [ ] **Step 2: Declarar os limites**

`deploy/fly/3vm/fly.app.toml` — acrescentar dentro de `[http_service]`, antes do bloco `[[http_service.checks]]`:

```toml
  [http_service.concurrency]
    type = "requests"
    soft_limit = 40
    hard_limit = 80
```

Justificativa dos valores: o bundle serve 6 apps ASGI por trás de um nginx, cada um com **um** processo uvicorn (`run-*.sh` sem `--workers`). Um uvicorn single-process sustenta bem dezenas de requisições concorrentes de I/O, mas não centenas. `soft_limit = 40` diz ao proxy da Fly "prefira outra machine a partir daqui" e `hard_limit = 80` diz "pare de mandar". Se o pico medido no Step 1 for maior que 40, subir os dois proporcionalmente — mas nunca acima do que o pool do Postgres (Task C1) aguenta, porque a requisição que não acha conexão devolve 500, e não 503 com retry.

`type = "requests"` e não `"connections"` porque o `[http_service]` da Fly já faz keep-alive: contar conexões superestimaria a carga.

- [ ] **Step 3: Deploy e conferir que o proxy aceitou**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly config show -a app2037 | grep -A 4 concurrency
```

Esperado: o bloco aparecer na config efetiva do app.

- [ ] **Step 4: Commit**

```bash
git add deploy/fly/3vm/fly.app.toml
git commit -m "ops(fly): declara concorrencia do http_service do app2037"
```

---

### Task C3: Remover o `[[mounts]]` e escalar

**Files:**
- Modify: `deploy/fly/3vm/fly.app.toml:98-105`

- [ ] **Step 1: Reconfirmar que o volume está frio**

```bash
fly ssh console -a app2037 -C "find /data -newermt '-24 hours' -type f 2>/dev/null | head; echo '--- fim'"
fly ssh console -a app2037 -C "du -sh /data/* 2>/dev/null"
```

Esperado: nenhuma linha antes de `--- fim` (nada escrito nas últimas 24h). Os diretórios ainda **têm** os dados antigos — é isso que os torna o rollback da Fase A. **Gate:** se houver escrita nas últimas 24h, voltar para a Task A8.

- [ ] **Step 2: Snapshot final antes de soltar o volume**

```bash
fly volumes snapshots create vol_vdeg231ez2xnq234 -a app2037
fly volumes snapshots list vol_vdeg231ez2xnq234 -a app2037 | tail -3
```

Este snapshot é o último ponto de recuperação dos três SQLite e da mídia antiga. Retenção de 5 dias.

- [ ] **Step 3: Remover o mount e alinhar a memória declarada**

`deploy/fly/3vm/fly.app.toml` — remover as três linhas finais:

```toml
[[mounts]]
  source = "app_data"
  destination = "/data"
```

E corrigir a divergência registrada no inventário: a linha 100 declara `memory = "1536"` mas a machine roda com 1024MB, e o consumo medido é ~675MB. Deixar `1024`, que é a verdade operacional:

```toml
[[vm]]
  size = "shared-cpu-1x"
  memory = "1024"
```

- [ ] **Step 4: Deploy com uma machine e conferir que ela sobe sem `/data`**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
fly ssh console -a app2037 -C "ls /data 2>&1 || echo 'sem /data — esperado'"
curl -sS -o /dev/null -w "healthz=%{http_code}\n" https://app2037.fly.dev/healthz
```

Esperado: `/data` não existe (ou está vazio, sem o volume montado) e `healthz=200`. Este é o momento em que o fail-fast das Tasks A3/A4/A6 prova o seu valor: se algum secret de banco estiver faltando, a machine morre no boot em vez de subir com banco vazio.

- [ ] **Step 5: Escalar para 2**

```bash
fly scale count 2 -a app2037 --yes
fly machines list -a app2037
fly volumes list -a app2037
```

Esperado: duas machines `started`, ambas com checks passando, e **nenhum volume novo criado** — a ausência de `[[mounts]]` é o que garante isso. Se aparecer um `app_data` novo, o mount não foi removido de verdade.

- [ ] **Step 6: Smoke das duas machines em paralelo**

```bash
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w "%{http_code} " https://app2037.fly.dev/healthz
done; echo
curl -sS -o /dev/null -w "revy=%{http_code}\n"    https://app2037.fly.dev/trafego/health/ready
curl -sS -o /dev/null -w "vitrine=%{http_code}\n" https://app2037.fly.dev/loja/
```

Esperado: vinte `200`. Depois, na UI: login no Portal e navegação por 5+ páginas — se a sessão sobreviver, o cookie assinado está funcionando entre machines, confirmando o que a análise estática dizia (`SessionMiddleware` stateless).

- [ ] **Step 7: Conferir conexões e locks com 2 machines**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"PORTAL_DATABASE_URL\"]) as c:
    print(\"conexoes:\", c.execute(\"SELECT count(*) FROM pg_stat_activity\").fetchone()[0])
    print(\"advisory:\", c.execute(\"SELECT count(*) FROM pg_locks WHERE locktype=\x27advisory\x27\").fetchone()[0])
"'
```

Esperado: conexões dentro do orçamento da Task C1; advisory locks entre 0 e o número de workers — nunca dois locks com o mesmo `objid`, que é impossível por construção mas vale confirmar.

- [ ] **Step 8: Destruir o volume**

**Só depois** dos Steps 5-7 verdes e do snapshot do Step 2 confirmado.

```bash
fly volumes destroy vol_vdeg231ez2xnq234 --yes -a app2037
fly volumes list -a app2037
```

Esperado: lista vazia. Isto libera US$0,15/mês e, mais importante, remove a possibilidade de alguém remontar o volume e reviver os SQLite fantasmas.

`deploy/fly/3vm/README.md:426` proíbe destruir volumes sem pedido do owner. **Este step exige confirmação explícita do owner antes de rodar** — não é coberto por "o plano manda".

- [ ] **Step 9: Commit**

```bash
git add deploy/fly/3vm/fly.app.toml
git commit -m "ops(fly): app2037 sem volume e escalavel horizontalmente"
```

**Rollback:** recriar o volume (`fly volumes create app_data --region iad --size 1 -a app2037`), restaurar do snapshot do Step 2, devolver o `[[mounts]]` e reverter os commits das Tasks A3/A4/A6. Custo: ~15 minutos e a janela de 5 dias do snapshot.

---

### Task C4: `suite-pg` — o próximo gargalo, documentado

Depois da Fase C o `app2037` escala por `fly scale count`. O que **não** escala é o `suite-pg`: um nó `shared-cpu-1x:512MB`, sem réplica, agora servindo 6 bancos em vez de 3.

**Files:**
- Modify: `deploy/fly/3vm/README.md`
- Modify: `docs/handoff-contexto.md`
- Modify: `docs/contexto-compacto.md`

- [ ] **Step 1: Estabelecer a linha de base do Postgres**

```bash
fly ssh console -a app2037 -C 'python3 -c "
import os, psycopg
with psycopg.connect(os.environ[\"PORTAL_DATABASE_URL\"]) as c:
    print(\"tamanho por banco:\")
    for r in c.execute(\"SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datistemplate=false ORDER BY pg_database_size(datname) DESC\"):
        print(\" \", r[0], r[1])
    print(\"cache hit ratio:\", c.execute(\"SELECT round(sum(blks_hit)*100.0/nullif(sum(blks_hit)+sum(blks_read),0),2) FROM pg_stat_database\").fetchone()[0])
"'
fly volumes list -a suite-pg
```

Registrar em `$SCRATCH/escala-app2037/pg-baseline.txt`. **Sinais de que chegou a hora de crescer:** cache hit ratio abaixo de 95%, ou o volume de 1GB passando de 70%.

- [ ] **Step 2: Escrever o caminho de crescimento no README**

`deploy/fly/3vm/README.md` — seção nova, "Crescimento do `suite-pg`", com os três degraus **em ordem**, e o gatilho de cada um:

1. **Vertical primeiro.** `fly machine update 48ee5d4ad12768 -a suite-pg --vm-memory 1024 --yes`. Gatilho: cache hit ratio < 95% ou `max_connections` apertando o orçamento da Task C1. Custo em `iad`: de US$3,19 para US$5,70/mês. É reversível em minutos e não muda topologia.
2. **Volume.** `fly volumes extend <id> -a suite-pg --size 3`. Gatilho: volume acima de 70%. Volume da Fly só cresce, nunca encolhe — subir de 1 em 1 GB.
3. **Réplica de leitura, por último.** `fly machine clone 48ee5d4ad12768 --region iad -a suite-pg` cria um standby do `postgres-flex`. Gatilho: a vertical não resolver mais. **Isto não é transparente:** as URLs de aplicação apontam para `suite-pg.flycast:5432`, que resolve para o primário; usar a réplica exige separar leitura de escrita no código de cada produto — trabalho real, não configuração. Registrar como o limite conhecido da arquitetura atual.

Registrar também a consequência já aceita da migração para `iad`: o `motor2037` fica em `gru` e paga ~120ms de RTT por query contra este mesmo Postgres (README linhas 29-31). Escalar o `suite-pg` verticalmente **não** melhora isso.

- [ ] **Step 3: Atualizar o contexto do repositório**

`docs/contexto-compacto.md` e `docs/handoff-contexto.md` — registrar:

- `app2037` é stateless e escala por `fly scale count`; **não** tem mais volume;
- Portal, Revy Tráfego e Catálogo agora vivem no `suite-pg` (bancos `portal`, `revy_trafego`, `catalogo`);
- mídia do Estoque está no Tigris, servida pela mesma URL pública de antes;
- os 9 workers periódicos são coordenados por advisory lock; a tabela de chaves está no `deploy/fly/3vm/README.md`;
- o próximo gargalo é o `suite-pg`, com o caminho de crescimento do Step 2;
- pendência aberta, não resolvida aqui: `revy-trafego/tests/test_control_provisioning_outbox.py::test_process_pending_falha_marca_failed_e_incrementa_attempts` está falhando desde `573348e` e cobre justamente o caminho de falha do outbox que a Fase B passou a proteger por lock.

- [ ] **Step 4: Validar o worktree**

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
git diff --check && git status --short
```

- [ ] **Step 5: Commit**

```bash
git add deploy/fly/3vm/README.md docs/contexto-compacto.md docs/handoff-contexto.md
git commit -m "docs: app2037 escalavel, estado no suite-pg e caminho de crescimento do postgres"
```

---

## Rollback global

Cada fase reverte sozinha, e a ordem de reversão é a inversa da execução:

| Situação | Reversão |
|---|---|
| Fase C quebrou (2 machines instáveis) | `fly scale count 1 -a app2037 --yes`. Volta ao comportamento pré-plano sem tocar em dados. |
| Volume já destruído e é preciso voltar ao SQLite | `fly volumes create app_data --region iad --size 1 -a app2037`, restaurar do snapshot da Task C3 Step 2, `git revert` dos commits de A3/A4/A6, redeploy. **Janela de 5 dias** (retenção de snapshot da Fly). |
| Fase B duplicando trabalho | `git revert` dos commits de B1/B2. Os locks são aditivos: removê-los devolve exatamente o comportamento de hoje. |
| Um produto específico da Fase A | `fly secrets unset <PRODUTO>_DATABASE_URL -a app2037` + `git revert` do commit daquela task. Enquanto o volume existir, o `.db` original está lá, intacto — nenhuma task deste plano apaga um SQLite de origem. |
| Mídia no Tigris com problema | `fly secrets unset BUCKET_NAME -a app2037`. `_escolher_backend()` volta para `BackendLocal` sem mudança de código. |

**O único ponto sem rollback barato** é o port do Catálogo (Task A5): reverter significa voltar ao `sqlite3` cru, e qualquer linha escrita no Postgres depois do cutover da A6 teria de ser copiada de volta à mão. Por isso A5 e A6 são tasks separadas — A5 é revertível sozinha, porque não muda banco nem comportamento.
