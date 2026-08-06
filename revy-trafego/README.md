# Revy Control (diretório `revy-trafego`)

> O nome técnico do diretório, do processo e do prefixo público (`/trafego`) continua
> `revy-trafego` durante a migração. A UI e o produto operacional já se chamam
> **Revy Control**, mantendo Tráfego como um módulo interno. Ver
> [design](../docs/superpowers/specs/2026-07-29-revy-control-design.md) e
> [plano por fases](../docs/plans/2026-07-29-plano-revy-control.md).

Cockpit multi-loja da **equipe Revy** para operação de mídia paga (Pixel, CAPI, Ads spend, campanhas, ROI, auditorias e diagnóstico de leads).

A **Revy Loja** (`portal-gestao`) mostra resultados e rotinas da loja; configuração
técnica, prontidão e operação multi-loja ficam aqui.

**Plano canônico:**  
[`docs/plans/2026-07-28-plano-revy-trafego-separacao.md`](../docs/plans/2026-07-28-plano-revy-trafego-separacao.md)

---

## Status atual — Control F0–F6 concluído no código

- Banco próprio; o Alembic head do código é
  `0013_revy_control_readiness_alert_acceptances` (confira `alembic/versions/` se o head
  tiver avançado).
- Vendas chegam pelo outbox criptografado da Loja e são materializadas em
  `vendas_projetadas`; ROI/CAPI não leem tabelas do Portal.
- CAPI assíncrona, `blocked_config`, cancelamento seguro, lease e dedupe por loja.
- Shell Control, Pessoas/Cargos, `AcessoControl`, RBAC, convites, recuperação,
  portfólio, provisionamento e prontidão estão implementados.
- O detalhe da Loja oferece a operação Google Ads em quatro passos: conexão OAuth,
  conta, conversões e métricas.
- **Defaults de código** das flags Control/Google/multi-WA continuam OFF. Em **prod
  `app2037`** o piloto liga Control + delivery + RBAC + dashboard + multi-WA por
  secrets (ops). Google Ads sync/conversões e secrets GCP ainda são residual operacional.
- Referência as-built:
  [`docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`](../docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md).
  Provisão de loja → Portal:
  [`docs/2026-08-02-provisionamento-loja-entitlements.md`](../docs/2026-08-02-provisionamento-loja-entitlements.md).

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
| Portal / Revy Loja | https://app2037.fly.dev |
| Catálogo | https://app2037.fly.dev/catalogo/ (`/loja/` é legado e redireciona 301) |

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

