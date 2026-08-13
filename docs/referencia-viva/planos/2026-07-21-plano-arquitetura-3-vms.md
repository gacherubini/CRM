# Plano — Arquitetura 3 VMs (Fly.io lab / loja)

> **Status:** IMPLEMENTADO / OPERANDO (2026-07-21+) — runtime 3-VM no ar.  
> **Data:** 2026-07-21 (design); revisão 2026-07-22 (menu WA + fotos em prod).  
> **Origem:** custo always-on de 9 VMs (~US$ 35–45/mês); dono pediu arquitetura com menos VMs.  
> **Ops canônico:** `deploy/fly/3vm/` + `bash deploy/fly/up-all.sh --3vm`.  
> **Residual de produto (não é migração 3-VM):** E2E menu/cadastro + E2E cliente — ver
> [plano 2026-07-22](2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md).

**Goal:** Reduzir o runtime Fly de **9 machines always-on** para **3 machines always-on**
+ **classe de VM Playwright própria (efêmera)**, mantendo bot WhatsApp, Portal, Estoque,
Catálogo e Motor-API utilizáveis, com custo alvo always-on **~US$ 12–18/mês**.

**Architecture:** Três papéis **always-on** — **data** (Postgres), **canal** (Evolution, sessão
WA isolada), **app** (n8n + suíte Python + **site estático nginx**, **sem Chromium**). Quarto
papel **obrigatório e separado:** **VM worker Playwright** (imagem e machine próprias, 2 GB,
sob demanda). O monorepo e os produtos lógicos permanecem; muda o empacotamento de deploy.

**Tech Stack:** Fly.io Machines (`gru`), Fly Postgres self-managed, Docker multi-stage,
`supervisord` (ou `s6-overlay`) no app bundle, Uvicorn/FastAPI existentes, n8n imagem
oficial, Evolution API imagem oficial, Caddy (borda) + nginx (site estático do `site/`),
**imagem worker dedicada** com Playwright/Chromium (Machines API / fan-out já no Motor).

## Global Constraints

- Região: **`gru`** (São Paulo); org lab **`crm-419`**.
- Não recriar volumes/dados sem pedido: preservar `pg_data`, `n8n_data`,
  `evolution_instances`, `estoque_media`, `portal_data`, `motor_data`, `catalogo_data`.
- Não imprimir/versionar secrets (`.env`, tokens, Gemini, Evolution, CAPI).
- Integrações entre produtos continuam **HTTP** (mesmo se localhost no app bundle).
- **Evolution sozinha na VM canal** — deploy do Python/n8n **não** pode derrubar a sessão WA.
- **Playwright/Chromium NUNCA na VM app always-on** — só na **VM worker** (classe 4).
- Workers Playwright: **máx. 2** simultâneos (`MOTOR_MAX_BROWSER_WORKERS`); idle = **stopped**.
- monorepo: pastas `chatbot-api/`, `estoque-api/`, `portal-gestao/`, `motor-simulacao/`,
  `catalogo-publico/`, `n8n/`, `deploy/fly/` permanecem; novos artefatos em `deploy/fly/3vm/`.
- Não misturar com eixo CRM/Google Conversions na mesma PR de migração.
- Checkout/reset destrutivo proibido sem pedido explícito.
- Meta de custo always-on: **≤ US$ 18/mês** compute+volumes (egress e minutos de RPA à parte).

---

## 1. Alvo de runtime (3 always-on + VM Playwright)

> Contagem de produto: **“arquitetura 3 VMs”** = 3 machines **sempre ligadas**.  
> Playwright tem **VM própria** (classe 4), mas **não** entra no always-on: 0–2 machines
> started só durante simulação real.

```
                    Internet
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   Evolution :443   n8n :443     Portal/Catálogo :443
   (VM 2 canal)     (VM 3 app)   (VM 3 app)
        │              │              │
        │         ┌────┴────┐         │
        │         │  VM 3   │         │
        │         │ n8n     │◄────────┘
        │         │ chatbot │
        │         │ estoque │
        │         │ portal  │
        │         │ catalogo│
        │         │ site    │  (nginx estático)
        │         │ motor-api ──fan-out / Machines API──┐
        │         └────┬────┘                          │
        │              │                               ▼
        └──────────────┼──────────► VM 1 data (Postgres)
                       │              ▲
                       │              │ (storage_state / meta; sem browser)
                       │
              ┌────────┴─────────────────────────────┐
              │  VM 4 · worker-playwright (EFÊMERA)   │
              │  · imagem própria (Chromium)           │
              │  · shared-cpu-2x / 2048 MB             │
              │  · 0 idle · máx. 2 started             │
              │  · NÃO compartilha machine com app     │
              └────────────────────────────────────────┘
```

