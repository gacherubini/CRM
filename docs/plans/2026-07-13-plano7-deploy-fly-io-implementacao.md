# Plano #7 — Deploy da suíte no Fly.io (implementação)

> **Para operadores/agentes:** SUB-SKILL RECOMENDADA — use `superpowers:executing-plans` para
> executar este plano tarefa-a-tarefa, com checkpoint de revisão entre fases. Os passos usam
> checkbox (`- [ ]`) para rastreio.
>
> **Fonte da verdade:** `docs/plans/2026-07-13-plano7-deploy-fly-io-design.md`. Este documento
> DETALHA aquele design (7 apps, região `gru`, Postgres self-managed no teste → MPG no go-live,
> inventário de secrets §5, ordem de deploy §6, riscos §7). Onde este plano decide algo que o
> design deixou em aberto, o ponto está marcado com **[DECISÃO — revisar]**.

**Objetivo:** subir os 5 produtos + Evolution + n8n em produção real no Fly.io (região `gru`),
com o bot WhatsApp ligado, seguindo a ordem de deploy que resolve o ovo-e-galinha dos tokens.

**Arquitetura:** 7 apps Fly. Serviços que compartilham imagem viram *process groups* (motor =
`api`+`worker`; estoque = `api`+`outbox`). Apps HTTP request-resposta usam autostop→zero;
`motor-worker`, `estoque-outbox`, `evolution`, `n8n`, Postgres ficam always-on. Postgres
self-managed com 4 bancos + Upstash Redis. Comunicação interna por `.flycast`.

**Stack:** Fly.io (Machines, Volumes, Postgres self-managed, flycast/6PN), Upstash Redis,
Python 3.12 / FastAPI / Alembic (motor, estoque, chatbot, portal, catalogo), Evolution API,
n8n, Gemini (credencial dentro do n8n).

## Constraints globais

- Região única: **`gru`** (São Paulo) em TODOS os apps e volumes (`--region gru`).
- **NUNCA** ler, versionar ou colar segredos reais. Segredos vão só via `fly secrets set`.
  Os arquivos `deploy/motor-standalone/.env` e `deploy/chatbot-standalone/.env` contêm
  segredos reais — **proibido abrir**. Use apenas os `.env.example`.
- Este plano **não** executa `fly`, **não** cria recursos e **não** cria os arquivos `fly.toml`.
  O conteúdo de cada `fly.toml` está inline para o executor criar no momento do deploy.
- Geradores de segredo (use exatamente estes):
  - Fernet: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - Token aleatório: `python -c "import secrets; print(secrets.token_urlsafe(32))"` (ou `openssl rand -hex 32`)
- Tokens de serviço (`MOTOR_TOKEN`, `ESTOQUE_API_TOKEN`, `CHATBOT_API_TOKEN`) **não** são
  inventados: são emitidos pela CLI de cada serviço DEPOIS que ele sobe (ver Fase 3, 4, 6).
- Nomes de app usados neste plano (ajuste o sufixo se já existirem): `motor`, `estoque`,
  `chatbot`, `portal`, `catalogo`, `evolution`, `n8n`, e o Postgres `suite-pg`.
- Onde os apps têm porta interna: motor/estoque/chatbot = **8000**; portal = **9000**;
  catalogo = **8000**; evolution = **8080**; n8n = **5678**.

---

## Decisões que este plano tomou (revisar antes de executar)

1. **[DECISÃO — revisar] `.flycast`, não `.internal`, para HTTP entre apps.** Os apps HTTP
   internos escalam a zero (autostop). `<app>.internal` resolve direto para as instâncias (6PN)
   e **não passa pelo proxy do Fly** — logo não acorda uma máquina parada. `<app>.flycast`
   roteia pelo proxy Fly, que respeita `auto_start_machines` e faz load-balancing. Para chamada
   HTTP de app privado que pode estar dormindo, **`.flycast` é o correto**. Postgres (always-on,
   conexão TCP direta) usa `.internal`.
2. **[DECISÃO — revisar] `estoque` fica privado (sem IP público).** O design (§2) diz "api
   público read + privado", mas o único consumidor da leitura pública é o `catalogo` (que roda
   no mesmo org e alcança `estoque.flycast`). O comprador nunca chama o estoque direto — chama o
   `catalogo` web, que faz a chamada server-side. Manter `estoque` privado reduz superfície. Se
   surgir consumidor externo do catálogo público, alocar IP com `fly ips allocate-v6 -a estoque`.
3. **[DECISÃO — revisar] Migrations via `release_command`, não no CMD.** Os Dockerfiles rodam
   `alembic upgrade head && uvicorn`. Com process groups (2 máquinas subindo juntas) isso corre
   risco de corrida no Alembic. Este plano roda a migration uma única vez por deploy via
   `[deploy] release_command`, e cada processo roda só o servidor/worker. Mantém-se `*_SKIP_INIT=1`.
4. **[DECISÃO — revisar] `ESTOQUE_OUTBOX_KEY` gerada offline com o one-liner Fernet.** É uma
   chave Fernet (a CLI `gerar-chave-outbox` só imprime uma). Gerar antes evita um redeploy.
5. **[DECISÃO — revisar] Porta interna 8000 exposta no flycast** dos apps privados via bloco
   `[[services]]` (em vez de `[http_service]`, que só publica 80/443). Assim as URLs internas
   ficam `http://<app>.flycast:8000`, batendo com o inventário §5 do design.

---

## Fase 0 — Pré-requisitos

### Task 0.1: Conta, CLI e organização

**Critério de sucesso:** `fly auth whoami` retorna o e-mail da conta; `fly orgs list` mostra a
org de trabalho; `gru` disponível.

- [ ] **Passo 1: Instalar/atualizar flyctl**

Windows (PowerShell): `pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"`
Verificar: `fly version` (>= 0.3).

- [ ] **Passo 2: Login**

`fly auth login`
Verificar: `fly auth whoami` imprime o e-mail da conta.

- [ ] **Passo 3: Confirmar org e cartão**

