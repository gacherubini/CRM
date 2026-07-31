# Arquitetura 3 VMs (+ Playwright on-demand)

Plano canônico: `docs/plans/2026-07-21-plano-arquitetura-3-vms.md`.

## Status (2026-07-21+)

Stack **implementada e em uso** no org Fly (`crm-419`). Desde **2026-07-31** a topologia é
**dividida por região** — ver "Por que a stack está dividida" abaixo:

| Host público | App / papel | Região |
|--------------|-------------|--------|
| `https://app2037.fly.dev` | Bundle: portal, **revy-trafego (`/trafego`)**, chatbot, estoque, catálogo, site, motor-api, nginx edge | `iad` |
| `https://n8n2037.fly.dev` | n8n (orquestra WhatsApp → tools HTTP no chatbot) | `iad` |
| `https://evolution2037.fly.dev` | Evolution (WhatsApp) — 512MB | `iad` |
| (interno) `suite-pg` | Postgres por serviço | `iad` |
| (on-demand) `motor2037` | Playwright por banco | **`gru`** |

### Por que a stack está dividida

`gru` é a região **mais cara da Fly**: markup de **1,615** sobre a tabela base, contra **1,0**
de `iad` (valor publicado em `regionMarkups` na página de preços da Fly). Migrar os quatro
always-on derrubou o custo com tudo ligado de **~US$ 36,80 para ~US$ 20,28/mês**.

O `motor2037` **fica em `gru` de propósito**: os drivers Playwright logam em portal de lojista
brasileiro e já falham com `captcha_login` por reputação de IP de datacenter
(`docs/plans/2026-07-16-fly-rpa-captcha-opcoes.md`). IP dos EUA piora o scoring e arrisca
geo-block; e como as machines ficam `stopped`, mover não economizaria nada.

**Consequência aceita:** `motor2037` (`gru`) consulta `suite-pg` (`iad`) via `flycast`, então
cada query do RPA custa ~120ms de RTT. Decisão do owner em 2026-07-30. Se o RPA degradar de
forma perceptível, a saída é dar ao motor um Postgres próprio em `gru`.

**Pendência após a migração:** o volume da Evolution nasceu vazio — os números de WhatsApp
precisam ser pareados de novo por QR, em Ajustes na Revy Loja.

**Feito neste cutover:** monólitos legados removidos; bundle `app2037` + Evolution isolada;
workflow n8n importado/publicado; webhook Evolution → `n8n2037` `/webhook/whatsapp-ai`;
roteamento de mensagens no chatbot (3 casos); portal dono; `MOTOR_ENCRYPTION_KEY` no Motor
para Acessos bancos.

**Ainda operacional (não de deploy):** credencial Gemini no n8n (UI); E2E estável de 1ª
conversa; transcritor de áudio real (hoje fallback para texto).

### Revy Control (`revy-trafego`) — data plane da Fase 3

- Portal e Revy têm bancos SQLite separados no mesmo volume persistente:
  `/data/portal/portal.db` e `/data/revy-trafego/revy_trafego.db`.
- O Portal publica confirmação/cancelamento por outbox criptografado; o Revy materializa
  `vendas_projetadas` e calcula ROI sem ler tabelas do Portal.
- O entrypoint executa Alembic de Chatbot, Estoque, Motor, Portal e Revy em modo fail-fast.
- O health agregado exige resposta 2xx de Chatbot, Estoque, Portal e Revy.

## Realidade operacional (atual)

Apps monólito legados (`portal2037`, `catalogo2037`, `estoque2037`,
`chatbot2037`, `n8n2037` como monólito separado, `site2037` isolado, etc.) foram
**removidos a pedido do owner**. O inventário Fly válido é só:

| Papel | App | Estado típico |
|-------|-----|----------------|
| Postgres | `suite-pg` | **always-on** |
| WhatsApp (Evolution) | `evolution2037` | **always-on** (isolada) |
| Bundle app | `app2037` | **always-on** — chatbot + estoque + portal + catálogo + site + motor-api (supervisord + nginx edge) |
| Orquestração | `n8n2037` | **always-on** quando o lab está ativo — workflow WhatsApp → tools no chatbot |
| Workers Playwright | `motor2037` | **on-demand** — idle **stopped**; acordados via Machines API pelo fan-out em `app2037` |