### 1.1 Always-on (as 3)

| # | Papel | App Fly (nome proposto) | RAM | Conteúdo |
|---|-------|-------------------------|-----|----------|
| 1 | **data** | `suite-pg` (existente) | 512 MB | Postgres (dbs: motor, estoque, chatbot, evolution) |
| 2 | **canal** | `evolution2037` (reusar) | 512 MB | **Só** Evolution API + volume sessão |
| 3 | **app** | `app2037` (novo) | **1536 MB** (default) | supervisord: n8n + chatbot + estoque + portal + catálogo + site (nginx) + **motor-api sem browser** |

### 1.2 VM 4 — Playwright (própria, obrigatória, **não** always-on)

| Item | Valor |
|------|--------|
| **Papel** | Executar drivers RPA (Santander, Fontecred, Bradesco, Pan, …) com Chromium |
| **App Fly** | Preferência: manter `motor2037` como **worker-only** *ou* app `worker2037` / imagem `registry.fly.io/app2037-worker` |
| **Machine size** | `shared-cpu-2x`, **2048 MB** (igual workers atuais) |
| **Imagem** | Dockerfile **separado** do app always-on — **com** `playwright install chromium` |
| **Quantidade** | Pool de machines nomeadas (`motor-worker-*`) ou create/start sob demanda; **teto 2** started |
| **Estado idle** | **`stopped`** — custo ≈ rootfs da imagem (~US$ 0,15/GB), **não** compute 2 GB |
| **Quem acorda** | `motor-api` (na VM 3) via **Fly Machines API** / fan-out já implementado |
| **Rede** | Privada (sem IP público); fala com `motor-api` e Postgres (`suite-pg.flycast`) |
| **Volume** | Opcional: reusar `motor_data` / storage_state por cliente+provedor; **não** montar volumes do app CRM |
| **Proibido** | Instalar Chromium no `Dockerfile.app`; rodar browser no mesmo cgroup/RAM da VM 3 |

**Por que VM própria (não na VM app):**

1. **Isolamento de falha** — crash/OOM do Chromium não derruba n8n/WhatsApp/Portal.  
2. **RAM** — browser precisa ~2 GB; app always-on já usa ~1–1,5 GB.  
3. **Imagem** — worker ~450 MB+ com browsers; app fica slim e deploy rápido.  
4. **Custo** — 2 GB always-on ≈ **+US$ 12/mês por worker**; stopped quase zero.  
5. **Escala** — sobe 0, 1 ou 2 workers sem redimensionar a VM do bot.

**Custo RPA (à parte do always-on):**

| Uso | Estimativa |
|-----|------------|
| Idle (4 machines stopped, rootfs) | ~US$ 1–2/mês |
| 1 worker · 20 h/mês | ~20 × US$ 0,0164 ≈ **US$ 0,33** |
| 1 worker · 24/7 | ~**US$ 11,8/mês** (evitar no lab) |

### 1.3 Fora do always-on (outros)

| Item | Onde |
|------|------|
| Site marketing | **Dentro da VM 3** (nginx no supervisord); app legado `site2037` → scale 0 após cutover |
| Apps legados API | `chatbot2037`, `estoque2037`, `portal2037`, `catalogo2037`, `n8n2037`, `site2037` → scale 0 após cutover |
| `motor2037` process `app` legado | some; sobra só papel **worker** (VM 4) se reusar o app |

### 1.4 Estimativa de custo (30 dias, prices base Fly shared)

| Item | US$/mês |
|------|---------|
| PG 512 MB | ~3,3 |
| Canal Evolution 512 MB | ~3,3 |
| App 1,5 GB | ~8,4 |
| Volumes ~7×1 GB | ~1,1 |
| **Subtotal always-on (3 VMs)** | **~US$ 16** (faixa 13–18) |
| VM 4 Playwright idle (rootfs) | ~1–2 |
| VM 4 uso típico lab (horas) | +0–2 |
| vs hoje 9 VMs always-on | **~US$ 35–45** |

---

## 2. Decisões de desenho (travadas neste plano)

