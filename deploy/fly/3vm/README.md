# Lab Fly — arquitetura 3 VMs (+ Playwright on-demand)

Stack em uso no org Fly `crm-419`. Plano canônico:
`docs/plans/2026-07-21-plano-arquitetura-3-vms.md`.

## O que não destruir

- **`fly apps destroy` e destroy de volume são proibidos sem pedido explícito do owner.**
- Não destruir `suite-pg` / volume Postgres sem intenção de zerar dados.
- Não destruir volume/sessão da Evolution sem intenção de zerar o WhatsApp.
- Não destruir `motor2037` enquanto houver slots/`worker_slots` apontando para ele.
- Não recriar os monólitos legados (`portal2037`, `catalogo2037`, `estoque2037`,
  `chatbot2037`, `site2037`) — foram removidos a pedido do owner.
- Antes de deploy que altera schema: snapshot do volume do `app2037` e conferência dos
  secrets **pelo nome** (nunca imprima valores).

## Inventário

| App | Papel | Região | Estado típico |
|---|---|---|---|
| `suite-pg` | Postgres (DB por serviço) | `iad` | always-on |
| `evolution2037` | WhatsApp (Evolution), 512 MB, isolada | `iad` | always-on |
| `app2037` | Bundle: portal, revy-trafego, chatbot, estoque, catálogo, site, motor-api, nginx edge | `iad` | always-on |
| `n8n2037` | Orquestração WhatsApp → tools HTTP no chatbot | `iad` | always-on com o lab ativo |
| `motor2037` | Slots Playwright por banco, 2 GB | **`gru`** | on-demand, stopped no idle |

`motor2037` fica em `gru` de propósito (reputação de IP para os portais bancários) e
consulta `suite-pg` em `iad` via flycast, ~120ms de RTT por query — decisão aceita.
Ver [histórico](../../../docs/historico/fly-3vm.md).

### Rotas públicas do `app2037`

| Path | Destino |
|---|---|
| `/` · `/app` | Portal / Revy Loja (`:9000`) |
| `/trafego/` | Revy Control (`:9010`) |
| `/catalogo/` | Catálogo público (`:8003`) — `/loja/` redireciona 301 |
| `/public/` | **Mídia do estoque** (`:8002`) — não confundir com o catálogo |
| `/site/` | Site marketing (`:8081`) |
| `/webhook/` `/v1/` `/health/` | Chatbot API (`:8001`) |

Health agregado: `https://app2037.fly.dev/healthz` (exige 2xx de Chatbot, Estoque, Portal e
Revy). Revy: `/trafego/health/ready`.

## Subir e desligar

```bash
bash deploy/fly/up-all.sh --3vm          # start suite-pg, evolution2037, app2037
bash deploy/fly/up-all.sh --3vm 45       # + keepalive 45 min
bash deploy/fly/down-all.sh --3vm --yes  # stop os always-on E motor2037
```

`up-all.sh --3vm` **não** sobe `motor2037`. Se o n8n estiver em app separado, confira
`fly status -a n8n2037`. Sem `--3vm` a CLI usa o path legado dos monólitos — **use sempre
`--3vm`**.

> Em Windows os scripts podem falhar silenciosamente (invocam `python3`). Se `down-all.sh`
> não confirmar o stop, pare na mão com `fly machine stop <id> -a <app>` — senão o lab fica
> ligado gastando.

## Deploy

```bash
# App bundle (portal + revy-trafego + chatbot + estoque + catálogo + site + motor-api)
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false

# Canal WhatsApp
fly deploy -a evolution2037 -c deploy/fly/3vm/fly.canal.toml --ha=false

# Worker Playwright — só depois do cutover (ver histórico)
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --ha=false
# Pré-cutover, valide sem tocar machines:
fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml --build-only
```

O deploy usa a **árvore local**, não o commit — commite antes, senão prod e repo divergem.
O bundle roda todas as migrações (fail-fast) antes de iniciar os serviços.

`dockerfile` no `fly.worker.toml` é relativo ao diretório do toml; o build context é a raiz
do repo. Não é preciso `--dockerfile` na CLI.

### Contexto de build

| Artefato | Uso |
|---|---|
| `.dockerignore` (raiz) | `docker build -f deploy/fly/3vm/Dockerfile.* .` e fallback do flyctl |
| `deploy/fly/3vm/.dockerignore` | `fly.app.toml` → `ignorefile = ".dockerignore"` |
| `deploy/fly/3vm/.dockerignore.worker` | `fly.worker.toml` (exclui os outros serviços) |

