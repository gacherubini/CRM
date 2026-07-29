# Revy Tráfego

Cockpit multi-loja da **equipe Revy** para operação de mídia paga (Pixel, CAPI, Ads spend, campanhas, ROI, auditorias e diagnóstico de leads).

O **portal da loja** (`portal-gestao`) mostra só resultados de negócio ao dono; a config técnica fica aqui.

**Plano canônico:**  
[`docs/plans/2026-07-28-plano-revy-trafego-separacao.md`](../docs/plans/2026-07-28-plano-revy-trafego-separacao.md)

---

## Status atual — Fase 3 no código local

- Banco próprio e Alembic `0001_revy_trafego_baseline`.
- Vendas chegam pelo outbox criptografado do Portal e são materializadas em `vendas_projetadas`.
- ROI/CAPI não leem mais tabelas do Portal.
- CAPI assíncrona, `blocked_config`, cancelamento seguro, lease e dedupe por loja.
- **Ainda sem commit/deploy**; o ambiente publicado pode continuar no desenho antigo.
- Validação local: **95 testes Revy + 293 Portal + 170 Chatbot + 87 Estoque**.

## Status anterior (2026-07-28 — Fase 1/2 no lab)

| Item | Estado |
|---|---|
| Código Fase 1 + 2 + UI + cutover B5 | **DONE** na `main` |
| Deploy lab Fly 3-VM (`app2037`) | **DONE** (imagem com `/trafego` + workers) |
| Lab machines | Desligar com `down-all.sh --3vm` quando não em uso (pedido ops) |
| UI pública (lab up) | `https://app2037.fly.dev/trafego` |
| API interna (bundle) | `http://127.0.0.1:9010` |
| Flags portal resultados + venda | **ON** |
| Workers CAPI/spend | **Só Revy Tráfego** (`:9010`); portal `PORTAL_*_ENABLED=0` |
| Smoke final | **17/17 PASS** (health, login, loja, telas, conversa, API, pixel, portal, catálogo) |

### URLs lab

| O quê | URL |
|---|---|
| Login / app | https://app2037.fly.dev/trafego |
| Login direto | https://app2037.fly.dev/trafego/health/live (health) · `/trafego/login` |
| Portal loja | https://app2037.fly.dev |
| Catálogo | https://app2037.fly.dev/loja/ |

Bootstrap do 1º gestor: secrets Fly `REVY_TRAFEGO_BOOTSTRAP_EMAIL` / `_SENHA` (só cria se `gestores_revy` vazia).

---

## O que entrou nesta entrega (ops + UI)

### Bundle Fly 3-VM

- App copiado em `Dockerfile.app` → `/srv/revy-trafego`
- Supervisor: `program:revy-trafego` → `run-revy-trafego.sh` (uvicorn `:9010`)
- Nginx edge: path **`/trafego/`** (strip prefix) + `absolute_redirect off` (evita `http://host:8080`)
- Envs no `fly.app.toml` + secrets (`SESSION_SECRET`, `SERVICE_TOKEN`, bootstrap)
- Prefixo de URL: `REVY_TRAFEGO_URL_PREFIX=/trafego` (links/redirects corretos no edge)

### Flags / cutover no lab (completo B1–B5)

| Env | Valor lab | Nota |
|---|---|---|
| `REVY_TRAFEGO_URL` | `http://127.0.0.1:9010` | Portal → API |
| `REVY_TRAFEGO_PUBLIC_URL` | `http://127.0.0.1:9010` | Catálogo Pixel (prioridade) |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `1` | Cards ROI via API |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `1` | Notifica venda-confirmada |
| `PORTAL_TRAFEGO_UI_LEGACY` | `0` | Dono sem menus técnicos |
| `PORTAL_CAPI_RETRY_ENABLED` | `0` | Portal **não** processa outbox |
| `PORTAL_META_SPEND_SYNC_ENABLED` | `0` | Portal **não** sync spend |
| `REVY_TRAFEGO_CAPI_WORKER` | `1` | CAPI retry **só** no tráfego |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `1` | Spend job **só** no tráfego |
| `REVY_TRAFEGO_LOJAS` | `loja1,moto-center` | Dropdown mesmo sem campanha no DB |

No bundle, o shell `run-revy-trafego.sh` força `PORTAL_CAPI_RETRY_ENABLED=1` / spend `=1`
**apenas** no processo `:9010` (o Portal força `0`). O Revy usa banco próprio e é o único dono
da outbox CAPI e do sync de spend.