**Always-on típico:** `suite-pg` + `evolution2037` + `app2037` + `n8n2037`.  
**Worker = app extra**, sobe só sob job e volta a stopped no idle.

> `up-all.sh --3vm` sobe Postgres + Evolution + app; se o n8n estiver em app separado,
> confira `fly status -a n8n2037` e suba/reinicie se o webhook não responder.

### Subir / desligar o lab

```bash
# Always-on only (NÃO inicia motor2037)
bash deploy/fly/up-all.sh --3vm
bash deploy/fly/up-all.sh --3vm 45   # + keepalive 45 min

# Para always-on + motor se algum worker tiver ficado started
bash deploy/fly/down-all.sh --3vm --yes
```

`--3vm` toca **apenas**:

| Script | Apps |
|--------|------|
| `up-all.sh --3vm` | start: `suite-pg`, `evolution2037`, `app2037` · **não** sobe `motor2037` |
| `down-all.sh --3vm` | stop: os 3 always-on **e** `motor2037` (se up) |

Sem `--3vm` o path “legado” ainda existe na CLI, mas os monólitos **não** devem
mais existir no org — use sempre `--3vm`.

## Papel de cada app

| # | App | Conteúdo |
|---|-----|----------|
| 1 | `suite-pg` | Postgres (DBs por serviço) |
| 2 | `evolution2037` | WhatsApp (Evolution) — **isolada** |
| 3 | `app2037` | chatbot + estoque + portal + **revy-trafego (:9010, path `/trafego`)** + catálogo + site + **motor-api** · n8n em `n8n2037` |
| 4 | `motor2037` | Playwright only · 2 GB · stopped idle |

**Alvo 3vm:** `motor2037` **não** roda HTTP/orquestrador. A API do Motor fica em
`app2037` (`127.0.0.1:8004`). O fan-out em `app2037` acorda Machines no app
`motor2037` via Machines API (`FLY_API_TOKEN` app-scoped + inventário
`worker_slots`).

### Cutover motor (worker-only)

Se `motor2037` ainda tiver process group `app` (API HTTP :8000 do perfil
`motor-simulacao/fly.toml`), **não** rode o deploy completo worker-only até
motor-api healthy em `app2037` e clientes no bundle.

```bash
# PERIGOSO pré-cutover — remove [[services]] / process `app` e derruba a API:
# fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false

# Seguro: só validar/buildar a imagem (não aplica release às machines)
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --build-only

# Opcional: atualizar só slots Playwright com a imagem publicada
fly image show -a motor2037
# fly machine update <ID> -a motor2037 --image registry.fly.io/motor2037:deployment-… --yes
```

**Depois** do cutover: deploy completo com `fly.worker.toml` torna `motor2037`
worker-only (sem HTTP `min_machines`).

## Multi-WhatsApp: um workflow n8n, N instâncias Evolution

**Regra:** um único workflow atende todos os números da loja (e do lab). Não
copie o JSON por número.

O código permite que dono/gerente faça a operação em
`/app/loja/whatsapp`: cadastrar um número, obter QR efêmero, reconectar e
desconectar. API key e payload bruto da Evolution não chegam ao navegador.

O rollout continua **default off**. Antes de habilitar a tela:

1. configure `CHATBOT_WHATSAPP_PROVIDER=evolution` e
   `CHATBOT_EVOLUTION_WEBHOOK_URL=https://n8n2037.fly.dev/webhook/whatsapp-ai`;
2. confira a URL e a API key da Evolution. O provider aceita
   `CHATBOT_EVOLUTION_URL` / `CHATBOT_EVOLUTION_API_KEY` e, se ausentes, reutiliza
   os `CHATBOT_IMAGE_EVOLUTION_*` já usados pelo bundle;