Login: se `gestores_revy` estiver vazia, o bootstrap cria o primeiro admin legado e
projeta sua `Pessoa` e seu `AcessoControl`. A autenticação prefere
`AcessoControl` + `Pessoa`; `GestorRevy` permanece apenas como fallback de
compatibilidade quando ainda não existe projeção.

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
| `REVY_CONTROL_ENABLED` | `0` | Habilita as superfícies `/control/v1` e `/app/control`; desligada, elas respondem 404 |
| `REVY_CONTROL_RBAC_ENABLED` | `0` | Aplica escopo de lojas por vínculo no backend e no seletor; ligar somente após migration/backfill e gate de isolamento da Fase 1 |
| `GOOGLE_ADS_SYNC_ENABLED` | `0` | Liga rotas Control de OAuth/contas/métricas e os quatro passos Google Ads no detalhe da loja em `/app/control`; no lifespan também sobe o worker de métricas |
| `GOOGLE_CONVERSIONS_ENABLED` | `0` | Liga bindings/outbox, hook venda→conversão e worker de outbox Google; também gate do painel de conversões da UI (Parte B) |
| `GOOGLE_CONVERSIONS_WORKER_ENABLED` | = conversions | Override do worker; default segue `GOOGLE_CONVERSIONS_ENABLED` |
| `GOOGLE_CONVERSIONS_WORKER_INTERVAL_SECONDS` | `60` | Intervalo do outbox Google |
| `GOOGLE_CONVERSIONS_WORKER_INITIAL_DELAY_SECONDS` | `30` | Delay inicial do outbox Google |
| `GOOGLE_CONVERSIONS_WORKER_MAX_ATTEMPTS` | `8` | Máx. tentativas por item da outbox |
| `GOOGLE_ADS_METRICS_WORKER_ENABLED` | `0` | Worker diário de métricas (forçado `1` se `GOOGLE_ADS_SYNC_ENABLED`) |
| `GOOGLE_ADS_METRICS_WORKER_INTERVAL_SECONDS` | `86400` | Intervalo (default diário) |
| `GOOGLE_ADS_METRICS_WORKER_INITIAL_DELAY_SECONDS` | `120` | Delay inicial |
| `GOOGLE_ADS_METRICS_WORKER_TIME_WINDOW_DAYS` | `7` | Janela de datas no sync |
| `GOOGLE_ADS_OAUTH_CLIENT_ID` | vazio | OAuth Web client (GCP) |
| `GOOGLE_ADS_OAUTH_CLIENT_SECRET` | vazio | Secret do client OAuth (secret manager) |
| `GOOGLE_ADS_OAUTH_REDIRECT_URI` | vazio | Callback HTTPS do Control; ver "Operação Google Ads no Control" — precisa ser repontado à mão para a rota HTML nova (passo de ops pendente) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | vazio | Developer token (API Center do manager Revy); sem ele a UI bloqueia a conexão real. Os adapters fake continuam disponíveis para testes |
| `GOOGLE_ADS_API_VERSION` | `v19` | Versão REST da Google Ads API |
| `MULTI_WHATSAPP_ENABLED` | `0` | `1` = libera os endpoints proxy de canais WhatsApp e faz a prontidão contar canais ativos |
| `REVY_CONTROL_DASHBOARD_ENABLED` | `0` | Com `REVY_CONTROL_ENABLED=1`, habilita dashboard/resumo e os painéis operacionais no Control |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | `POST /internal/jobs/*` (`meta-spend-sync`, `google-conversions-outbox`, `google-ads-metrics-sync`) |
| `META_GRAPH_API_VERSION` | `v26.0` | Versão compartilhada da Graph/Marketing API (spend, CAPI, diagnóstico e resolução de anúncios) |
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

### Revy Control — Fases 1 e 2 locais

Com `REVY_CONTROL_ENABLED=1`, `/control/v1` expõe cadastro, consulta e transição de
Lojas, vínculos de gestores, auditoria e o corte de Pessoas/Cargos:

- `POST /control/v1/pessoas` — cadastra uma Pessoa Revy sem senha;
- `GET /control/v1/pessoas?email=...` — busca exata por e-mail normalizado;
- `GET /control/v1/pessoas/{pessoa_id}` — consulta uma pessoa por ID;
- `POST /control/v1/lojas/{loja_id}/cargos` — atribui dono, gerente ou vendedor;
- `GET /control/v1/lojas/{loja_id}/cargos` — lista os cargos ativos da Loja;
- `POST /control/v1/lojas/{loja_id}/cargos/{cargo_id}/revogar` — encerra a atribuição
  identificada, preservando seu histórico.

`/app/control/lojas` oferece o painel administrativo para listar, criar e administrar
Lojas. No detalhe da Loja, o Admin busca ou cadastra a pessoa por e-mail, atribui vários
cargos e revoga cada atribuição pelo seu `cargo_id`. A Loja só vira `pronta` com ao
menos um Dono ativo **e** com acesso ativável (`AcessoControl` em `pendente` ou
`ativo`); o último Dono ativo fica protegido nos estados operacionais.

O schema local `acessos_control` e seu backfill são aditivos e idempotentes. Para cada
gestor legado, a reconciliação reutiliza ou cria a `Pessoa`, preserva o ID de
`GestorRevy` em `AcessoControl.id` e `gestor_legado_id` e copia o hash de senha sem
alterá-lo ou expor senha em texto puro. O bootstrap também mantém essa projeção.