**Nunca** ligar CAPI worker nos dois processos no mesmo outbox.

### UI

- Login no mesmo padrão do portal (layout 2 colunas, tema claro/escuro, Inter)
- **Dropdown de loja** na home e na sidebar (troca com `POST /app/loja` + `next`)
- Lista de lojas: união de tabelas de mídia/vendas + `REVY_TRAFEGO_LOJAS` / fallback catálogo

### Bugs corrigidos no lab

- Redirect `/trafego` → `http://host:8080/...` (browser “off”) — nginx `absolute_redirect off`
- Links Jinja `public_path('/.../{{ id }}')` literal (conversas/campanhas/ROI/CTWA) — concatenação `~`
- Schema portal stuck em Alembic `0008` com tabelas parciais — alinhado a `0011` + coluna `codigo_ctwa`
- Conversas de leads inacessíveis (links quebrados + telefone na path)

### Smoke validado no lab

- Login bootstrap → `/trafego/app`
- Dropdown `loja1` / `moto-center`
- Config, Campanhas, ROI → 200
- Diagnóstico leads (proxy chatbot) + abrir conversa (mensagens)
- `GET /v1/lojas/{slug}/resultados` com `X-Service-Token`
- `GET /public/v1/lojas/{slug}/pixel`

### Ainda residual (dados de mídia, não de plataforma)

- Pixel / CAPI / Ads token: configurar por loja na UI (lab ainda sem Pixel salvo)
- Campanhas/gastos/vendas: vazios até operação de mídia
- Plataforma/cutover de código e workers: **concluído**

---

## Fase 1 / 2 (histórico do desenho compartilhado — não usar no deploy atual)

- Essas fases usavam o banco do Portal (`/data/portal/portal.db`); a Fase 3 substituiu esse desenho.
- Mesma chave Fernet: `PORTAL_ENCRYPTION_KEY` (ou `REVY_TRAFEGO_ENCRYPTION_KEY`).
- Workers CAPI/spend **desligados por padrão** (continuam no portal até cutover B5).
- API `/v1` com `REVY_TRAFEGO_SERVICE_TOKEN`; portal consome com flags ligadas.

---

## Local

```bash
cd revy-trafego
python3.12 -m venv .venv   # precisa 3.12+
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export REVY_TRAFEGO_DATABASE_URL="sqlite:///./revy_trafego.db"
export REVY_TRAFEGO_ENCRYPTION_KEY='gere-uma-chave-fernet'
export REVY_TRAFEGO_BOOTSTRAP_EMAIL=trafego@revy.local
export REVY_TRAFEGO_BOOTSTRAP_SENHA='troque-isto'
export REVY_TRAFEGO_URL_PREFIX=   # vazio em local puro (sem nginx /trafego)
export CHATBOT_API_URL=http://127.0.0.1:8001
export REVY_TRAFEGO_CHATBOT_TOKENS_JSON='{"moto-center":"..."}'
alembic upgrade head
uvicorn app.main:app --reload --port 9010
```

Login: se `gestores_revy` estiver vazia, o bootstrap cria o primeiro admin.

Testes:

```bash
pytest -q
```

---

## Envs principais

| Env | Default | Notas |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | `sqlite:///./revy_trafego.db` | Banco exclusivo do Revy |
| `REVY_TRAFEGO_SESSION_SECRET` | dev | Cookie `revy_trafego_session` |
| `REVY_TRAFEGO_ENCRYPTION_KEY` | = `PORTAL_ENCRYPTION_KEY` | Tokens CAPI/Ads |
| `REVY_TRAFEGO_URL_PREFIX` | vazio | No Fly: `/trafego` |
| `REVY_TRAFEGO_SECURE_COOKIE` | `0` | Lab Fly: `1` |
| `REVY_TRAFEGO_LOJAS` | vazio | Lista `loja1,moto-center` para o dropdown |
| `REVY_TRAFEGO_BOOTSTRAP_EMAIL` / `_SENHA` / `_NOME` | bootstrap | 1º gestor se tabela vazia |
| `CHATBOT_API_URL` | — | Diagnóstico leads/conversas |
| `REVY_TRAFEGO_CHATBOT_TOKENS_JSON` | — | JSON `loja_slug → token`; recomendado para multi-loja |
| `REVY_TRAFEGO_CHATBOT_TOKEN_LOJA` + `CHATBOT_API_TOKEN` | — | Compatibilidade para uma única loja |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `0` | Job 24h |
| `REVY_TRAFEGO_CAPI_WORKER` | `0` | Retry outbox |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | `POST /internal/jobs/meta-spend-sync` |
| `REVY_TRAFEGO_SERVICE_TOKEN` | vazio | Header `X-Service-Token` nas APIs `/v1/*` |