Exclui `.venv`, `__pycache__`, `tests/`, `*.db`, `motor-simulacao/data`, `docs/`, `n8n/`,
stacks standalone e `.git`. **Não** exclui o que `Dockerfile.app` copia (`*/app`,
`*/alembic`, `site/`, `deploy/fly/3vm/…`).

```bash
docker build -f deploy/fly/3vm/Dockerfile.app -t revy-app:3vm .
docker build -f deploy/fly/3vm/Dockerfile.worker -t revy-worker:3vm .
```

## Secrets

Ver `env.example`. **Não versionar valores, não imprimir em log/chat.** Gitignored nesta
pasta: `.secrets.local`, `.evolution_key.local`, `workflow-fly.ready.json`.

As flags `REVY_*` / `MULTI_*` do `app2037` são **secrets**, não `[env]` do toml — e secret
vence `[env]`. O toml pode dizer uma coisa e o efetivo ser outra.

### `app2037` (orquestrador + fan-out)

| Secret / env | Notas |
|---|---|
| `MOTOR_DATABASE_URL` | `postgresql://…@suite-pg.flycast:5432/motor` (mesmo DB dos workers) |
| `MOTOR_TOKEN` / `MOTOR_METRICS_TOKEN` / `MOTOR_ENCRYPTION_KEY` | auth + credenciais cifradas |
| `MOTOR_FANOUT_ENABLED=1` | liga tarefas por provedor |
| `MOTOR_FLY_AUTOSCALE_ENABLED=1` | liga wake via Machines API |
| `FLY_API_TOKEN` | token **app-scoped** com start/stop em `motor2037` (nunca token pessoal) |
| `FLY_APP_NAME=motor2037` | app das machines worker |
| `MOTOR_MAX_BROWSER_WORKERS=2` | teto de Playwrights simultâneos |
| `REVY_TRAFEGO_DATABASE_URL` | `sqlite:////data/revy-trafego/revy_trafego.db` |
| `REVY_TRAFEGO_SERVICE_TOKEN` | autentica Portal → Revy |
| `REVY_TRAFEGO_CHATBOT_TOKENS_JSON` | JSON `loja_slug → token` (recomendado em multi-loja) |

No `fly.app.toml` o processo motor roda com `MOTOR_ORCHESTRATOR_ONLY=1` e
`MOTOR_WORKER_TIPOS=api,mock` — mock/API **não** sobem a VM 4.

### `motor2037` (workers Playwright)

`DATABASE_URL` (o **mesmo** Postgres `motor` do app), `MOTOR_ENCRYPTION_KEY` (idêntico ao
app), `MOTOR_METRICS_TOKEN` opcional, e os `MOTOR_WORKER_*` no `[env]` do toml. Workers
**não** precisam de `FLY_API_TOKEN` — só o orquestrador acorda machines.

### `n8n2037` (retenção de execução — senão o volume enche e o bot fica mudo)

O n8n usa SQLite no volume `n8n_data` (**3 GB**, montado em `/home/node/.n8n`). Sem poda, o
`database.sqlite` cresce ~1 GB/semana (guarda o payload inteiro de cada execução) e ao
chegar a 100% **toda** execução do workflow estoura `SQLITE_FULL` → `POST
/webhook/whatsapp-ai` responde **500** → Evolution não entrega → **bot mudo**, com todos os
serviços de pé e `/healthz` = ok. Diagnóstico: `fly logs -a n8n2037` (`SQLITE_FULL`) e
`fly ssh console -a n8n2037 -C "df -h /home/node/.n8n"`. Destravar sem apagar dados:
`fly volumes extend <vol-id> -s <GB> -a n8n2037` (redimensiona online, sem restart).

Secrets obrigatórios (janela deslizante de 7 dias; o banco estabiliza em ~1 semana ≈ ~1 GB
e para de crescer). Apagar execução do n8n **não** perde conversa — o Revy Loja lê do
chatbot-api (`/v1/conversas`) e o workflow grava toda mensagem em `POST /webhook/mensagem`:

| Secret | Valor | Papel |
|---|---|---|
| `EXECUTIONS_DATA_PRUNE` | `true` | liga a poda |
| `EXECUTIONS_DATA_MAX_AGE` | `168` | retém 7 dias (limitador principal) |
| `EXECUTIONS_DATA_PRUNE_MAX_COUNT` | `20000` | teto de segurança p/ surto de tráfego |
| `EXECUTIONS_DATA_SAVE_ON_SUCCESS` | `all` | mantém sucesso p/ debug (bug "respondeu errado" conta como execução de **sucesso**, não de erro) |
| `EXECUTIONS_DATA_SAVE_ON_ERROR` | `all` | mantém erros |
| `EXECUTIONS_DATA_SAVE_ON_PROGRESS` | `false` | — |
| `EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS` | `false` | — |
| `DB_SQLITE_VACUUM_ON_STARTUP` | `true` | compacta o arquivo no boot |