Login, sessão e `Actor` preferem `AcessoControl` + `Pessoa`. Um acesso ativo sem
`gestor_legado_id` autentica e opera o Control; convite de ativação não cria mais
`GestorRevy`. Gestores legados sem projeção continuam autenticáveis; quando a projeção
existe, o estado/versão de `AcessoControl` mandam. Recuperação e reativação sincronizam
o legado somente se houver vínculo.

O snapshot de provisionamento enfileira para **chatbot, estoque, portal, motor e
catalogo** (`control_provisioning_outbox` / migration `0009`). Worker opt-in
(`REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED`) entrega e reprocessa `failed` (máx. 5).

Tokens por destino: Chatbot/Estoque/Motor Bearer (por slug ou JSON);
Portal/Catálogo `X-Service-Token` (`PORTAL_SERVICE_TOKEN`, `CATALOGO_SERVICE_TOKEN`).
Import push: `POST /control/v1/imports/portal-usuarios`. Isolamento de permissões:
`control:*` vs `store:*` em `app/control/permissions.py`.

Com `REVY_CONTROL_ENABLED=0`, as superfícies Control respondem 404.

`REVY_CONTROL_RBAC_ENABLED=1` aplica o escopo de vínculos ao seletor e às requisições
existentes. As duas flags permanecem default off; não ativar no lab antes de concluir
inventário, restore drill, migrations/backfills e o gate de isolamento. O Alembic head
local é `0013_revy_control_readiness_alert_acceptances`; confirme o estado do lab antes
do rollout do Control.

### Operação Google Ads no Control (Parte B — implementada)

Desenho em `docs/superpowers/specs/2026-07-29-telas-canais-wa-google-design.md` (Parte B).
O detalhe da Loja (`/app/control/lojas/{id}`) oferece o fluxo conexão → conta →
conversões → métricas, sem endpoint novo de API e gated por
`GOOGLE_ADS_SYNC_ENABLED`; o painel de conversões também exige
`GOOGLE_CONVERSIONS_ENABLED`. Contas MCC aparecem desabilitadas, conversion actions
vêm da lista do Google e métricas usam por padrão os últimos sete dias. Autorização
segue no domínio: admin Revy **ou** gestor responsável pela Loja; colaborador recebe
403. Sem client id, client secret, redirect URI ou developer token, a tela informa que
o Google não está configurado e não oferece o botão de conexão.

**Passo manual de ops — obrigatório antes do rollout.** A rota HTML implementada é
`GET /app/control/google-ads/oauth/callback`, que completa o OAuth e redireciona para
`/app/control/lojas/{id}?ok=google_conectado`. Para a UI funcionar:

1. registrar a rota HTML nova como URI de redirecionamento autorizado no **Google Cloud
   Console** (no lab, com o prefixo do edge:
   `https://app2037.fly.dev/trafego/app/control/google-ads/oauth/callback`);
2. repontar o secret `GOOGLE_ADS_OAUTH_REDIRECT_URI` para a mesma URL
   (`fly secrets set GOOGLE_ADS_OAUTH_REDIRECT_URI=... -a app2037`).

Os dois têm de casar exatamente — divergência dá `redirect_uri_mismatch` no Google, sem
pista no log do Control. O endpoint JSON legado
`GET /control/v1/google-ads/oauth/callback` continua existindo para compatibilidade;
se algum ambiente ainda apontar para ele, o admin voltará do Google para JSON cru.
Sem client id/secret e developer token, o painel permanece indisponível para conexão.

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

- Revy Loja: `/data/portal/portal.db`; head esperado pelo código:
  `0015_auditoria_dominio_canal`.
- Revy Control: `/data/revy-trafego/revy_trafego.db`; head esperado pelo código:
  `0013_revy_control_readiness_alert_acceptances`.

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
| Pixel, CAPI token, Ads, campanhas, ROI técnico, CTWA audit, leads | **Revy Control** |
| Resultados de mídia (leitura) no dashboard do dono | Revy Loja (API ou local conforme flags) |
| Confirmar venda / CRM / estoque | Revy Loja |

Detalhe de flags e runbook: plano 6.4 em `docs/plans/`.