### Portal (flags cutover)

| Env | Default | Efeito |
|---|---|---|
| `PORTAL_TRAFEGO_UI_LEGACY` | off | `1` = menus técnicos de volta ao dono |
| `REVY_TRAFEGO_URL` | — | Base deste app |
| `REVY_TRAFEGO_SERVICE_TOKEN` | — | Mesmo token |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `0` | `1` = cards ROI via API |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `0` | `1` = POST venda-confirmada |
| `PORTAL_REVY_TRAFEGO_TIMEOUT` | `4` | segundos |

### Catálogo

| Env | Notas |
|---|---|
| `REVY_TRAFEGO_PUBLIC_URL` | Prioridade sobre `PORTAL_PUBLIC_URL` para Pixel |
| `PORTAL_PUBLIC_URL` | Fallback |

---

## API v1

- `GET /health/live`
- `GET /health/ready`
- `GET /v1/lojas/{slug}/resultados?periodo=7d|mes` — ROI (header `X-Service-Token`)
- `POST /v1/lojas/{slug}/eventos/venda-confirmada` — CAPI (idempotente)
- `POST /v1/lojas/{slug}/eventos/venda-atualizada` — projeção/cancelamento idempotente
- `GET /public/v1/lojas/{slug}/pixel` — Pixel público (sem auth)

Público via edge: prefixar `/trafego` (ex.: `/trafego/health/live`, `/trafego/v1/...`).  
No bundle, portal/catálogo usam `http://127.0.0.1:9010` **sem** prefixo.

---

## Deploy Fly (3-VM)

Da raiz do repo:

```bash
# Secrets (uma vez; não commitar valores)
fly secrets set --stage \
  REVY_TRAFEGO_SESSION_SECRET=... \
  REVY_TRAFEGO_SERVICE_TOKEN=... \
  REVY_TRAFEGO_BOOTSTRAP_EMAIL=trafego@revy.local \
  REVY_TRAFEGO_BOOTSTRAP_SENHA=... \
  -a app2037

fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
# Se a machine ficar stopped após deploy:
fly machine start <id> -a app2037
```

Artefatos: `deploy/fly/3vm/Dockerfile.app`, `supervisord.conf`, `run-revy-trafego.sh`, `nginx-edge.conf`, `fly.app.toml`, `env.example`.

Subir/desligar lab: `bash deploy/fly/up-all.sh --3vm` / `down-all.sh --3vm`.

### Schemas no volume

- Portal: `/data/portal/portal.db`, Alembic head `0012_revy_trafego_event_outbox`.
- Revy: `/data/revy-trafego/revy_trafego.db`, Alembic head `0001_revy_trafego_baseline`.

O entrypoint executa ambos os Alembics em modo fail-fast antes do supervisord. Readiness do Revy
consulta `vendas_projetadas`; schema incompleto não deve ser anunciado como saudável.

---

## Cutover workers (B5 — **DONE no lab**)

Estado atual no `fly.app.toml` + scripts:

1. `REVY_TRAFEGO_CAPI_WORKER=1` + `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED=1`
2. Portal: `PORTAL_CAPI_RETRY_ENABLED=0`, `PORTAL_META_SPEND_SYNC_ENABLED=0`
3. `run-revy-trafego.sh` força `PORTAL_*=1` só no processo tráfego

Rollback flags portal: zerar `PORTAL_REVY_TRAFEGO_*`.  
Rollback UI dono: `PORTAL_TRAFEGO_UI_LEGACY=1`.  
Rollback workers: inverter os `PORTAL_*_ENABLED` / `REVY_TRAFEGO_*_WORKER`.

---

## Relação com o portal

| Superfície | Onde |
|---|---|
| Pixel, CAPI token, Ads, campanhas, ROI técnico, CTWA audit, leads | **Revy Tráfego** |
| Resultados de mídia (leitura) no dashboard do dono | Portal (API ou local conforme flags) |
| Confirmar venda / CRM / estoque | Portal |

Detalhe de flags e runbook: plano 6.4 em `docs/plans/`.