3. habilite `MULTI_WHATSAPP_ENABLED=1` e valide os endpoints de canais no Chatbot;
4. só então habilite `REVY_LOJA_SHELL_ENABLED=1` e
   `REVY_LOJA_WHATSAPP_ENABLED=1`.

No Control, a prontidão multi-WhatsApp também exige `REVY_CONTROL_ENABLED=1`.
O QR usa `Cache-Control: no-store`; não o copie para logs, tickets ou screenshots.
Rollback: desligue primeiro `REVY_LOJA_WHATSAPP_ENABLED`, depois
`MULTI_WHATSAPP_ENABLED`, sem apagar instâncias na Evolution.

| Peça | Comportamento |
|------|----------------|
| Evolution webhook | cada evento traz `body.instance` (nome da instância) |
| n8n `Extrair1` | exige `body.instance`; rejeita evento sem instance |
| URLs Evolution (`sendText`, `findChats`, `sendMedia`) | expressão n8n com `instance` do `Extrair1` — **sem** `__INSTANCE__` fixo |
| Chatbot `registrar_mensagem` / tools | resolvem loja + canal via `resolver_loja_por_instancia` / `resolve_canal_for_instance` |
| Memória do Agent | chave `instance:telefone` (conversas isoladas por canal) |
| `fromMe` / handoff | pausa só a conversa do canal (webhook com instance; PATCH `/estado` com `instance` opcional) |
| `prepare-workflow.ps1` | substitui só bases URL + secrets (`__EVOLUTION_KEY__`, tokens); **não** grava instance |

Placeholders ainda necessários no JSON canônico: `__EVOLUTION_KEY__`,
`__CHATBOT_TOKEN__`, `__CHATBOT_WEBHOOK_TOKEN__`. Instance **não** é placeholder.

Validação: `python n8n/validate_workflow.py` (rejeita qualquer `__INSTANCE__` residual).

## Google Ads no Control

O detalhe da Loja no Control já implementa conexão OAuth, escolha da conta, bindings
de conversão e métricas. Para o rollout, mantenha `GOOGLE_ADS_SYNC_ENABLED=0` e
`GOOGLE_CONVERSIONS_ENABLED=0` até:

1. cadastrar client id/secret e developer token nos secrets do `app2037`;
2. registrar no Google Cloud Console exatamente
   `https://app2037.fly.dev/trafego/app/control/google-ads/oauth/callback`;
3. usar a mesma URL em `GOOGLE_ADS_OAUTH_REDIRECT_URI`;
4. validar OAuth e sync numa loja de teste; só depois ligar as duas flags.

O callback `/control/v1/google-ads/oauth/callback` retorna JSON e permanece apenas
por compatibilidade. A UI deve usar o callback HTML em `/app/control/...`.

## Roteamento WhatsApp (grupo do estoque)

Endpoint: `POST /v1/operacao/roteamento` (chatbot em `app2037`).
O n8n consulta `isSaved` na Evolution e manda
`{ instance, telefone, texto, is_saved, grupo_jid }`.

| Caso | Condição | `acao` |
|------|----------|--------|
| Contato que já fala | `is_saved=true` e **não** autorizado | `ignorar` (sem bot) |
| Contato **novo** | `is_saved=false` e **não** autorizado | `cliente` (IA Gemini) |
| Grupo do estoque | `grupo_jid` igual ao grupo selecionado no Portal | menu, cadastro e fotos do estoque |
| Outro grupo ou imagem privada | não é o grupo selecionado | `ignorar` silenciosamente |

`is_saved` desconhecido → **ignorar** (fail-closed).

O grupo é selecionado no Portal em **Operação → Grupo do estoque**. A lista de
números autorizados permanece somente para compatibilidade com instalações que
ainda não escolheram um grupo.

## Critérios de aceite