### D1 — O que entra na VM `app`

Um único Dockerfile multi-serviço:

| Processo | Porta interna | Persistência |
|----------|---------------|--------------|
| n8n | 5678 | volume `n8n_data` → `/home/node/.n8n` |
| chatbot (uvicorn) | 8001 | Postgres `chatbot` |
| estoque (uvicorn + outbox thread/process) | 8002 | Postgres `estoque` + volume `estoque_media` → `/data/estoque` |
| portal (uvicorn) | 9000 | volume `portal_data` → `/data/portal` (SQLite) |
| catalogo (uvicorn) | 8003 | volume `catalogo_data` → `/data/catalogo` (SQLite) |
| motor-api (uvicorn, **sem** Playwright no processo always-on) | 8004 | Postgres `motor` + volume `motor_data` (storage_state leve) |
| **site (nginx)** | 8081 | estático de `site/` (index + assets); **sem volume** (vai na imagem) |

**Proxy de borda na VM app:** Caddy escutando **uma** porta pública 8080 e roteando por `Host`:

| Host | Upstream |
|------|----------|
| `n8n2037.fly.dev` (ou manter hostname via fly cert) | `127.0.0.1:5678` |
| `portal2037.fly.dev` | `127.0.0.1:9000` |
| `catalogo2037.fly.dev` | `127.0.0.1:8003` |
| **`site2037.fly.dev`** | **`127.0.0.1:8081`** (nginx do `site/`) |
| (opcional) health unificado | `127.0.0.1:8080/healthz` |

Chatbot/Estoque/Motor-API **sem IP público** — só `127.0.0.1` + flycast interno se necessário.
n8n, Portal, Catálogo e **Site** precisam de HTTPS público (hoje já têm).

**Site no bundle:** copiar `site/index.html`, `site/assets/`, `site/nginx.conf` (ajustar
`listen 8081`) para a imagem do app. RAM extra negligível (~5–20 MB). **Não** abre 4ª
machine always-on. Health do site **não** derruba o bot (opcional no `/healthz` agregado).

> **Fly multi-hostname no mesmo app:** um app pode ter vários certificados. Alternativa
> mais simples no MVP: **um hostname** `app2037.fly.dev` com path prefix
> (`/n8n`, `/portal`, `/catalogo`, `/` site) — preferir **manter hostnames** se o custo
> de cert for zero (≤10 free), incluindo `site2037.fly.dev`.

### D2 — Comunicação interna (pós-migração)

Trocar URLs `*.flycast` entre serviços co-localizados por **localhost**:

| Quem chama | Antes | Depois |
|------------|-------|--------|
| n8n → chatbot | `http://chatbot2037.flycast:8000` | `http://127.0.0.1:8001` |
| n8n → evolution | `http://evolution2037.flycast:8080` | `http://canal2037.flycast:8080` (outra VM) |
| chatbot → motor | `http://motor2037.flycast:8000` | `http://127.0.0.1:8004` |
| chatbot → estoque | `http://estoque2037.flycast:8000` | `http://127.0.0.1:8002` |
| portal → * | flycast multi | `http://127.0.0.1:8001/2/4` |
| catalogo → estoque | flycast | `http://127.0.0.1:8002` |

Evolution permanece em **VM canal** → n8n usa **flycast** para o canal.

### D3 — Motor / Playwright = **VM 4 dedicada** (não always-on)

Decisão travada: **Playwright tem VM própria.** Não é process group da VM app.

| Componente | Onde roda | Imagem |
|------------|-----------|--------|
| `motor-api` (HTTP, fila, fan-out, mock) | **VM 3 app** | `Dockerfile.app` — **sem** Playwright |
| Driver + Chromium | **VM 4 worker** | `Dockerfile.worker` (ou `motor-simulacao/Dockerfile` worker target) — **com** Playwright |

Regras:

1. `playwright install` / libs de browser **somente** no build do worker.  
2. `MOTOR_MAX_BROWSER_WORKERS=2` e idle stop permanecem.  
3. App Fly do worker: **(default)** reutilizar `motor2037` em modo **worker-only**
   (sem process group `app` always-on); alternativa: `worker2037` + imagem
   `registry.fly.io/app2037-worker`.  
4. `motor-api` na VM 3 chama Machines API (secrets app-scoped) para start/stop.  
5. Simulação `mock` **não** sobe VM 4.  
6. Aceite Task 0: `fly machine list` always-on **= 3**; workers existem mas **stopped**
   fora de job.

