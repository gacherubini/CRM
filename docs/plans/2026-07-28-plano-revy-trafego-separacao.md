# Plano — Revy Tráfego separado do Portal da loja

> **Status 2026-07-28/29: FASE 3 IMPLANTADA NO LAB** — banco próprio, projeção de vendas e
> outbox Portal → Revy em `origin/main` (`98cefe4`) e no Fly `app2037` v28. Portal no head `0012`;
> Revy no head `0001`; snapshot e smoke registrados no handoff.
> Spec: [`docs/superpowers/specs/2026-07-28-revy-trafego-separacao-portal-design.md`](../superpowers/specs/2026-07-28-revy-trafego-separacao-portal-design.md)  
> App: `revy-trafego/` · README ops (canônico): [`revy-trafego/README.md`](../../revy-trafego/README.md)

**Eixo:** C · CRM / marketing  
**Depende de:** campanhas+ROI DONE, Meta spend MVP, CTWA MVP, resultados dono no dashboard  
**Não reimplementar:** fórmula ROI, match UTM, CAPI Purchase, spend Meta — só **extrair e reorganizar**

**Goal:** Equipe Revy opera tráfego multi-loja num app próprio (config + resultados + diagnóstico). Portal da loja mostra só resultados de negócio (mesmas métricas, UI limpa), sem Pixel/tokens/CRUD técnico.

**Architecture:** Strangler. Fase 1 = app `revy-trafego` + auth interna + port da superfície técnica + slim do portal (DB/schema compartilhado). Fase 2 = API de resultados + hooks de venda (flags off por default). Integração HTTP no alvo.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, Jinja2, pytest, httpx — mesmo padrão do `portal-gestao`.

**Commits de referência (main):**
- `623cc29` — design + planos
- `5da09e0` — Fase 1 (app + slim portal)
- `60e5d80` — Fase 2 (API + client portal + catálogo URL)

---

## Decisões (não reabrir sem motivo)

1. Gestor = **equipe Revy** (todas as lojas no seletor).
2. Cliente = **só resultados** (gasto, leads, vendas, CPL, CPA, ROAS).
3. App **separado** (`revy-trafego`), não só papel no portal.
4. Fonte da verdade de mídia → Revy Tráfego (médio prazo).
5. Resultados **nos dois** apps; **uma** fórmula/fonte no alvo (API).
6. Diagnóstico com lead/conversa (proxy chatbot) permitido.
7. Migração **strangler**, não big bang.
8. Flags de cutover **default off** — portal continua calculando ROI local e CAPI local até ops ligar.

---

## Fases e planos detalhados

| Fase | Plano detalhado | Entrega | Status |
|---:|---|---|---|
| **1** | [Fase 1](../superpowers/plans/2026-07-28-revy-trafego-fase1-app-multi-loja.md) | Cockpit Revy + cliente sem menus técnicos | **CÓDIGO FEITO** |
| **2** | [Fase 2](../superpowers/plans/2026-07-28-revy-trafego-fase2-api-cutover.md) | API + flags portal + pixel URL catálogo | **CÓDIGO FEITO** (flags off) |
| **ops** | **Seção abaixo** + README | Deploy lab + smoke + cutover B1–B5 | **DONE no lab** |
| **3** | seção abaixo | Split DB, projeção de vendas e outbox criptografado | **DONE NO LAB** |

## Fase 3 — contrato implementado

- Revy tem Alembic e banco próprios; o Portal não é mais consultado por SQL.
- Portal grava evento de venda no mesmo commit e um worker o entrega ao Revy.
- Revy rejeita snapshots antigos e mantém projeção idempotente por `(venda_id, loja_slug)`.
- CAPI é persistida mesmo sem configuração e enviada somente por worker.
- Cancelamento mais novo impede confirmação atrasada e terminaliza CAPI ainda pendente.
- Payload Portal → Revy é cifrado em repouso; retry usa backoff e lease recuperável.