1. Evolution `loja1` (ou instância ativa) state `open`.
2. WhatsApp **contato novo** (`isSaved=false`) → resposta IA via n8n/chatbot.
3. Contato **já salvo** e não autorizado → **sem** resposta de bot.
4. Grupo selecionado: `menu` abre as opções; cadastro e fotos alimentam Estoque → Catálogo.
5. Imagem privada ou enviada em outro grupo → nenhuma resposta e nenhum cadastro.
6. Portal login + listagem básica + Acessos bancos (com `MOTOR_ENCRYPTION_KEY`).
7. Simulação **mock** 2xx sem subir worker Playwright.
8. Always-on machines started; workers Playwright stopped fora de job.
9. Health agregado: `https://app2037.fly.dev/healthz`; Revy:
   `https://app2037.fly.dev/trafego/health/ready`.

## Deploy (raiz do repo)

Antes do deploy que altera schema, crie snapshot do volume do `app2037` e confira os secrets pelo
nome (nunca imprima valores). O deploy do bundle roda todas as migrações antes de iniciar serviços.

```bash
# 1) App bundle (motor-api + n8n + …)
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false

# 2) Canal (reusa app evolution se já existir)
fly deploy -a evolution2037 -c deploy/fly/3vm/fly.canal.toml --ha=false

# 3) Worker Playwright — SÓ após cutover (ver secção acima)
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false

# Pré-cutover: validar imagem sem tocar machines
# fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --build-only
```

O `dockerfile` em `fly.worker.toml` é **relativo ao diretório do toml**
(`deploy/fly/3vm/Dockerfile.worker`). O build context é a raiz do repo (`.`).
`ignorefile` = `deploy/fly/3vm/.dockerignore.worker`.
**Não** é necessário `--dockerfile` na CLI.

### Contexto de build enxuto (lean context)

O context do Docker/Fly é a **raiz do repo** (`fly deploy .`), não `deploy/fly/3vm/`.
Por isso o ignorefile precisa estar na raiz **ou** ser apontado em `[build].ignorefile`
no toml (caminho relativo ao toml).

| Artefato | Uso |
|----------|-----|
| `.dockerignore` (raiz) | `docker build -f deploy/fly/3vm/Dockerfile.* .` e fallback do flyctl |
| `deploy/fly/3vm/.dockerignore` | `fly.app.toml` → `ignorefile = ".dockerignore"` |
| `deploy/fly/3vm/.dockerignore.worker` | `fly.worker.toml` → `ignorefile = ".dockerignore.worker"` (exclui outros serviços) |

Exclui `.venv`, `__pycache__`, `tests/`, `*.db`, `motor-simulacao/data`, `docs/`,
`n8n/` (JSON local; n8n entra via npm na imagem), stacks standalone e `.git`.
**Não** exclui o que o `Dockerfile.app` copia (`*/app`, `*/alembic`, `site/`,
`deploy/fly/3vm/…`). Dockerfiles por serviço (`chatbot-api/`, etc.), com context
no próprio diretório, continuam usando o `.dockerignore` local e não são afetados.

Build local:

```bash
docker build -f deploy/fly/3vm/Dockerfile.app -t revy-app:3vm .
docker build -f deploy/fly/3vm/Dockerfile.worker -t revy-worker:3vm .
```

### Worker: o que o deploy (pós-cutover) faz / não faz

| Faz | Não faz |
|-----|---------|
| Publica imagem `registry.fly.io/motor2037:…` com Chromium + entrypoint on-demand | Criar/acordar slots `motor-worker-*` por si só |
| Atualiza a machine **Launch** do app (seed; `MOTOR_WORKER_SEED=1` → exit 0 → **stopped**) | Manter `min_machines` / HTTP always-on do perfil legado |
| Deixa app **sem** `[[http_service]]` / `[[services]]` | Migrar o inventário `worker_slots` |
| size Launch seed = `shared-cpu-2x` / **2048 MB** | Destruir apps (`fly apps destroy` proibido sem pedido) |

Slots Playwright existentes (`motor-worker-santander`, `fontecred`, `bradesco`, `pan`)
são Machines **fora** do Fly Launch. Depois de publicar a imagem, alinhe cada slot:

```bash
# pegue o tag (fly deploy / --build-only imprime; ou:)
fly image show -a motor2037
fly machines list -a motor2037

# atualize cada worker parado (IDs de exemplo — confira com machines list):
# IMG=registry.fly.io/motor2037:deployment-XXXXXXXX
# fly machine update 286501db405d68 -a motor2037 --image "$IMG" --yes   # santander
# fly machine update 48ed461ce22718 -a motor2037 --image "$IMG" --yes   # fontecred
# fly machine update 1850921c91d648 -a motor2037 --image "$IMG" --yes   # bradesco
# fly machine update 080e207bed0068 -a motor2037 --image "$IMG" --yes   # pan
#
# NÃO rode machine update no process group `app` (API always-on) pré-cutover.
```

Cada slot deve ter (já é o padrão atual):

- entrypoint `/srv/scripts/on-demand-worker-entrypoint.sh`
- `MOTOR_WORKER_PROVEDOR=<santander|fontecred|bradesco|pan>`
- `MOTOR_WORKER_ON_DEMAND=1`, `MOTOR_WORKER_TIPOS=playwright`
- restart policy **`on-failure`** (exit 0 após idle → machine **stopped**)
- size `shared-cpu-2x` / **2048 MB**
- **sem** serviço HTTP

Registrar IDs no Postgres do Motor (tabela `worker_slots`), se ainda não estiverem:

```bash
# com DATABASE_URL do motor (suite-pg) — ver deploy/fly/sync-motor-worker-machines.sh
bash deploy/fly/sync-motor-worker-machines.sh \
  santander:286501db405d68 \
  fontecred:48ed461ce22718 \
  bradesco:1850921c91d648 \
  pan:080e207bed0068
```

## Workflow n8n (sem secrets no git)

1. Canônico versionado: `n8n/workflow-ai-nao-salvos.json` (placeholders `__CHATBOT_TOKEN__` etc.).
2. Local: preencha `deploy/fly/3vm/.secrets.local` (gitignored).
3. Gere o JSON com tokens: `pwsh deploy/fly/3vm/prepare-workflow.ps1`
   → saída `workflow-fly.ready.json` (**gitignored** — tem Bearer reais).
4. Importe/publique: `pwsh deploy/fly/3vm/upload-and-import-workflow.ps1`
   (CLI n8n precisa `HOME=/home/node` no container; workflow deve estar **published**
   para o webhook `/webhook/whatsapp-ai` responder 200).

Hosts preferidos no workflow preparado: HTTPS públicos
`https://app2037.fly.dev` e `https://evolution2037.fly.dev` (flycast IPv6 exige
nginx ouvindo `[::]` no edge).

## Secrets / env

Ver também `env.example`. **Não versionar valores.** Não imprimir secrets em logs/chat.

Arquivos **gitignored** nesta pasta:

- `.secrets.local` — tokens de prepare-workflow / ops local
- `.evolution_key.local` — apikey Evolution
- `workflow-fly.ready.json` — workflow com tokens embutidos

### `app2037` (orquestrador + fan-out)

O motor-api no bundle app precisa do DB do motor e de permissão para acordar
workers no app `motor2037`:

| Secret / env | Onde | Notas |
|--------------|------|--------|
| `MOTOR_DATABASE_URL` | secret | `postgresql://…@suite-pg.flycast:5432/motor` (mesmo DB dos workers) |
| `MOTOR_TOKEN` / `MOTOR_METRICS_TOKEN` / `MOTOR_ENCRYPTION_KEY` | secret | auth + credenciais cifradas |
| `MOTOR_FANOUT_ENABLED=1` | secret ou env | liga tarefas por provedor |
| `MOTOR_FLY_AUTOSCALE_ENABLED=1` | secret ou env | liga wake via Machines API |
| `FLY_API_TOKEN` | secret | token **app-scoped** com permissão de start/stop em **`motor2037`** (não token pessoal) |
| `FLY_APP_NAME=motor2037` | secret ou env | app das machines worker (default no código também é `motor2037`) |
| `MOTOR_MAX_BROWSER_WORKERS=2` | opcional | teto de Playwrights simultâneos |
| `MOTOR_FLY_START_BURST` | opcional | default alinhado ao teto |
| demais (`CHATBOT_*`, `ESTOQUE_*`, portal, n8n) | secret | ver `env.example` |