### D4 — Site (dentro da VM 3, não fora do Fly)

- `site/` **permanece no Fly**, empacotado na **VM app** (nginx no supervisord, porta 8081).
- Caddy roteia `site2037.fly.dev` → `127.0.0.1:8081`.
- App legado `site2037` (machine 256 MB dedicada) → **scale 0** após cutover (economia ~US$ 2).
- **Não** usar Cloudflare Pages / hospedagem externa neste plano (decisão do dono).
- Conteúdo versionado em `site/`; rebuild da imagem `app` publica landing nova.

### D5 — Produtos “vendáveis separados”

- **Código e pastas** continuam independentes (não fundir repositórios).
- **Deploy lab 3-VM** é um **perfil de empacotamento** (`deploy/fly/3vm/`), não apaga
  Dockerfiles standalone.
- Compose standalone em `deploy/*-standalone/` permanece para dev local.

### D6 — Supervisor e falhas

- `supervisord` com `autorestart=true` por processo.
- Health agregado: falha de **chatbot** ou **n8n** → unhealthy (bot morto).
- Falha de **portal/catalogo** → unhealthy **opcional** no MVP (ou só log) para não
  matar o bot se o CRM cair — **decisão MVP:** portal/catalogo unhealthy **não** derruba
  o health do Fly proxy do bot; checagem Fly aponta para `/healthz` que exige
  n8n + chatbot + estoque + pg connectivity.

### D7 — Memória do app

| Orçamento 1024 MB | Orçamento 1536 MB (recomendado lab) |
|-------------------|--------------------------------------|
| n8n ~400–500 | n8n ~400–500 |
| 5× uvicorn slim ~80–120 cada | folga |
| Caddy + OS ~100 | folga |
| **Risco OOM no n8n** | **Mais seguro** |

**Default do plano:** `shared-cpu-1x` **1536 MB** no app (~US$ +2–3 vs 1 GB).

---

## 3. Mapa de arquivos (criar / modificar)

| Path | Responsabilidade |
|------|------------------|
| `deploy/fly/3vm/README.md` | Runbook cutover / rollback |
| `deploy/fly/3vm/Dockerfile.app` | Imagem multi-serviço (Python apps + n8n node + Caddy + supervisord) |
| `deploy/fly/3vm/supervisord.conf` | Processos e prioridades |
| `deploy/fly/3vm/Caddyfile` | Roteamento Host → porta |
| `deploy/fly/3vm/fly.app.toml` | App `app2037`, volume(s), 1536 MB, always-on |
| `deploy/fly/3vm/fly.canal.toml` | Evolution only (baseado em `deploy/fly/evolution/fly.toml`) |
| `deploy/fly/3vm/Dockerfile.worker` | **VM 4** — Chromium + entrypoint on-demand (sem n8n/portal) |
| `deploy/fly/3vm/fly.worker.toml` | App worker-only (`motor2037` ou `worker2037`); sem min_machines HTTP always-on |
| `deploy/fly/3vm/entrypoint-app.sh` | Migrations (alembic de cada serviço) + supervisord |
| `deploy/fly/3vm/env.example` | Lista de env vars sem valores secretos |
| `n8n/update_live_workflow.js` | Flags para hosts localhost no perfil 3vm |
| `deploy/fly/up-all.sh` / `down-all.sh` | Perfil `--3vm` |
| `docs/referencia-viva/contexto-compacto.md` | Checkpoint pós-cutover |
| `docs/referencia-viva/go-live-chatbot.md` | URLs e checklist 3vm |

**Não fazer no MVP 3-VM:** fundir código FastAPI em um único `app.main`; reescrever n8n em Python.

---

## 4. Fases e tasks

### Task 0: Baseline e critérios de aceite

**Files:**
- Create: `deploy/fly/3vm/README.md` (seção “Aceite”)

**Critérios de aceite (cutover OK só se todos verdes):**

1. Evolution `loja1` state `open` após 24 h sem deploy do canal.
2. Mensagem WhatsApp de número não salvo → resposta IA (fluxo n8n 25 nós).
3. Cadastro de foto (número autorizado) grava no Estoque e aparece no Catálogo.
4. Portal login + listagem leads/estoque (pode cold? não — always-on).
5. `POST` simulação mock (sem Playwright) retorna 2xx via motor-api local.
6. `fly machine list` always-on **= 3** (pg, canal, app); workers stopped.
7. Custo invoice projetado ≤ US$ 20 compute+volumes (Cost Explorer).

