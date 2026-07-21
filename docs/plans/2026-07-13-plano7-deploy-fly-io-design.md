# Plano #7 — Deploy da suíte no Fly.io (design)

> **Status 2026-07-15: DONE (lab subiu)** — design + implementação da 1ª subida concluídos.  
> **Atualização 2026-07-20:** lab **parado** (machines stopped, apps/volumes mantidos). Uso
> preferido = **local**. Reativar só com `deploy/fly/up-all.sh` e pedido explícito do dono.
> Ambiente lab Fly (`crm-419` / `gru`) com apps da suíte; ops do dia a dia em
> `deploy/fly/up-all.sh`, `down-all.sh` e `docs/contexto-compacto.md` (checkpoint Fly).
> Este arquivo é **referência de arquitetura**, não checklist a reexecutar do zero.
> Implementação histórica (checklist SUPERSEDED):  
> `_archive/2026-07-13-plano7-deploy-fly-io-implementacao.md`.
>
> Data original: 2026-07-13 · Objetivo: subir os 5 produtos no Fly.io (WhatsApp ligado).
> Filosofia: produtos vendáveis separadamente — cada produto = deploy próprio.

## 1. Objetivo e escopo

Colocar a suíte automotiva no ar no **Fly.io**, região **`gru` (São Paulo)** — menor latência
para a loja e residência de dados (LGPD). Escopo aprovado com o dono:

- **Produção real** — loja vai operar; bot WhatsApp **ligado** (Gemini já configurado e testado local).
- **Todos os 5 produtos**: Motor, Portal, Estoque, Catálogo, Chatbot (+ Evolution + n8n).
- **1 Postgres** compartilhado (ver §4) + **1 Redis** (Upstash) para cache da Evolution.

Não é objetivo deste plano: reescrever serviços, trocar Gemini por Claude, ou plugar novos
bancos reais. O único driver bancário real hoje é o **Santander** (RPA Playwright).

## 2. Arquitetura no Fly.io — 7 apps

Estratégia: **agrupar serviços que compartilham a mesma imagem como *process groups*** dentro de
um mesmo app (o Fly permite tamanho de máquina distinto por processo). Reduz de ~11 containers
para **7 apps**, sem custo extra (o Fly cobra por máquina-segundo e RAM, não por app).

| App Fly | Imagem (build) | Processos | Exposição | Volume |
|---------|----------------|-----------|-----------|--------|
| **motor** | `motor-simulacao/` | `api` (leve) + `worker` (Chromium/Xvfb, 2GB, always-on) | privado (6PN) | `motor_data` (storage_state + screenshots) |
| **estoque** | `estoque-api/` | `api` (público read + privado) + `outbox` (worker) | api público, outbox privado | — |
| **chatbot** | `chatbot-api/` | `api` | privado (n8n chama) | — |
| **portal** | `portal-gestao/` | web (:9000) | **público HTTPS** | `portal_data` (SQLite `portal.db`) |
| **catalogo** | `catalogo-publico/` | web | **público HTTPS** | `catalogo_data` (SQLite `catalogo.db`) |
| **evolution** | `evoapicloud/evolution-api:latest` | Evolution API | **público** (QR + webhook), always-on | `evolution_instances` (sessão WhatsApp) |
| **n8n** | `docker.n8n.io/n8nio/n8n` | editor + engine | **público** (login), always-on | `n8n_data` |

### Rede
- Serviços internos (**motor-api, chatbot-api, estoque-api**) ficam **sem IP público**,
  acessíveis só pela rede privada Fly. Comunicação por DNS interno (`<app>.internal` /
  `.flycast`) — o plano de implementação define qual usar por serviço.
- **Públicos** (IP + HTTPS gerenciado pelo Fly): portal, catalogo, evolution, n8n.
- URLs internas nos secrets, ex.: `MOTOR_URL=http://motor.flycast:8000`,
  `ESTOQUE_API_URL=http://estoque.flycast:8000`.

### Autostop (economia)
Os 5 serviços HTTP internos/públicos de request-resposta (**motor-api, estoque-api,
chatbot-api, portal, catalogo**) usam **autostop → escala a zero** quando ociosos e acordam no
próximo request. Ficam **always-on** (não escalam a zero): `motor-worker`, `estoque-outbox`,
`evolution`, `n8n`, Postgres.