Para o Revy no bundle:

| Env/secret | Notas |
|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | default canônico `sqlite:////data/revy-trafego/revy_trafego.db` |
| `REVY_TRAFEGO_SERVICE_TOKEN` | autentica Portal → Revy |
| `REVY_TRAFEGO_CHATBOT_TOKENS_JSON` | recomendado em multi-loja; JSON `loja_slug → token` |
| `CHATBOT_API_TOKEN` + `REVY_TRAFEGO_LOJAS` | compatibilidade segura quando existe exatamente uma loja |

No `fly.app.toml` o processo motor já roda com `MOTOR_ORCHESTRATOR_ONLY=1` e
`MOTOR_WORKER_TIPOS=api,mock` (mock/API **não** sobem VM 4).

Exemplo (valores fictícios — use os reais só no terminal local):

```bash
fly secrets set \
  MOTOR_FANOUT_ENABLED=1 \
  MOTOR_FLY_AUTOSCALE_ENABLED=1 \
  FLY_APP_NAME=motor2037 \
  FLY_API_TOKEN="***" \
  -a app2037
```

### `motor2037` (workers Playwright)

| Secret / env | Onde | Notas |
|--------------|------|--------|
| `DATABASE_URL` | secret | **mesmo** Postgres `motor` que `MOTOR_DATABASE_URL` no app (`…/motor`) |
| `MOTOR_ENCRYPTION_KEY` | secret | deve bater com o app (credenciais de provedor) |
| `MOTOR_METRICS_TOKEN` | opcional | se workers expuserem métricas |
| `MOTOR_WORKER_*` / browser | `fly.worker.toml` `[env]` | on-demand, idle 60s, headed+Xvfb |

Workers **não** precisam de `FLY_API_TOKEN` (só o orquestrador em `app2037` acorda machines).

```bash
# se ainda não existir / para alinhar com app2037:
fly secrets set \
  DATABASE_URL="postgresql://…@suite-pg.flycast:5432/motor" \
  MOTOR_ENCRYPTION_KEY="***" \
  -a motor2037
```

### Ordem recomendada no cutover (motor worker-only)

1. Secrets de fan-out em **`app2037`** (`FLY_API_TOKEN` com scope no app `motor2037`).
2. Deploy **`app2037`** healthy (`curl 127.0.0.1:8004/health/ready` → ok; mock 2xx).
3. Tráfego só no bundle (`app2037`); monólitos legados já não existem.
4. Opcional: `--build-only` + `fly machine update` nos **slots** `motor-worker-*`
   (imagem nova) **sem** mexer no process `app` ainda (se ainda houver API no app).
5. Deploy worker-only: `fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false`
   → remove HTTP always-on do orquestrador legado neste app.
6. Confirmar: `fly machines list -a motor2037` → sem machine `app` started 24/7;
   só seed stopped + slots stopped.
7. Smoke mock em app2037 (nenhuma VM 4 sobe) → smoke 1 banco real
   (1 machine started → stopped).

## Rollback

Monólitos legados **não** estão mais no inventário. Rollback realista:

1. Stop / redeploy `app2037` se o bundle estiver quebrado.
2. Motor: se precisar da API HTTP de novo em `motor2037`, redeploy
   `motor-simulacao/fly.toml` (orquestrador + serviço HTTP) **só** com intenção
   explícita — e reaponte quem consumir essa URL.
3. Evolution / Postgres: não destruir `suite-pg` nem volume da Evolution sem
   intenção de zerar sessão WA e dados.
4. Recriar monólitos legados só se o owner pedir (não é o path padrão).

## O que não destruir

- **Não** destruir `suite-pg` / volume Postgres sem intenção de zerar dados.
- **Não** destruir volume/sessão Evolution sem intenção de zerar WA.
- **Não** destruir `motor2037` se ainda houver slots/`worker_slots` apontando para ele.
- `fly apps destroy` e destroy de volumes: **proibido** sem pedido explícito do owner.