- [ ] **Step 1:** Documentar os 7 critérios em `deploy/fly/3vm/README.md`.
- [ ] **Step 2:** Anotar estado atual dos apps legados (`fly apps list`) sem destruir nada.
- [ ] **Step 3:** Commit doc-only.

```bash
git add deploy/fly/3vm/README.md
git commit -m "docs: critérios de aceite arquitetura 3 VMs"
```

---

### Task 1: Scaffold do bundle `app` (local)

**Files:**
- Create: `deploy/fly/3vm/Dockerfile.app`
- Create: `deploy/fly/3vm/supervisord.conf`
- Create: `deploy/fly/3vm/Caddyfile`
- Create: `deploy/fly/3vm/entrypoint-app.sh`
- Create: `deploy/fly/3vm/env.example`
- Create: `deploy/fly/3vm/site-nginx.conf` (listen 8081; root com assets do `site/`)

**Interfaces:**
- Produz: imagem local `revy-app:3vm` que sobe n8n + 5 uvicorn + **site nginx** + Caddy.
- Consome: código existente em `chatbot-api/`, `estoque-api/`, `portal-gestao/`,
  `catalogo-publico/`, `motor-simulacao/` (só API, sem Playwright), **`site/`** (estático).

- [ ] **Step 1:** Escrever `Dockerfile.app` multi-stage:

  - Stage `python-deps`: merge requirements (pip install unificado ou venvs por serviço em
    `/srv/{chatbot,estoque,portal,catalogo,motor}`).
  - Stage `runtime`: `python:3.12-slim` + Node 20 (para n8n) **ou** copiar binários n8n
    de `n8nio/n8n:2.26.8` (preferir **multi-stage FROM n8n** + copiar Python).
  - Instalar `supervisor`, `caddy`.
  - **Não** rodar `playwright install` neste Dockerfile.

- [ ] **Step 2:** `supervisord.conf` com programas: `caddy`, `n8n`, `chatbot`, `estoque`,
  `portal`, `catalogo`, `motor_api`, **`site_nginx`** — cada um com `stdout_logfile=/dev/stdout`.

- [ ] **Step 3:** `Caddyfile` com `handle` por host (placeholders `{$PORTAL_HOST}`,
  `{$SITE_HOST}` etc.), incluindo site → `127.0.0.1:8081`.

- [ ] **Step 4:** `entrypoint-app.sh` roda em sequência (fail-fast):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /srv/chatbot && alembic upgrade head
cd /srv/estoque && alembic upgrade head
cd /srv/portal && alembic upgrade head
cd /srv/motor && alembic upgrade head
# catalogo sem alembic se N/A
exec /usr/bin/supervisord -n -c /etc/supervisord.conf
```

- [ ] **Step 5:** Build local:

```bash
docker build -f deploy/fly/3vm/Dockerfile.app -t revy-app:3vm .
```

Expected: exit 0.

- [ ] **Step 6:** Smoke local com `docker run` + Postgres compose (rede) — health HTTP em
  8001/8002/9000/5678 (detalhar env em `env.example`).

- [ ] **Step 7:** Commit scaffold.

```bash
git add deploy/fly/3vm/
git commit -m "feat(deploy): scaffold bundle 3vm app (Dockerfile + supervisor)"
```

---

### Task 2: Wiring de env e localhost

**Files:**
- Modify: configs via env only (não hardcode secrets)
- Create: `deploy/fly/3vm/env.example` (completo)
- Modify: `n8n/update_live_workflow.js` (se necessário flag `--profile 3vm`)

**Env críticos no app (exemplos sem segredos):**

```bash
# Postgres (suite-pg flycast)
CHATBOT_DATABASE_URL=postgresql://...@suite-pg.flycast:5432/chatbot
ESTOQUE_DATABASE_URL=postgresql://...@suite-pg.flycast:5432/estoque
MOTOR_DATABASE_URL=postgresql://...@suite-pg.flycast:5432/motor
# Evolution (VM canal)
CHATBOT_AUDIO_EVOLUTION_URL=http://canal2037.flycast:8080
# Co-localizados
MOTOR_URL=http://127.0.0.1:8004
ESTOQUE_API_URL=http://127.0.0.1:8002
CHATBOT_API_URL=http://127.0.0.1:8001
ESTOQUE_PUBLIC_API_URL=http://127.0.0.1:8002
```

- [ ] **Step 1:** Mapear **todas** as env vars dos `fly.toml` atuais de
  chatbot/estoque/portal/catalogo/motor/n8n → uma tabela em `env.example`.
- [ ] **Step 2:** Garantir que cada app Python lê URL por env (já o fazem via `config.py`);
  só ajustar defaults de produção se algum estiver fixo em fly.toml legado.
- [ ] **Step 3:** Atualizar publisher do workflow para emitir URLs `127.0.0.1` no perfil 3vm.
- [ ] **Step 4:** Teste: `python n8n/validate_workflow.py` (ou script existente) no JSON gerado.
- [ ] **Step 5:** Commit.

---

### Task 3: App Fly `app2037` + volumes

**Files:**
- Create: `deploy/fly/3vm/fly.app.toml`

```toml
app = "app2037"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile.app"
  # build context = repo root (fly deploy -c ... --dockerfile ...)

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

  [[http_service.checks]]
    path = "/healthz"
    interval = "20s"
    timeout = "5s"
    grace_period = "90s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "1536"