O restante deste runbook descreve o cutover anterior com banco compartilhado e deve ser tratado
como histórico. O resultado do cutover Fase 3 está registrado no topo de
`docs/handoff-contexto.md`.

### Critério de pronto código (já atendido)

- [x] App `revy-trafego` com auth, multi-loja, Pixel/campanhas/ROI/auditoria/diagnóstico
- [x] Portal slim: sem nav Tráfego/Campanhas; `pode_ver_resultados_midia`
- [x] API `/v1/.../resultados` e `/eventos/venda-confirmada`
- [x] Client portal + flags
- [x] Catálogo: `REVY_TRAFEGO_PUBLIC_URL` prioriza Pixel

### Critério de pronto ops

- [x] `revy-trafego` no ar no lab (porta **9010**, path `/trafego`)
- [x] Smoke checklist (login, loja, config, leads/conversas, API)
- [x] Flags API ligadas (`RESULTADOS` + `VENDA_EVENTS`)
- [x] Workers CAPI/spend **só** no Revy Tráfego (B5; portal `PORTAL_*_ENABLED=0`)
- [x] Snapshot pré-cutover e migrações fail-fast
- [x] Portal em `0012`, Revy em banco próprio no head `0001`
- [x] Release `app2037` v28 com health/checks passando

---

# Runbook ops (lab DONE 2026-07-28; B5 opcional)

Código + deploy lab na **main**/Fly. Detalhe operacional atual: [`revy-trafego/README.md`](../../revy-trafego/README.md).

## A) Deploy mínimo seguro (recomendado primeiro)

Sobe o app; equipe Revy opera nele. Portal da loja já está slim. **Não** precisa ligar flags da Fase 2 ainda.

### Envs — `revy-trafego`

| Env | Obrigatório | Valor / notas |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | sim | **Mesmo Postgres** do portal (`PORTAL_DATABASE_URL`) |
| `PORTAL_ENCRYPTION_KEY` ou `REVY_TRAFEGO_ENCRYPTION_KEY` | sim | **Mesma** chave Fernet do portal (senão tokens CAPI/Ads não decriptam) |
| `REVY_TRAFEGO_SESSION_SECRET` | sim | Cookie `revy_trafego_session` (diferente do portal) |
| `REVY_TRAFEGO_BOOTSTRAP_EMAIL` | 1ª subida | Cria admin se `gestores_revy` vazia |
| `REVY_TRAFEGO_BOOTSTRAP_SENHA` | 1ª subida | Trocar depois do 1º login |
| `REVY_TRAFEGO_BOOTSTRAP_NOME` | opcional | default “Equipe Tráfego” |
| `CHATBOT_API_URL` | sim (diagnóstico) | Mesmo do portal |
| `CHATBOT_API_TOKEN` | sim (diagnóstico) | Mesmo do portal |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | manter `0` | Job spend — portal ainda processa |
| `REVY_TRAFEGO_CAPI_WORKER` | manter `0` | Retry CAPI — portal ainda processa |
| `REVY_TRAFEGO_SERVICE_TOKEN` | só se for ligar API | Compartilhado com portal depois |

### Envs — `portal-gestao` (deploy mínimo)

| Env | Valor |
|---|---|
| `PORTAL_TRAFEGO_UI_LEGACY` | **não setar** (ou `0`) — dono sem menus técnicos |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `0` (default) — ROI local no dashboard |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `0` (default) — CAPI só pelo fluxo atual do portal |
| Workers spend/CAPI do portal | **continuar ligados** como hoje |

### Envs — catálogo (deploy mínimo)

| Env | Valor |
|---|---|
| `PORTAL_PUBLIC_URL` | Continua apontando pro **portal** (pixel ainda serve de lá) |
| `REVY_TRAFEGO_PUBLIC_URL` | **não setar** ainda |

### Serviço

- Porta **9010**
- Dockerfile: `revy-trafego/Dockerfile`
- Health: `GET /health/live`
- Detalhe local: `revy-trafego/README.md`