## 3. Redis
**Upstash Redis** (integração Fly). Tier gratuito cobre o cache da Evolution na fase de teste.
Secret `CACHE_REDIS_URI` no app evolution.

## 4. Postgres — self-managed na fase de teste, MPG no go-live

- **Fase de teste:** **Fly Postgres self-managed** — máquina `shared-cpu-1x` pequena + volume
  (~$3/mês). Bancos: `motor`, `estoque`, `chatbot`, `evolution` (criados no mesmo cluster).
  O plano inclui **backup diário** (`pg_dump` agendado ou snapshot de volume) para reduzir o
  risco de nó único.
- **Go-live real (loja atendendo cliente):** migrar para **Fly Managed Postgres (MPG)** —
  backup automático + PITR + HA. Migração é `pg_dump`/`pg_restore` (trivial enquanto pequeno).
- **Regra de corte:** trocar para MPG **no dia em que a loja começar a atender cliente real**
  pelo WhatsApp. Antes disso, self-managed.

Portal e Catálogo **não** usam Postgres — usam **SQLite em volume Fly** (`portal.db`,
`catalogo.db`). Precisam de volume persistente e backup próprio.

## 5. Inventário de secrets (o dono preenche na plataforma Fly)

| App | Secrets | Origem / geração |
|-----|---------|------------------|
| **motor** | `MOTOR_ENCRYPTION_KEY`, `MOTOR_METRICS_TOKEN`, `DATABASE_URL` | Fernet; token aleatório; URL PG (db `motor`) |
| **estoque** | `ESTOQUE_OUTBOX_KEY`, `DATABASE_URL` | CLI `gerar-chave-outbox`; db `estoque` |
| **chatbot** | `DATABASE_URL`, `SIMULATION_PROVIDER=http`, `MOTOR_URL`, `MOTOR_TOKEN`, `ESTOQUE_API_URL`, `ESTOQUE_API_TOKEN`, `ESTOQUE_PUBLIC_URL` | db `chatbot`; URLs internas; tokens via CLI |
| **portal** | `PORTAL_SESSION_SECRET`, `PORTAL_IDENTITY_HMAC_SECRET`, `PORTAL_ENCRYPTION_KEY`, `PORTAL_SECURE_COOKIE=1`, `MOTOR_URL`+`MOTOR_TOKEN`, `ESTOQUE_API_URL`+`ESTOQUE_API_TOKEN`, `CHATBOT_API_URL`+`CHATBOT_API_TOKEN` | `PORTAL_ENCRYPTION_KEY` = Fernet (**cifra credenciais dos bancos**) |
| **catalogo** | `ESTOQUE_PUBLIC_API_URL`, `ESTOQUE_PUBLIC_API_TOKEN`, `CATALOGO_PUBLIC_BASE_URL`, `CATALOGO_SECURE_COOKIE=1` | base URL = `https://<catalogo>.fly.dev` |
| **evolution** | `EVOLUTION_API_KEY`, `DATABASE_CONNECTION_URI`, `CACHE_REDIS_URI`, `CONFIG_SESSION_PHONE_VERSION` | invente key; db `evolution`; URI Upstash |
| **n8n** | `N8N_ENCRYPTION_KEY` | **chave do Gemini NÃO é secret Fly** — fica na credencial dentro do n8n |

> A chave da **API Google Gemini** é cadastrada como credencial *dentro do n8n* (UI), cifrada
> pelo `N8N_ENCRYPTION_KEY`. Não vai como secret do Fly.

## 6. Ordem de deploy (dependências e tokens)

Há um ovo-e-galinha: `MOTOR_TOKEN`, `ESTOQUE_API_TOKEN`, `CHATBOT_API_TOKEN` são **criados por
CLI dentro de cada serviço depois que ele sobe**. Ordem:

1. **Postgres** (self-managed) + criar os 4 bancos + **Redis** (Upstash).
2. **motor** (api+worker). Rodar CLI para criar `MOTOR_TOKEN`. Verificar `/health/ready`.
3. **estoque** (api+outbox). Rodar CLI para criar `ESTOQUE_API_TOKEN` (e token público do catálogo).
4. **catalogo** — consome estoque (token público).
5. **chatbot** — recebe `MOTOR_TOKEN` + `ESTOQUE_API_TOKEN`. Rodar CLI p/ `CHATBOT_API_TOKEN`.
6. **portal** — recebe `MOTOR_TOKEN`, `ESTOQUE_API_TOKEN`, `CHATBOT_API_TOKEN`.
7. **evolution** — subir, parear WhatsApp (escanear QR uma vez → grava no volume).
8. **n8n** — subir, importar workflow, cadastrar credencial Gemini + Evolution, apontar webhook
   Evolution→n8n, **ativar** o workflow.

### Fases
- **Fase 1 — núcleo:** passos 1–6. Validar suíte fim-a-fim + **Santander RPA real** (ver risco §7).
- **Fase 2 — WhatsApp:** passos 7–8. Go-live do bot.

## 7. Riscos e mitigação

1. **RPA de banco a partir de IP de datacenter (maior risco).** Santander/Akamai pode bloquear
   o Chromium do `motor-worker` mesmo *headed*, porque o IP do Fly é de datacenter. **Mitigação:**
   testar RPA logo na Fase 1; se bloquear, plano B é proxy residencial ou rodar o worker fora do
   Fly. Não bloqueia os outros 4 produtos.
2. **Bot em produção / LGPD.** Cliente real = dado real: garantir consentimento antes de dado
   pessoal, CPF cifrado, retenção 6 meses. Sessão WhatsApp persistente no volume (senão repareia).
3. **2 testes do Motor falhando** (mock `Santander` vs driver real homônimo) — não bloqueia deploy,
   mas a suíte não está 100% verde. Registrar; corrigir fora deste plano.
4. **Custo.** Ver §8. Alavancas: parar `motor-worker` quando não testa RPA; autostop; PG self-managed.

## 8. Custo estimado (fase de teste)

| Item | ~Custo/mês |
|------|-----------|
| motor-worker (shared-2x, 2GB, 24/7) | $15–22 (**$0 se parado quando não testa RPA**) |
| evolution (512MB–1GB, 24/7) | $4–6 |
| n8n (512MB, 24/7) | $4 |
| estoque-outbox (256MB) | $2 |
| Postgres self-managed | ~$3 |
| Redis (Upstash free) | ~$0 |
| HTTP com autostop (motor-api, estoque-api, chatbot-api, portal, catalogo) | ~$0–5 ociosos |
| Volumes (~6 × 1–3GB) | ~$1–3 |
| **Total enxuto** (worker parado fora do teste) | **~$15–25** |
| **Total tudo 24/7** | **~$50–70** |

Fora do Fly: **API Gemini** (tier grátis cobre o teste), **chip WhatsApp**, domínio (opcional —
o Fly já dá `*.fly.dev` com HTTPS).

*Valores são estimativas (preços do Fly mudam); confirmar na doc oficial ao executar.*

## 9. Entregáveis do plano de implementação

O plano detalhado (próximo passo, escrito por agente) deve produzir:
- Um `fly.toml` por app (7), com process groups, tamanhos de máquina, `[mounts]` de volume,
  `[http_service]` com autostop onde aplicável, e `internal_port` correto.
- Comandos `fly apps create` / `fly volumes create` / `fly secrets set` / `fly deploy` na ordem §6.
- Provisionamento do Postgres self-managed + criação dos 4 bancos + Upstash Redis.
- Passo de criação dos tokens de serviço via CLI (Motor/Estoque/Chatbot).
- Checklist de pareamento da Evolution (QR) e import/ativação do workflow n8n.
- Rotina de backup diário (Postgres + volumes SQLite).
- Checklist de verificação por app (`/health/ready`, login Portal, simulação, mensagem WhatsApp).
- Passo marcado de **migração self-managed → MPG** no go-live real.

## 10. Decisões registradas

- 7 apps (process-groups), **não** monólito — Fly cobra por RAM/máquina-segundo, não por app;
  o split deixa os HTTP dormirem (mais barato no teste) e preserva independência dos produtos.
- Região `gru`. Rede: internos sem IP público.
- Postgres self-managed no teste → MPG no go-live. Portal/Catálogo em SQLite+volume.
- Gemini (não Claude) como NLU, via credencial no n8n. README corrigido nesta sessão.