# Preferir 1 volume grande montado em /data com subdirs, ou multi-mount se Fly permitir
[[mounts]]
  source = "app_data"
  destination = "/data"
```

**Estratégia de volumes (escolher na implementação; default A):**

| Opção | Descrição |
|-------|-----------|
| **A (default)** | Volume único `app_data` 5 GB: `/data/n8n`, `/data/portal`, `/data/catalogo`, `/data/estoque`, `/data/motor` — migrar dados dos volumes antigos com `fly sftp` / machine one-off |
| **B** | Manter volumes separados se multi-mount estável no app |

- [ ] **Step 1:** `fly apps create app2037 -o crm-419` (se não existir).
- [ ] **Step 2:** Criar volume `app_data` 5gb em `gru`.
- [ ] **Step 3:** Setar secrets (copiar dos apps legados via `fly secrets list` + re-set;
  **não logar valores**).
- [ ] **Step 4:** `fly deploy -c deploy/fly/3vm/fly.app.toml --ha=false` a partir do root
  com build context correto.
- [ ] **Step 5:** Verificar `fly status -a app2037` e logs supervisord.
- [ ] **Step 6:** Commit toml + runbook de secrets (sem valores).

---

### Task 4: VM canal (Evolution isolada)

**Files:**
- Create: `deploy/fly/3vm/fly.canal.toml` (fork de `deploy/fly/evolution/fly.toml`)
- Ou reusar app `evolution2037` sem mudança de nome (preferir **reusar** para não
  perder DNS/sessão)

- [ ] **Step 1:** Confirmar `evolution2037` always-on, 512 MB, volume `evolution_instances`.
- [ ] **Step 2:** Garantir `DATABASE_CONNECTION_URI` → `suite-pg` db `evolution`.
- [ ] **Step 3:** Redis Upstash inalterado.
- [ ] **Step 4:** Webhook Evolution → URL pública do **n8n no app**  
  (`https://n8n-host/...` apontando para Caddy no `app2037`).
- [ ] **Step 5:** Testar QR/sessão `open` **sem** redeploy do app no mesmo momento.
- [ ] **Step 6:** Documentar: “nunca colocar Evolution no Dockerfile.app”.

---

### Task 5: Postgres (`suite-pg`) — sem mudança de papel

- [ ] **Step 1:** Manter 1 machine 512 MB always-on.
- [ ] **Step 2:** Conferir 4 databases e conexões a partir do app (IPv6 flycast).
- [ ] **Step 3:** Backup: snapshot volume `pg_data` antes do cutover.
- [ ] **Step 4:** Anotar restore drill residual (já no eixo E) — não bloqueia 3vm se snapshot ok.

---

### Task 6: Migração de dados (volumes SQLite / n8n / mídia)

**Ordem:**

1. Snapshot / `fly volumes snapshots create` em cada volume legado.
2. Subir `app2037` com volumes vazios **ou** copiar:
   - `portal.db` → `/data/portal/`
   - `catalogo.db` → `/data/catalogo/`
   - n8n `.n8n` → `/data/n8n/` (workflow + credenciais)
   - estoque media files → `/data/estoque/`
3. Validar checksum / contagem de arquivos.
4. Só então apontar DNS/hosts de produção para o app.