> **Armadilha — reiniciar o `n8n2037` derruba o bot por ~6 min.** Qualquer restart
> (`fly secrets set`, `fly machine restart`, `fly deploy`) faz o n8n levar **~6 min** para
> reativar o workflow e re-registrar o webhook (recuperação "This could be due to a
> crash…"). Nesse intervalo `POST /webhook/whatsapp-ai` responde **404** e a **Evolution
> cancela o retry no 404** (perde as mensagens do intervalo; no 500 ela re-tenta). **Não
> reinicie de novo** — zera o relógio; espere. Verificação não-invasiva: `curl -X POST -d
> '{}' https://n8n2037.fly.dev/webhook/whatsapp-ai` → **404** = ainda ativando, **200** =
> registrado (o `Extrair1` rejeita `{}` sem `instance`, sem efeito colateral). Confira o
> estado no DB com `HOME=/home/node n8n list:workflow --active=true` (via `fly ssh`).
> Agrupe mudanças de secret e evite restart em horário de pico.

## Multi-WhatsApp: um workflow n8n, N instâncias

**Um único workflow atende todos os números.** Não copie o JSON por número — a instance
vem em `body.instance` de cada evento da Evolution e **não é placeholder**.

| Peça | Comportamento |
|---|---|
| n8n `Extrair1` | exige `body.instance`; rejeita evento sem instance |
| URLs Evolution (`sendText`, `findChats`, `sendMedia`) | expressão com `instance` do `Extrair1` — sem `__INSTANCE__` fixo |
| Chatbot | resolve loja + canal via `resolver_loja_por_instancia` / `resolve_canal_for_instance` |
| Memória do Agent | chave `instance:telefone` (conversas isoladas por canal) |
| `fromMe` / handoff | pausa só a conversa daquele canal |

Ordem de rollout (default off): `CHATBOT_WHATSAPP_PROVIDER=evolution` +
`CHATBOT_EVOLUTION_WEBHOOK_URL` → conferir URL/apikey da Evolution →
`MULTI_WHATSAPP_ENABLED=1` e validar os endpoints de canais → só então
`REVY_LOJA_SHELL_ENABLED=1` e `REVY_LOJA_WHATSAPP_ENABLED=1`. Rollback na ordem inversa,
sem apagar instâncias na Evolution. O QR usa `Cache-Control: no-store` — não copie para
log, ticket ou screenshot.

## Workflow n8n (sem secrets no git)

1. Canônico versionado: `n8n/workflow-ai-nao-salvos.json` (placeholders
   `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`, `__CHATBOT_WEBHOOK_TOKEN__`).
2. Preencha `deploy/fly/3vm/.secrets.local` (gitignored).
3. `pwsh deploy/fly/3vm/prepare-workflow.ps1` → `workflow-fly.ready.json` (**gitignored**,
   tem Bearer reais).
4. `pwsh deploy/fly/3vm/upload-and-import-workflow.ps1` (a CLI do n8n precisa de
   `HOME=/home/node`; o workflow tem de estar **published** para o webhook responder 200).
5. `python n8n/validate_workflow.py` — rejeita `__INSTANCE__` residual.

Hosts preferidos no workflow preparado: `https://app2037.fly.dev` e
`https://evolution2037.fly.dev`.

## Roteamento WhatsApp

`POST /v1/operacao/roteamento` no chatbot. O n8n consulta `isSaved` na Evolution e manda
`{ instance, telefone, texto, is_saved, grupo_jid }`.

| Condição | `acao` |
|---|---|
| `is_saved=true` e não autorizado | `ignorar` |
| `is_saved=false` e não autorizado | `cliente` (IA Gemini) |
| `grupo_jid` = grupo selecionado no Portal | menu, cadastro e fotos do estoque |
| Outro grupo ou imagem privada | `ignorar` silenciosamente |

`is_saved` desconhecido → **ignorar (fail-closed)**.

---

Histórico (divisão de regiões e custo, cutover worker-only, rollback, critérios de aceite):
[`../../../docs/historico/fly-3vm.md`](../../../docs/historico/fly-3vm.md).