### Smoke manual (~15 min) após subir

| # | Onde | O quê | OK se |
|---:|---|---|---|
| 1 | Revy Tráfego | Login com bootstrap | Entra em `/app` |
| 2 | Revy Tráfego | Selecionar loja (slug existente ou digitar) | Abre Config |
| 3 | Revy Tráfego | Config Pixel / Campanhas / ROI / CTWA / Pixel audit | Telas 200 |
| 4 | Revy Tráfego | Diagnóstico leads (chatbot up) | Lista ou erro claro de chatbot |
| 5 | Portal (dono) | Visão geral | **Sem** links Tráfego/Campanhas/CTWA/Pixel/ROI técnico |
| 6 | Portal (dono) | Bloco “Resultados do tráfego” | Aparece (se houver dados de campanha/gasto) |
| 7 | Portal | Confirmar venda de teste | Continua `?ok=confirmada`; CAPI outbox no portal |
| 8 | Catálogo | Página com Pixel | `pixel_id` ainda carrega (via portal) |

### Rollback UI do dono (se precisar)

```bash
PORTAL_TRAFEGO_UI_LEGACY=1
```

Restaura menus técnicos de tráfego no portal para dono/gerente. Dados intactos (shared DB).

---

## B) Cutover opcional (só depois do smoke A verde)

Ordem **importa**. Nunca dois workers CAPI/spend ao mesmo tempo.

### B1 — Token de serviço

```bash
# mesmo valor nos dois lados
REVY_TRAFEGO_SERVICE_TOKEN=<secreto-longo>
```

Portal também precisa de:

```bash
REVY_TRAFEGO_URL=https://<host-revy-trafego>   # ou http interno :9010
REVY_TRAFEGO_SERVICE_TOKEN=<mesmo-secreto>
```

### B2 — Resultados no portal via API

```bash
PORTAL_REVY_TRAFEGO_RESULTADOS=1
```

- Dashboard tenta API; se offline → fallback local + não quebra CRM.
- Desligar: `PORTAL_REVY_TRAFEGO_RESULTADOS=0`.

Smoke: cards do dono batem com ROI no Revy Tráfego (mesmo período).

### B3 — Notificar venda no Revy Tráfego

```bash
PORTAL_REVY_TRAFEGO_VENDA_EVENTS=1
```

- Portal ainda roda `publish_conversion` local **e** notifica a API (idempotente por `event_id`).
- Só faz sentido se shared DB e/ou worker for migrado com cuidado.

### B4 — Pixel do catálogo no Revy Tráfego

```bash
# catálogo
REVY_TRAFEGO_PUBLIC_URL=https://<host-revy-trafego>
# (prioridade sobre PORTAL_PUBLIC_URL)
```

Smoke: vitrine ainda carrega Pixel ID. Rollback: remover env (volta portal).

### B5 — Workers só no Revy Tráfego (último passo)

1. Revy Tráfego:
   - `REVY_TRAFEGO_CAPI_WORKER=1`
   - `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED=1` (se quiser spend job)
2. Portal:
   - `PORTAL_CAPI_RETRY_ENABLED=0` (ou equivalente que desliga o job)
   - `PORTAL_META_SPEND_SYNC_ENABLED=0`
3. Smoke: confirmar venda → outbox delivered; sync spend manual no Revy Tráfego.

**Nunca** deixar CAPI worker nos dois processos no mesmo outbox.

---

## C) Mapa rápido de envs (todos)

### Revy Tráfego

| Env | Default | Notas |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | = portal DB | Shared schema |
| `REVY_TRAFEGO_SESSION_SECRET` | dev | |
| `REVY_TRAFEGO_ENCRYPTION_KEY` | = `PORTAL_ENCRYPTION_KEY` | Fernet |
| `REVY_TRAFEGO_BOOTSTRAP_EMAIL` / `_SENHA` / `_NOME` | bootstrap | Só se tabela vazia |
| `CHATBOT_API_URL` / `CHATBOT_API_TOKEN` | — | Diagnóstico |
| `REVY_TRAFEGO_SERVICE_TOKEN` | vazio | API `/v1` |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `0` | Job 24h |
| `REVY_TRAFEGO_CAPI_WORKER` | `0` | Retry outbox |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | Cron spend |