- [ ] **Step 1:** Script `deploy/fly/3vm/migrate-volumes.sh` (one-off machine ou sftp).
- [ ] **Step 2:** Dry-run em lab com apps legados ainda up (cópia a frio preferível:
  `down` controlado → copy → `up` 3vm).
- [ ] **Step 3:** Validar n8n abre UI e workflow `SBAUPjrUlYa4gtgE` (ou id atual) ativo.
- [ ] **Step 4:** Commit script.

---

### Task 7: Cutover de tráfego

**Janela:** manutenção curta (15–30 min).

- [ ] **Step 1:** `bash deploy/fly/down-all.sh` seletivo **ou** stop machines legadas
  (exceto pg + evolution até app healthy).
- [ ] **Step 2:** App 3vm healthy + canal healthy + pg healthy.
- [ ] **Step 3:** Atualizar workflow n8n (URLs localhost + evolution flycast).
- [ ] **Step 4:** Atualizar webhook Evolution → n8n no app.
- [ ] **Step 5:** Certificados / DNS: se hostnames antigos, usar `fly certs add` no `app2037`
  para `portal2037.fly.dev`, `catalogo2037.fly.dev`, `n8n2037.fly.dev`, **`site2037.fly.dev`**
  **ou** CNAME internos Fly (avaliar limite: um app, vários hosts).
- [ ] **Step 6:** Rodar critérios Task 0 (WhatsApp E2E mínimo) + smoke `https://site2037.fly.dev/health`.
- [ ] **Step 7:** Scale count 0 nos apps legados incl. **`site2037`** (não destroy na primeira semana).

**Rollback:**

1. Stop `app2037`.
2. Start machines legadas (`up-all.sh`).
3. Reverter webhook Evolution para n8n legado.
4. Volumes legados intactos se não tiver apagado.

---

### Task 8: VM 4 — Playwright (imagem e machines próprias)

**Files:**
- Create: `deploy/fly/3vm/Dockerfile.worker`
- Create: `deploy/fly/3vm/fly.worker.toml`
- Modify: fan-out / config do motor (`motor-simulacao/`) para imagem worker e app name
- Modify: secrets Machines API no `app2037` (token com permissão de start no app worker)

**Interfaces:**
- Consome: `motor-api` em `127.0.0.1:8004` (VM 3) enfileira job e acorda worker.
- Produz: 0–2 machines `shared-cpu-2x:2048MB` no app worker; idle = stopped.

- [ ] **Step 1:** Default travado: **(i)** `motor2037` vira **worker-only** (remover machine
  always-on do process `app` legado). Documentar em `deploy/fly/3vm/README.md`.
- [ ] **Step 2:** `Dockerfile.worker` baseado em `motor-simulacao/Dockerfile` com
  Playwright; **sem** copiar portal/n8n/chatbot. Entrypoint =
  `scripts/on-demand-worker-entrypoint.sh` (ou equivalente atual).
- [ ] **Step 3:** `fly.worker.toml`: **sem** `min_machines_running = 1` de HTTP público;
  sem `auto_stop` de serviço web se não houver service — machines geridas pela API.
- [ ] **Step 4:** Deploy só da imagem worker; garantir machines `motor-worker-*` existem
  em estado **stopped** (ou create on first job).
- [ ] **Step 5:** `MOTOR_URL` no app = `http://127.0.0.1:8004`; secrets de fan-out apontam
  para app worker + imagem nova.
- [ ] **Step 6:** Smoke mock: **nenhuma** VM 4 sobe.
- [ ] **Step 7:** Smoke real (1 banco): 1 machine 2 GB **started** → job → **stopped** após idle.
- [ ] **Step 8:** `fly machine list` nos 3 apps always-on = started; workers = stopped
  (exceto durante o smoke).
- [ ] **Step 9:** Commit Dockerfile.worker + fly.worker.toml + docs.

```bash
git add deploy/fly/3vm/Dockerfile.worker deploy/fly/3vm/fly.worker.toml deploy/fly/3vm/README.md
git commit -m "feat(deploy): VM 4 worker Playwright isolada do app 3vm"
```

---

### Task 9: Scripts ops e docs

**Files:**
- Modify: `deploy/fly/up-all.sh` → flag `--3vm`
- Modify: `deploy/fly/down-all.sh` → para pg+canal+app
- Modify: `docs/referencia-viva/contexto-compacto.md` (checkpoint)
- Modify: `docs/nao-plano/historico/README.md` (índice)
- Modify: `docs/referencia-viva/go-live-chatbot.md` (URLs)