`fly orgs list`
Anote o slug da org (ex.: `personal`). Confirme meio de pagamento ativo no dashboard
(https://fly.io/dashboard) — apps always-on cobram por máquina-segundo.

- [ ] **Passo 4: Reunir insumos externos (não são secrets Fly ainda)**

- Número/chip WhatsApp dedicado, com o aparelho em mãos para escanear o QR (Fase 7).
- **Chave da API Google Gemini** já criada e testada localmente — será cadastrada **dentro do
  n8n** (Fase 8), não como secret Fly.
- `CONFIG_SESSION_PHONE_VERSION` atual da Evolution (default do compose: `2.3000.1033773198`).

**Verificação da fase:** `fly platform regions | grep gru` lista São Paulo.

---

## Fase 1 — Postgres self-managed + 4 bancos + Redis

### Task 1.1: Criar o cluster Postgres self-managed

**Critério de sucesso:** `fly status -a suite-pg` mostra a máquina `started`; a connection string
interna foi anotada (usuário `postgres` + senha gerada).

- [ ] **Passo 1: Criar o Postgres (self-managed, nó único, pequeno)**

```bash
fly postgres create \
  --name suite-pg \
  --region gru \
  --org <sua-org> \
  --vm-size shared-cpu-1x \
  --volume-size 3 \
  --initial-cluster-size 1
```

Guarde a saída (usuário `postgres`, **senha gerada** e hostname `suite-pg.internal`). A senha
aparece **uma vez** — copie para o gerenciador de segredos.

- [ ] **Passo 2: Verificar**

`fly status -a suite-pg` → estado `started`.
`fly postgres connect -a suite-pg -c "SELECT version();"` → imprime a versão do PostgreSQL.

### Task 1.2: Criar os 4 bancos

**Critério de sucesso:** `\l` lista `motor`, `estoque`, `chatbot`, `evolution`.

- [ ] **Passo 1: Criar bancos**

```bash
fly postgres db create motor    -a suite-pg
fly postgres db create estoque  -a suite-pg
fly postgres db create chatbot  -a suite-pg
fly postgres db create evolution -a suite-pg
```

- [ ] **Passo 2: Verificar**

`fly postgres connect -a suite-pg -c "\l"` → os 4 bancos aparecem.

- [ ] **Passo 3: Montar as connection strings (guardar, não versionar)**

Substitua `<PG_PASS>` pela senha do Task 1.1 (host interno `suite-pg.internal:5432`, user `postgres`):

- motor:     `postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/motor`
- estoque:   `postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/estoque`
- chatbot:   `postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/chatbot`
- evolution: `postgresql://postgres:<PG_PASS>@suite-pg.internal:5432/evolution` (driver plano, sem `+psycopg`)

### Task 1.3: Provisionar Upstash Redis

**Critério de sucesso:** URL `redis://...` anotada para `CACHE_REDIS_URI`.

- [ ] **Passo 1: Criar Redis (Upstash, região gru, tier free)**

```bash
fly redis create --name suite-redis --region gru --org <sua-org>
```

Escolha o plano gratuito quando solicitado. Guarde a URL `redis://default:<token>@...upstash.io:6379`.

- [ ] **Passo 2: Recuperar a URL depois (se perder)**

`fly redis status suite-redis` → mostra a connection string (`CACHE_REDIS_URI`).

**Verificação da fase:** 4 bancos criados + 1 URL Redis anotada. Segredos guardados fora do repo.

---

## Fase 2 — App `motor` (api + worker)  ·  Passo 2 da §6

### Task 2.1: Criar app, volume e secrets do motor

**Arquivos:**
- Criar (no momento do deploy): `motor-simulacao/fly.toml`

**Interfaces:**
- Consome: `DATABASE_URL` do banco `motor` (Task 1.2).
- Produz: `MOTOR_TOKEN` (Task 2.3) consumido por chatbot e portal; `MOTOR_URL=http://motor.flycast:8000`.

**Critério de sucesso:** `fly status -a motor` mostra `api` e `worker`; `fly secrets list -a motor`
lista as 3 secrets; volume `motor_data` existe em `gru`.

- [ ] **Passo 1: Criar o app (sem deployar ainda)**

`fly apps create motor --org <sua-org>`

- [ ] **Passo 2: Criar o volume do worker (storage_state + screenshots)**

`fly volumes create motor_data --region gru --size 1 -a motor`

- [ ] **Passo 3: Gerar e setar as secrets**

```bash
MOTOR_ENC=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
MOTOR_METRICS=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
fly secrets set -a motor \
  MOTOR_ENCRYPTION_KEY="$MOTOR_ENC" \
  MOTOR_METRICS_TOKEN="$MOTOR_METRICS" \
  DATABASE_URL="postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/motor"
```

- [ ] **Passo 4: Verificar**

`fly secrets list -a motor` → 3 nomes: `MOTOR_ENCRYPTION_KEY`, `MOTOR_METRICS_TOKEN`, `DATABASE_URL`.

### Task 2.2: Criar `motor-simulacao/fly.toml` e deployar

**Critério de sucesso:** deploy conclui; `api` responde `/health/ready`; `worker` sobe Xvfb+Chromium.

- [ ] **Passo 1: Criar `motor-simulacao/fly.toml` com este conteúdo**

```toml
app = "motor"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[deploy]
  # Roda a migration UMA vez por deploy (evita corrida entre api e worker).
  release_command = "alembic upgrade head"

[env]
  MOTOR_ENV = "production"
  MOTOR_SKIP_INIT = "1"
  MOTOR_BROWSER_HEADLESS = "0"
  PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL = "0"
  MOTOR_SCREENSHOT_DIR = "/srv/data/screenshots"
  MOTOR_STORAGE_STATE_DIR = "/srv/data/storage_state"
  DISPLAY = ":99"

[processes]
  api = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
  worker = "/srv/scripts/worker-entrypoint.sh"

# API privada exposta no flycast na porta 8000 (autostop → zero).
[[services]]
  processes = ["api"]
  internal_port = 8000
  protocol = "tcp"
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  [[services.ports]]
    port = 8000
    handlers = ["http"]
  [[services.http_checks]]
    path = "/health/ready"
    interval = "15s"
    timeout = "3s"

# Worker: Chromium headed sob Xvfb — always-on, sem serviço HTTP.
[[vm]]
  processes = ["worker"]
  size = "shared-cpu-2x"
  memory = "2048"

[[vm]]
  processes = ["api"]
  size = "shared-cpu-1x"
  memory = "512"

[[mounts]]
  source = "motor_data"
  destination = "/srv/data"
  processes = ["worker"]
```

- [ ] **Passo 2: Garantir 1 worker sempre ligado**

O `min_machines_running` só vale para grupos com `[[services]]`. Para o `worker` (sem serviço),
fixe a contagem após o primeiro deploy: `fly scale count worker=1 -a motor`.

- [ ] **Passo 3: Deployar**

`cd motor-simulacao && fly deploy -a motor`
Esperado: `release_command` roda `alembic upgrade head` sem erro; máquinas `api` e `worker` sobem.

- [ ] **Passo 4: Verificar api**

`fly ssh console -a motor -C "sh -c 'wget -qO- http://localhost:8000/health/ready'"`
Esperado: resposta 200 / JSON de readiness.

- [ ] **Passo 5: Verificar worker (Xvfb subiu)**

`fly logs -a motor` → linhas do `worker-entrypoint`; sem "Xvfb não subiu" nem "Missing X server".

### Task 2.3: Emitir o `MOTOR_TOKEN` via CLI

**Interfaces:**
- Produz: `MOTOR_TOKEN` (string `token=...`) para os apps chatbot e portal.

**Critério de sucesso:** um `token=...` foi impresso e guardado no gerenciador de segredos.

- [ ] **Passo 1: Criar o cliente de API**

`fly ssh console -a motor -C "sh -c 'cd /srv && python -m app.cli criar-cliente --nome \"loja\"'"`
Esperado: imprime `cliente_id=<uuid>`. Anote o `cliente_id`.

- [ ] **Passo 2: Criar a credencial (o token)**

`fly ssh console -a motor -C "sh -c 'cd /srv && python -m app.cli criar-credencial --cliente-id <cliente_id> --nome \"chatbot-portal\"'"`
Esperado: imprime `Guarde o token agora...` e `token=<MOTOR_TOKEN>`. **Guarde** — não é recuperável.

**Verificação da fase:** `/health/ready` 200 + `MOTOR_TOKEN` em mãos. (Teste do Santander RPA
fica para a Fase 10 — é o maior risco, ver seção Riscos.)

---

## Fase 3 — App `estoque` (api + outbox)  ·  Passo 3 da §6

### Task 3.1: Criar app e secrets do estoque

**Interfaces:**
- Consome: `DATABASE_URL` do banco `estoque`.
- Produz: `ESTOQUE_API_TOKEN` (token da loja, Task 3.3) para chatbot e portal;
  `ESTOQUE_PUBLIC_API_TOKEN` (Task 3.3) para catalogo; `ESTOQUE_API_URL=http://estoque.flycast:8000`.

**Critério de sucesso:** app criado; `fly secrets list -a estoque` lista `ESTOQUE_OUTBOX_KEY` e `DATABASE_URL`.

- [ ] **Passo 1: Criar o app**

`fly apps create estoque --org <sua-org>`

- [ ] **Passo 2: Gerar `ESTOQUE_OUTBOX_KEY` (Fernet) e setar secrets**

```bash
ESTOQUE_OUTBOX=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
fly secrets set -a estoque \
  ESTOQUE_OUTBOX_KEY="$ESTOQUE_OUTBOX" \
  DATABASE_URL="postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/estoque"
```

- [ ] **Passo 3: Verificar** — `fly secrets list -a estoque` mostra os 2 nomes.

### Task 3.2: Criar `estoque-api/fly.toml` e deployar

**Critério de sucesso:** deploy conclui; `api` responde `/health/ready`; `outbox` roda `python -m app.worker`.

- [ ] **Passo 1: Criar `estoque-api/fly.toml`**

```toml
app = "estoque"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "alembic upgrade head"

[env]
  ESTOQUE_SKIP_INIT = "1"
  ESTOQUE_PUBLIC_RATE_LIMIT = "120"
  ESTOQUE_OUTBOX_INTERVALO = "5"

[processes]
  api = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
  outbox = "python -m app.worker"

[[services]]
  processes = ["api"]
  internal_port = 8000
  protocol = "tcp"
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  [[services.ports]]
    port = 8000
    handlers = ["http"]
  [[services.http_checks]]
    path = "/health/ready"
    interval = "15s"
    timeout = "3s"

[[vm]]
  processes = ["api"]
  size = "shared-cpu-1x"
  memory = "512"

[[vm]]
  processes = ["outbox"]
  size = "shared-cpu-1x"
  memory = "256"
```

- [ ] **Passo 2: Deployar** — `cd estoque-api && fly deploy -a estoque`

- [ ] **Passo 3: Garantir outbox always-on** — `fly scale count outbox=1 -a estoque`

- [ ] **Passo 4: Verificar** —
`fly ssh console -a estoque -C "sh -c 'wget -qO- http://localhost:8000/health/ready'"` → 200.

### Task 3.3: Emitir tokens do estoque (loja + leitura pública)

**Interfaces:**
- Produz: `ESTOQUE_API_TOKEN` (papel dono; escrita/lookup por placa) e `ESTOQUE_PUBLIC_API_TOKEN`
  (papel leitura; catálogo). Anote também o **slug** da loja (usar o MESMO no chatbot).

**Critério de sucesso:** dois `TOKEN:` impressos e guardados; slug definido (ex.: `moto-center`).

- [ ] **Passo 1: Criar a loja + token de serviço (dono)**

`fly ssh console -a estoque -C "sh -c 'cd /srv && python -m app.cli criar-loja --nome \"Moto Center\" --slug moto-center --whatsapp 5511999999999'"`
Esperado: `Loja criada... slug=moto-center` e `TOKEN (guarde agora...): <ESTOQUE_API_TOKEN>`.

- [ ] **Passo 2: Criar credencial dedicada de leitura para o catálogo**

`fly ssh console -a estoque -C "sh -c 'cd /srv && python -m app.cli criar-credencial --slug moto-center --papel operador'"`
Esperado: `TOKEN (guarde agora...): <ESTOQUE_PUBLIC_API_TOKEN>`. **[DECISÃO — revisar]** usar
credencial separada para o catálogo isola o token público do token de escrita; se preferir
reaproveitar o token da loja, pule este passo e use `ESTOQUE_API_TOKEN` no catálogo.

**Verificação da fase:** `/health/ready` 200 + `ESTOQUE_API_TOKEN` + `ESTOQUE_PUBLIC_API_TOKEN` em mãos.

---

## Fase 4 — App `catalogo` (público)  ·  Passo 4 da §6

### Task 4.1: Criar app, volume e secrets do catalogo

**Interfaces:**
- Consome: `ESTOQUE_PUBLIC_API_TOKEN` (Task 3.3), `ESTOQUE_PUBLIC_API_URL=http://estoque.flycast:8000`.
- Produz: `CATALOGO_PUBLIC_BASE_URL=https://catalogo.fly.dev` (vitrine pública).

**Critério de sucesso:** app + volume `catalogo_data` criados; secret `ESTOQUE_PUBLIC_API_TOKEN` setada.

- [ ] **Passo 1: Criar app e volume**

```bash
fly apps create catalogo --org <sua-org>
fly volumes create catalogo_data --region gru --size 1 -a catalogo
```

- [ ] **Passo 2: Setar a secret (token) — as URLs não-sensíveis vão no fly.toml [env]**

`fly secrets set -a catalogo ESTOQUE_PUBLIC_API_TOKEN="<ESTOQUE_PUBLIC_API_TOKEN>"`

### Task 4.2: Criar `catalogo-publico/fly.toml` e deployar

**Critério de sucesso:** `https://catalogo.fly.dev/health/ready` responde 200; a vitrine lista veículos.

- [ ] **Passo 1: Criar `catalogo-publico/fly.toml`**

```toml
app = "catalogo"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[env]
  ESTOQUE_PUBLIC_API_URL = "http://estoque.flycast:8000"
  CATALOGO_DATABASE_PATH = "/data/catalogo.db"
  CATALOGO_PUBLIC_BASE_URL = "https://catalogo.fly.dev"
  CATALOGO_SECURE_COOKIE = "1"
  CATALOGO_PAGE_SIZE = "12"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  [[http_service.http_checks]]
    path = "/health/ready"
    interval = "15s"
    timeout = "3s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"

[[mounts]]
  source = "catalogo_data"
  destination = "/data"
```

> Se ligar o funil Catálogo→Chatbot depois, adicionar (só após a Fase 5):
> `fly secrets set -a catalogo CATALOGO_EVENTS_TOKEN="<CHATBOT_API_TOKEN>"` e no `[env]`
> `CATALOGO_EVENTS_URL = "http://chatbot.flycast:8000/v1/integracoes/catalogo/interesses"`.

- [ ] **Passo 2: Deployar** — `cd catalogo-publico && fly deploy -a catalogo`

- [ ] **Passo 3: Verificar** —
`curl -s https://catalogo.fly.dev/health/ready` → 200. Abrir a URL no navegador: a vitrine
carrega veículos do estoque (confirma que `estoque.flycast` acorda e responde).

**Verificação da fase:** vitrine pública no ar, consumindo o estoque via flycast.

---

## Fase 5 — App `chatbot` (api)  ·  Passo 5 da §6

### Task 5.1: Criar app e secrets do chatbot

**Interfaces:**
- Consome: `MOTOR_TOKEN` (Task 2.3), `ESTOQUE_API_TOKEN` (Task 3.3), banco `chatbot`.
- Produz: `CHATBOT_API_TOKEN` (Task 5.3) para o portal e para o n8n; `CHATBOT_API_URL=http://chatbot.flycast:8000`.

**Critério de sucesso:** `fly secrets list -a chatbot` lista `DATABASE_URL`, `MOTOR_TOKEN`, `ESTOQUE_API_TOKEN`.

- [ ] **Passo 1: Criar app** — `fly apps create chatbot --org <sua-org>`

- [ ] **Passo 2: Setar secrets (tokens + DB). URLs internas vão no [env] do fly.toml.**

```bash
fly secrets set -a chatbot \
  DATABASE_URL="postgresql+psycopg://postgres:<PG_PASS>@suite-pg.internal:5432/chatbot" \
  MOTOR_TOKEN="<MOTOR_TOKEN>" \
  ESTOQUE_API_TOKEN="<ESTOQUE_API_TOKEN>"
```

### Task 5.2: Criar `chatbot-api/fly.toml` e deployar

**Critério de sucesso:** deploy conclui; `/health/ready` 200; `SIMULATION_PROVIDER=http` ativo.

- [ ] **Passo 1: Criar `chatbot-api/fly.toml`**

```toml
app = "chatbot"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "alembic upgrade head"

[env]
  CHATBOT_SKIP_INIT = "1"
  SIMULATION_PROVIDER = "http"
  MOTOR_URL = "http://motor.flycast:8000"
  ESTOQUE_API_URL = "http://estoque.flycast:8000"
  ESTOQUE_PUBLIC_URL = "http://estoque.flycast:8000"
  MOTOR_REQUEST_TIMEOUT = "5"
  MOTOR_POLL_TIMEOUT = "20"
  MOTOR_POLL_INTERVAL = "0.5"
  ESTOQUE_REQUEST_TIMEOUT = "8"

[processes]
  api = "uvicorn app.main:app --host 0.0.0.0 --port 8000"

[[services]]
  processes = ["api"]
  internal_port = 8000
  protocol = "tcp"
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  [[services.ports]]
    port = 8000
    handlers = ["http"]
  [[services.http_checks]]
    path = "/health/ready"
    interval = "15s"
    timeout = "3s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"
```

- [ ] **Passo 2: Deployar** — `cd chatbot-api && fly deploy -a chatbot`

- [ ] **Passo 3: Verificar** —
`fly ssh console -a chatbot -C "sh -c 'wget -qO- http://localhost:8000/health/ready'"` → 200.

### Task 5.3: Criar loja no chatbot + emitir `CHATBOT_API_TOKEN` + autorizar número

**Interfaces:**
- Produz: `CHATBOT_API_TOKEN` para o portal (e para o webhook do n8n, se usar autenticação).
- Usa o **mesmo slug** da loja do estoque (`moto-center`) e o nome da instância Evolution (`loja1`).

**Critério de sucesso:** `token=...` guardado; número do dono autorizado para cadastro E5.

- [ ] **Passo 1: Criar a loja (gera o token de serviço)**

`fly ssh console -a chatbot -C "sh -c 'cd /srv && python -m app.cli criar-loja --nome \"Moto Center\" --slug moto-center --instance loja1 --whatsapp 5511999999999'"`
Esperado: `Loja criada... instance=loja1` e `TOKEN (guarde agora...): <CHATBOT_API_TOKEN>`.

- [ ] **Passo 2: Autorizar o número do dono (cadastro de veículo via WhatsApp — E5)**

`fly ssh console -a chatbot -C "sh -c 'cd /srv && python -m app.cli autorizar-numero --slug moto-center --telefone 5511999999999 --papel dono'"`
Esperado: `Número autorizado: 5511999999999 papel=dono ativo=True`.

**Verificação da fase:** `/health/ready` 200 + `CHATBOT_API_TOKEN` em mãos + loja/instância `loja1` criada.

---

## Fase 6 — App `portal` (público)  ·  Passo 6 da §6

### Task 6.1: Criar app, volume e secrets do portal

**Interfaces:**
- Consome: `MOTOR_TOKEN`, `ESTOQUE_API_TOKEN`, `CHATBOT_API_TOKEN` (das fases 2, 3, 5).

**Critério de sucesso:** app + volume `portal_data` criados; 6 secrets setadas.

- [ ] **Passo 1: Criar app e volume**

```bash
fly apps create portal --org <sua-org>
fly volumes create portal_data --region gru --size 1 -a portal
```

- [ ] **Passo 2: Gerar segredos próprios e setar todas as secrets**

```bash
PORTAL_SESSION=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
PORTAL_HMAC=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
PORTAL_ENC=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
fly secrets set -a portal \
  PORTAL_SESSION_SECRET="$PORTAL_SESSION" \
  PORTAL_IDENTITY_HMAC_SECRET="$PORTAL_HMAC" \
  PORTAL_ENCRYPTION_KEY="$PORTAL_ENC" \
  MOTOR_TOKEN="<MOTOR_TOKEN>" \
  ESTOQUE_API_TOKEN="<ESTOQUE_API_TOKEN>" \
  CHATBOT_API_TOKEN="<CHATBOT_API_TOKEN>"
```

> `PORTAL_ENCRYPTION_KEY` (Fernet) cifra em repouso as credenciais dos bancos guardadas no portal.

### Task 6.2: Criar `portal-gestao/fly.toml` e deployar

**Critério de sucesso:** `https://portal.fly.dev` abre a tela de login (porta interna **9000**).

- [ ] **Passo 1: Criar `portal-gestao/fly.toml`**

```toml
app = "portal"
primary_region = "gru"

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "alembic upgrade head"

[env]
  PORTAL_DATABASE_URL = "sqlite:////data/portal.db"
  PORTAL_SECURE_COOKIE = "1"
  MOTOR_URL = "http://motor.flycast:8000"
  ESTOQUE_API_URL = "http://estoque.flycast:8000"
  CHATBOT_API_URL = "http://chatbot.flycast:8000"

[processes]
  web = "uvicorn app.main:app --host 0.0.0.0 --port 9000"

[http_service]
  processes = ["web"]
  internal_port = 9000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  [[http_service.http_checks]]
    path = "/health/ready"
    interval = "15s"
    timeout = "3s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"

[[mounts]]
  source = "portal_data"
  destination = "/data"
```

> A migration roda no `release_command`. Como o SQLite está no volume `portal_data`, o
> `release_command` precisa do volume: o Fly executa o release numa máquina do app (que tem o
> mount). Se o release falhar por não achar `/data`, rode a migration via
> `fly ssh console -a portal -C "sh -c 'cd /srv && alembic upgrade head'"` após o primeiro deploy.

- [ ] **Passo 2: Deployar** — `cd portal-gestao && fly deploy -a portal`

- [ ] **Passo 3: Criar o usuário admin do portal (se aplicável)**

Verifique o comando de bootstrap do portal:
`fly ssh console -a portal -C "sh -c 'cd /srv && python -m app.cli --help'"` (se existir CLI de
usuário) e crie o admin. **[DECISÃO — revisar]** o portal pode criar o primeiro usuário no
primeiro acesso; confirmar o fluxo real do produto antes do go-live.

- [ ] **Passo 4: Verificar** — abrir `https://portal.fly.dev` → tela de login carrega sob HTTPS.

**Verificação da fase (Fase 1 do design — núcleo concluído):** os 5 produtos no ar; portal
conversa com motor/estoque/chatbot via flycast.

---

## Fase 7 — App `evolution` (WhatsApp)  ·  Passo 7 da §6

### Task 7.1: Criar app, volume e secrets da Evolution

**Critério de sucesso:** app + volume `evolution_instances` criados; secrets setadas.

- [ ] **Passo 1: Criar app e volume**

```bash
fly apps create evolution --org <sua-org>
fly volumes create evolution_instances --region gru --size 1 -a evolution
```

- [ ] **Passo 2: Gerar a API key e setar secrets**

```bash
EVO_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
fly secrets set -a evolution \
  EVOLUTION_API_KEY="$EVO_KEY" \
  DATABASE_CONNECTION_URI="postgresql://postgres:<PG_PASS>@suite-pg.internal:5432/evolution" \
  CACHE_REDIS_URI="<URL_UPSTASH_redis://...>"
```

Guarde `EVOLUTION_API_KEY` — o n8n vai usá-la no header `apikey`.

### Task 7.2: Criar `fly.toml` da Evolution (imagem pública) e deployar

**Critério de sucesso:** `https://evolution.fly.dev` responde; always-on (não escala a zero).

- [ ] **Passo 1: Criar `deploy/fly/evolution/fly.toml`** (sem build — imagem pública)

```toml
app = "evolution"
primary_region = "gru"

[build]
  image = "evoapicloud/evolution-api:latest"

[env]
  CONFIG_SESSION_PHONE_VERSION = "2.3000.1033773198"
  DATABASE_ENABLED = "true"
  DATABASE_PROVIDER = "postgresql"
  DATABASE_CONNECTION_CLIENT_NAME = "evolution"
  CACHE_REDIS_ENABLED = "true"
  CACHE_REDIS_PREFIX_KEY = "evolution"
  CACHE_LOCAL_ENABLED = "false"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "off"
  auto_start_machines = false
  min_machines_running = 1

[[vm]]
  size = "shared-cpu-1x"
  memory = "1024"

[[mounts]]
  source = "evolution_instances"
  destination = "/evolution/instances"
```

- [ ] **Passo 2: Deployar** — `fly deploy -a evolution -c deploy/fly/evolution/fly.toml`

- [ ] **Passo 3: Verificar app no ar** — `curl -s https://evolution.fly.dev/` → resposta da Evolution API.

### Task 7.3: Parear o WhatsApp (escanear QR uma vez → grava no volume)

**Critério de sucesso:** instância `loja1` no estado `open`; sessão persistida em `evolution_instances`.

- [ ] **Passo 1: Criar a instância (nome = o `--instance` do chatbot: `loja1`)**

```bash
curl -s -X POST https://evolution.fly.dev/instance/create \
  -H "apikey: <EVOLUTION_API_KEY>" -H "Content-Type: application/json" \
  -d '{"instanceName":"loja1","integration":"WHATSAPP-BAILEYS","qrcode":true}'
```

- [ ] **Passo 2: Obter e escanear o QR**

Abrir `https://evolution.fly.dev/instance/connect/loja1` (header `apikey`) ou usar o QR
retornado no passo 1. No celular do chip: WhatsApp → Aparelhos conectados → Conectar aparelho →
escanear.

- [ ] **Passo 3: Confirmar conexão**

`curl -s https://evolution.fly.dev/instance/connectionState/loja1 -H "apikey: <EVOLUTION_API_KEY>"`
Esperado: `"state":"open"`.

- [ ] **Passo 4: Confirmar persistência**

`fly volumes list -a evolution` mostra `evolution_instances` com uso > 0. **Não** apagar o volume
(sob risco de reparear). Reinício da máquina deve manter `state=open`.

**Verificação da fase:** WhatsApp pareado e persistido.

---

## Fase 8 — App `n8n` (orquestração + Gemini)  ·  Passo 8 da §6

### Task 8.1: Criar app, volume e secret do n8n

**Critério de sucesso:** app + volume `n8n_data` criados; `N8N_ENCRYPTION_KEY` setada.

- [ ] **Passo 1: Criar app e volume**

```bash
fly apps create n8n --org <sua-org>
fly volumes create n8n_data --region gru --size 1 -a n8n
```

- [ ] **Passo 2: Gerar e setar a encryption key (cifra as credenciais do n8n, inclusive a do Gemini)**

```bash
N8N_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
fly secrets set -a n8n N8N_ENCRYPTION_KEY="$N8N_KEY"
```

### Task 8.2: Criar `fly.toml` do n8n e deployar

**Critério de sucesso:** `https://n8n.fly.dev` abre a UI de login/setup; always-on.

- [ ] **Passo 1: Criar `deploy/fly/n8n/fly.toml`**

```toml
app = "n8n"
primary_region = "gru"

[build]
  image = "docker.n8n.io/n8nio/n8n"

[env]
  N8N_HOST = "n8n.fly.dev"
  N8N_PROTOCOL = "https"
  N8N_PORT = "5678"
  N8N_SECURE_COOKIE = "true"
  WEBHOOK_URL = "https://n8n.fly.dev/"
  GENERIC_TIMEZONE = "America/Sao_Paulo"

[http_service]
  internal_port = 5678
  force_https = true
  auto_stop_machines = "off"
  auto_start_machines = false
  min_machines_running = 1

[[vm]]
  size = "shared-cpu-1x"
  memory = "512"

[[mounts]]
  source = "n8n_data"
  destination = "/home/node/.n8n"
```

- [ ] **Passo 2: Deployar** — `fly deploy -a n8n -c deploy/fly/n8n/fly.toml`

- [ ] **Passo 3: Verificar** — abrir `https://n8n.fly.dev` → UI de setup do owner carrega.

### Task 8.3: Configurar credenciais, importar e ativar o workflow

**Critério de sucesso:** workflow ativo; credencial Gemini e Evolution cadastradas; webhook
Evolution→n8n apontado; uma mensagem de teste percorre o fluxo.

- [ ] **Passo 1: Criar o owner do n8n** (primeira tela) e logar.

- [ ] **Passo 2: Cadastrar a credencial do Gemini (na UI do n8n)**

Credentials → New → **Google Gemini (PaLM) API** → colar a chave da API Gemini (do Passo 0.4).
A chave fica cifrada por `N8N_ENCRYPTION_KEY`; **não** é secret Fly.

- [ ] **Passo 3: Cadastrar a credencial da Evolution**

Credentials → HTTP Header Auth (ou nó Evolution, se o workflow usar) → header `apikey` =
`<EVOLUTION_API_KEY>`; base URL `https://evolution.fly.dev`.

- [ ] **Passo 4: Importar o workflow** (arquivo JSON do repositório — localizar em `n8n/` ou docs)
e ajustar as URLs dos nós HTTP:
  - Chatbot: `http://chatbot.flycast:8000` (+ header `Authorization: Bearer <CHATBOT_API_TOKEN>` se o fluxo exigir).
  - Evolution (enviar mensagem): `https://evolution.fly.dev` com `apikey`.

- [ ] **Passo 5: Apontar o webhook Evolution → n8n**

```bash
curl -s -X POST https://evolution.fly.dev/webhook/set/loja1 \
  -H "apikey: <EVOLUTION_API_KEY>" -H "Content-Type: application/json" \
  -d '{"webhook":{"enabled":true,"url":"https://n8n.fly.dev/webhook/<PATH_DO_WORKFLOW>","events":["MESSAGES_UPSERT"]}}'
```

Substitua `<PATH_DO_WORKFLOW>` pelo path do nó Webhook do workflow importado.

- [ ] **Passo 6: Ativar o workflow** (toggle "Active" no n8n).

**Verificação da fase (Fase 2 do design — WhatsApp no ar):** enviar "oi" de outro número para o
WhatsApp da loja → Evolution → n8n → chatbot → resposta do bot volta no WhatsApp.

---

## Fase 9 — Backup diário

### Task 9.1: Backup diário do Postgres self-managed (pg_dump agendado)

**Critério de sucesso:** uma Machine agendada roda `pg_dump` dos 4 bancos 1x/dia e grava o dump
em armazenamento durável.

- [ ] **Passo 1: [DECISÃO — revisar] escolher destino do dump**

Recomendado: bucket S3-compatível (Fly Tigris — `fly storage create`) para durabilidade fora do
nó Postgres. Alternativa mínima: volume dedicado `pg_backups` num app de backup.

- [ ] **Passo 2: Criar app de backup + volume**

```bash
fly apps create suite-pg-backup --org <sua-org>
fly volumes create pg_backups --region gru --size 3 -a suite-pg-backup
```

- [ ] **Passo 3: Definir `deploy/fly/pg-backup/fly.toml`** (imagem `postgres:16` para ter `pg_dump`)

```toml
app = "suite-pg-backup"
primary_region = "gru"

[build]
  image = "postgres:16"

[[mounts]]
  source = "pg_backups"
  destination = "/backups"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256"
```

Secret: `fly secrets set -a suite-pg-backup PGCONN="postgresql://postgres:<PG_PASS>@suite-pg.internal:5432"`

- [ ] **Passo 4: Agendar o dump diário via Machine schedule**

```bash
fly machine run postgres:16 -a suite-pg-backup \
  --region gru --schedule daily --vm-memory 256 \
  --volume pg_backups:/backups \
  --entrypoint /bin/sh \
  -- -c 'for db in motor estoque chatbot evolution; do pg_dump "$PGCONN/$db" | gzip > /backups/$db-$(date +%F).sql.gz; done; find /backups -name "*.sql.gz" -mtime +14 -delete'
```

(`--schedule daily` faz o Fly ligar a máquina 1x/dia, rodar e desligar. Retenção 14 dias.)

- [ ] **Passo 5: Verificar** — após 1º ciclo (ou rodar `fly machine start <id> -a suite-pg-backup`
para forçar): `fly ssh console -a suite-pg-backup -C "ls -la /backups"` mostra 4 `.sql.gz`.

### Task 9.2: Snapshot dos volumes SQLite (portal, catalogo)

**Critério de sucesso:** snapshots diários confirmados para `portal_data` e `catalogo_data`.

- [ ] **Passo 1: Confirmar snapshots automáticos** (o Fly tira snapshot diário dos volumes,
retenção padrão ~5 dias):
`fly volumes snapshots list <volume_id_portal>` e idem catalogo (pegue os IDs em `fly volumes list -a portal`/`-a catalogo`).

- [ ] **Passo 2: Aumentar retenção para 14 dias** (recomendado para dados da loja)

`fly volumes update <volume_id_portal> --snapshot-retention 14`
`fly volumes update <volume_id_catalogo> --snapshot-retention 14`

- [ ] **Passo 3: Snapshot manual sob demanda** (antes de mudanças arriscadas)

`fly volumes snapshots create <volume_id>`

**Verificação da fase:** dumps PG + snapshots SQLite existem e têm data de hoje.

---

## Fase 10 — Verificação pós-deploy (por app)

### Task 10.1: Checklist de saúde e fluxo fim-a-fim

**Critério de sucesso:** todos os itens abaixo verdes; uma simulação Santander real concluída;
uma mensagem de teste no WhatsApp respondida.

- [ ] **motor** — `fly ssh console -a motor -C "sh -c 'wget -qO- http://localhost:8000/health/ready'"` → 200; `fly logs -a motor` sem erro de Xvfb.
- [ ] **estoque** — `/health/ready` 200 (via `fly ssh console`); outbox rodando (`fly status -a estoque` mostra `outbox` started).
- [ ] **chatbot** — `/health/ready` 200; `SIMULATION_PROVIDER=http` confirmado em `fly secrets list`/`[env]`.
- [ ] **catalogo** — `curl -s https://catalogo.fly.dev/health/ready` → 200; vitrine lista veículos reais do estoque.
- [ ] **portal** — abrir `https://portal.fly.dev`, **fazer login**, ver dashboard; disparar uma
  ação que chame motor/estoque/chatbot e confirmar resposta (valida os 3 tokens + flycast).
- [ ] **Simulação Santander REAL** — pelo portal (ou API do motor), disparar uma simulação que
  aciona o `motor-worker` (RPA Playwright headed) contra o Santander real. **Este é o teste do
  maior risco (§7.1).** Esperado: job conclui com retorno do banco; `fly logs -a motor` mostra o
  fluxo sem bloqueio Akamai; screenshots em `/srv/data/screenshots`.
- [ ] **WhatsApp** — enviar mensagem de outro número para o WhatsApp da loja; confirmar resposta
  do bot (Evolution → n8n → chatbot/Gemini → Evolution).

**Se o Santander bloquear:** seguir o plano B da seção Riscos (não bloqueia os outros 4 produtos).

---

## Fase 11 — Go-live: migrar Postgres self-managed → MPG

> **Gatilho (§4 do design):** executar esta fase **no dia em que a loja começar a atender cliente
> real** pelo WhatsApp. Antes disso, permanece no self-managed.

### Task 11.1: Provisionar MPG e migrar os dados

**Critério de sucesso:** os 4 bancos rodando no MPG; apps apontando para o novo cluster; suíte
verde; self-managed desligado só após validação.

- [ ] **Passo 1: Criar o cluster MPG (HA + backup automático + PITR)**

`fly mpg create --name suite-mpg --region gru --org <sua-org>` (escolher plano com HA).
Anote a nova connection string do MPG.

- [ ] **Passo 2: Janela de manutenção — pausar escrita**

Escalar a zero os produtores de escrita durante a cópia:
`fly scale count worker=0 -a motor`; `fly scale count outbox=0 -a estoque`; e avisar que o bot
ficará indisponível alguns minutos (ou parar temporariamente o workflow n8n).

- [ ] **Passo 3: Dump + restore banco a banco**

```bash
for db in motor estoque chatbot evolution; do
  pg_dump "postgresql://postgres:<PG_PASS>@suite-pg.internal:5432/$db" \
    | psql "<MPG_CONN>/$db"   # criar o db no MPG antes se necessário
done
```

(Executar de dentro de um `fly ssh console` num app do org, ou de um Machine efêmero com acesso 6PN.)

- [ ] **Passo 4: Repontar as secrets `DATABASE_URL` (e `DATABASE_CONNECTION_URI`)**

`fly secrets set -a motor DATABASE_URL="<MPG_CONN>/motor"` (idem estoque, chatbot; evolution usa
`DATABASE_CONNECTION_URI` sem `+psycopg`). Cada `fly secrets set` redeploya o app.

- [ ] **Passo 5: Religar workers** — `fly scale count worker=1 -a motor`; `fly scale count outbox=1 -a estoque`; reativar workflow n8n.

- [ ] **Passo 6: Validar** — repetir o checklist da Fase 10 apontando para o MPG.

- [ ] **Passo 7: Desligar o self-managed** só após 24–48h estáveis:
`fly apps destroy suite-pg` (mantenha os últimos dumps do Task 9.1 como salvaguarda).

**Verificação da fase:** suíte 100% no MPG; backups automáticos/PITR do MPG ativos; dumps antigos retidos.

---

## Riscos e o que fazer (eco da §7 do design)

1. **RPA de banco a partir de IP de datacenter — MAIOR RISCO (§7.1).** Santander/Akamai pode
   bloquear o Chromium do `motor-worker` mesmo *headed* (Xvfb), porque o IP do Fly é de
   datacenter. **Validar cedo:** rodar a simulação Santander real na Fase 10 antes de anunciar
   go-live. **Plano B se bloquear:** (a) proxy residencial no worker (variável de proxy no
   Playwright); (b) rodar o `motor-worker` fora do Fly (VPS residencial/on-prem) mantendo o
   `motor-api` no Fly e o worker consumindo o mesmo Postgres via túnel/flycast. **Não bloqueia**
   os outros 4 produtos — portal, estoque, catálogo e chatbot seguem no ar.
   - **Nota operacional relacionada:** o `/dev/shm` padrão de uma Machine Fly pode ser pequeno
     para o Chromium. Se o worker crashar por falta de shm, adicionar a flag Chromium
     `--disable-dev-shm-usage` (via a config do driver) — o RPA já roda headed+Xvfb com 2GB.
2. **Bot em produção / LGPD (§7.2).** Cliente real = dado real. Garantir: consentimento antes de
   coletar dado pessoal; **CPF cifrado** (motor/chatbot já usam Fernet — `MOTOR_ENCRYPTION_KEY`);
   retenção 6 meses; **sessão WhatsApp persistente** no volume `evolution_instances` (não apagar,
   senão repareia). Backups (Fase 9) contêm dado pessoal — tratar com o mesmo cuidado.
3. **2 testes do Motor falhando (§7.3)** — mock `Santander` vs driver real homônimo. **Não
   bloqueia o deploy**, mas a suíte não está 100% verde. Registrado aqui; corrigir fora deste plano.
4. **Custo (§7.4 / §8).** Alavancas: **parar `motor-worker` quando não estiver testando RPA**
   (`fly scale count worker=0 -a motor` → ~$0; religar com `worker=1`); autostop nos HTTP;
   Postgres self-managed no teste. Total enxuto ~$15–25/mês; tudo 24/7 ~$50–70/mês. Fora do Fly:
   API Gemini (tier grátis cobre o teste), chip WhatsApp, domínio opcional.
5. **Chicken-and-egg dos tokens.** Se um app subir antes do token existir, ele fica sem a
   credencial. **Mitigação:** seguir a ordem das fases 2→3→4→5→6 exatamente; os tokens são
   emitidos por CLI (fases 2.3, 3.3, 5.3) e só então setados nas secrets dos consumidores.
6. **`release_command` + volume SQLite (portal).** Se o release não enxergar `/data`, rodar a
   migration manualmente via `fly ssh console` (ver nota na Task 6.2).

---

## Auto-revisão (cobertura do design)

- §1–2 arquitetura 7 apps → Fases 2–8 (process groups motor api+worker, estoque api+outbox). ✔
- §2 rede `.flycast` vs `.internal` → Decisão 1 + URLs em cada `[env]`. ✔
- §2 autostop → `auto_stop_machines` nos HTTP; `min_machines_running=1`/`fly scale count` nos always-on. ✔
- §3 Redis Upstash → Task 1.3; `CACHE_REDIS_URI` na Task 7.1. ✔
- §4 Postgres self-managed + 4 bancos → Fase 1; migração MPG → Fase 11. ✔
- §5 inventário de secrets (por app, só nomes + geração) → Tasks *.1 de cada app. ✔
- §6 ordem de deploy + tokens via CLI → Fases 2→8 na ordem; comandos CLI exatos citados. ✔
- Entregáveis §9: fly.toml por app ✔; apps/volumes/secrets/deploy ✔; PG+bancos+Redis ✔; tokens CLI ✔;
  QR Evolution + workflow n8n ✔; backup diário ✔; checklist verificação ✔; go-live MPG ✔.
- Riscos §7 → seção "Riscos e o que fazer" com destaque ao RPA Santander (plano B). ✔