### Portal

| Env | Default | Notas |
|---|---|---|
| `PORTAL_TRAFEGO_UI_LEGACY` | off | `1` = menus técnicos de volta |
| `REVY_TRAFEGO_URL` | — | Base do app tráfego |
| `REVY_TRAFEGO_SERVICE_TOKEN` | — | = token do tráfego |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `0` | Cards via API |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `0` | POST venda-confirmada |
| `PORTAL_REVY_TRAFEGO_TIMEOUT` | `4` | segundos |
| `PORTAL_META_SPEND_SYNC_ENABLED` | `1` | Manter até B5 |
| `PORTAL_CAPI_RETRY_ENABLED` | típico on | Manter até B5 |

### Catálogo

| Env | Default | Notas |
|---|---|---|
| `REVY_TRAFEGO_PUBLIC_URL` | — | Prioridade pixel |
| `PORTAL_PUBLIC_URL` | — | Fallback / atual |
| `META_PIXEL_ID` | — | Fallback ops |

### API (contratos)

- `GET /v1/lojas/{slug}/resultados?periodo=7d|mes` — header `X-Service-Token`
- `POST /v1/lojas/{slug}/eventos/venda-confirmada` — body venda + ids
- `GET /public/v1/lojas/{slug}/pixel` — público

---

## D) Testes locais (sem deploy)

```bash
# Revy Tráfego (Python 3.12+)
cd revy-trafego && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q

# Portal (subset mídia)
cd portal-gestao && .venv/bin/pytest tests/test_trafego.py tests/test_resultados_dono.py \
  tests/test_client_revy_trafego.py tests/test_campanhas.py tests/test_vendas.py -q
```

Local multi-processo: mesmo `PORTAL_DATABASE_URL` / encryption key; portal `:9000`, tráfego `:9010`.

---

## E) O que **não** fazer em casa sem necessidade

- Reescrever ROI / campanhas / CAPI
- Big bang de split de banco
- Ligar workers nos dois lados
- Deploy forçado das flags se o lab mínimo ainda não passou smoke A

---

## Fases código (histórico)

```text
Fase 1  scaffold + auth + multi-loja + port UI + slim portal     DONE
Fase 2  API v1 + client portal + flags + catálogo URL             DONE
Ops     deploy lab + smoke A + flags B1–B3                        DONE (2026-07-28)
B5      workers CAPI/spend só no Revy Tráfego                     DONE (2026-07-28)
```

---

## Impacto em docs

| Doc | Estado |
|---|---|
| `revy-trafego/README.md` | Ops + envs + API (espelhar runbook) |
| `docs/trafego-pago-loja.md` | Cliente: setup via equipe Revy |
| `docs/contexto-compacto.md` | Eixo C → deploy/cutover |
| `portal-gestao/README.md` | Atualizar: UI técnica saiu do dono |
| `docs/fluxo-utm-pixel-ctwa-meta.md` | Atualizar dono do Pixel quando cutover |
| Tutoriais PDF | Regenerar após UI/ops estáveis |

---

## Relação com planos DONE

| Plano | Relação |
|---|---|
| `2026-07-20-plano-trafego-pago-crm-campanhas-roi.md` | DONE — domínio movido/portado |
| `2026-07-21-plano-conversao-atribuicao-insights.md` | Resultados dono / CAPI — slim + cutover |
| `2026-07-22-plano-ctwa-...` / `meta-spend-api` | Telas no Revy Tráfego; jobs no cutover B5 |

---

## Pacote comercial (visão)

- **Portal da loja:** CRM + resultados de mídia (leitura).
- **Revy Tráfego:** operação interna multi-loja (não self-serve de token ao lojista no MVP).