- [ ] **Step 1:** `up-all.sh --3vm` sobe só as 3 machines + garante autostop=off.
- [ ] **Step 2:** Documentar decommission: após 7 dias estáveis, `fly apps destroy`
  legados (pedido explícito do dono).
- [ ] **Step 3:** Atualizar custo esperado no contexto compacto.
- [ ] **Step 4:** Commit final docs.

---

### Task 10: Hardening pós-MVP (backlog, não bloqueia)

- [ ] Métricas de RSS por processo (log periódico) — ajustar 1536→1024 se sobrar.
- [ ] Separar health bot vs health CRM (dois checks / dois ports se necessário).
- [ ] CI que rebuilda `app2037` quando `site/` muda (landing).
- [ ] Opcional: eliminar n8n (fluxo no Chatbot) → app mais leve; **outro plano**.
- [ ] Reservas Fly 40% se uso mensal estável.

---

## 5. O que **não** entra neste plano

- Reescrever monorepo em monólito de código.
- Managed Postgres (MPG) — manter self-managed até go-live loja real (#7).
- Multi-região / HA.
- Fundir Evolution na VM app.
- Ligar workers RPA (VM 4) 24/7.
- Colocar Chromium / `playwright install` no `Dockerfile.app` (VM 3).

---

## 6. Riscos e mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| OOM no app (n8n + 5 uvicorn) | Bot cai | 1536 MB; limites `memory` no supervisord; monitorar |
| Deploy app reinicia n8n | Workflow breve down | Health grace 90s; janela controlada; Evolution isolada |
| Multi-host no mesmo app Fly | Cert/DNS | Path-based fallback; ou IPs dedicados |
| Migração volume corrompe n8n | Perde workflow | Snapshot + backup SQLite n8n antes |
| localhost quebra testes de tenancy | Integração | Manter tokens; só muda host |
| Process group Fly ≠ 1 VM | Contar errado | **Proibido** usar process groups para “parecer 1”; supervisor na mesma machine |

---

## 7. Cronograma sugerido

| Fase | Duração | Entrega |
|------|---------|---------|
| Task 0–1 | 1–2 dias | Bundle builda local |
| Task 2–3 | 1–2 dias | `app2037` no Fly com health |
| Task 4–6 | 1 dia | Canal + dados migrados |
| Task 7–8 | 0,5–1 dia | Cutover + **VM 4** worker smoke (start/stop) |
| Task 9 | 0,5 dia | Ops/docs |
| Observação | 7 dias | Só então destroy legados |

**Total:** ~1 semana de engenharia + 1 semana de observação.

---

## 8. Resumo executivo

| | Antes | Depois |
|---|-------|--------|
| VMs always-on | 9 | **3** (data + canal + app) |
| VM Playwright | misturada no ecossistema motor | **VM 4 própria**, 2 GB, **stopped** idle |
| Chromium na VM do bot | risco se unificar mal | **proibido** |
| Custo compute+vol always-on | ~US$ 35–45 | **~US$ 13–18** |
| Custo RPA | workers stopped / sob demanda | **igual**, explícito como classe 4 |
| Sessão WhatsApp | Evolution dedicada | **igual (isolada)** |
| Código produtos | pastas separadas | **igual** |
| Deploy lab | 1 app por produto | **pg + canal + app bundle (incl. site) + worker image** |
| Site | VM `site2037` dedicada | **nginx na VM 3**; legado scale 0 |

### Mapa mental final

```
Always-on:   [1 pg] [2 evolution] [3 app: n8n+APIs+motor-api]
On-demand:   [4 worker-playwright ×0..2]   ← VM própria, imagem própria
```

---

## Self-review

1. **Spec coverage:** 3 always-on, **VM 4 Playwright dedicada**, site **na VM 3**, custo,
   isolamento Evolution, localhost, volumes, cutover, rollback, monorepo — seções 1.2, D3, D4, Task 8.
2. **Placeholders:** sem TBD de comportamento; opções A/B de volume com default A;
   worker default = `motor2037` worker-only.
3. **Consistência:** nomes `app2037`, `evolution2037`, `suite-pg`, `motor2037` worker,
   portas 8001–8004/9000/5678/8080 alinhadas; proibição de Chromium na VM 3 repetida em
   constraints, D3 e “não entra”.
