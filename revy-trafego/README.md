# Revy Tráfego

Cockpit multi-loja da **equipe Revy** para operação de mídia paga (Pixel, CAPI, Ads spend, campanhas, ROI, auditorias e diagnóstico de leads).

O **portal da loja** (`portal-gestao`) mostra só resultados de negócio ao dono; a config técnica fica aqui.

**Plano canônico (continuar em casa):**  
[`docs/plans/2026-07-28-plano-revy-trafego-separacao.md`](../docs/plans/2026-07-28-plano-revy-trafego-separacao.md)  
→ seção **“O que fazer daqui (runbook ops)”**.

**Status código:** Fase 1+2 na `main`. **Pendente:** deploy lab + smoke + cutover opcional.

---

## Fase 1 / 2 (comportamento)

- Mesmo banco do portal (`REVY_TRAFEGO_DATABASE_URL` ou `PORTAL_DATABASE_URL`).
- Mesma chave Fernet: `PORTAL_ENCRYPTION_KEY` (ou `REVY_TRAFEGO_ENCRYPTION_KEY`).
- Workers CAPI/spend **desligados por padrão** (continuam no portal até cutover).
- API `/v1` com `REVY_TRAFEGO_SERVICE_TOKEN`; portal consome só se flags ligadas.

---

## Local

```bash
cd revy-trafego
python3.12 -m venv .venv   # precisa 3.12+
source .venv/bin/activate
pip install -r requirements.txt
export REVY_TRAFEGO_DATABASE_URL="${PORTAL_DATABASE_URL:-sqlite:///./revy_trafego.db}"
export PORTAL_ENCRYPTION_KEY="${PORTAL_ENCRYPTION_KEY:-}"  # mesma do portal em lab real
export REVY_TRAFEGO_BOOTSTRAP_EMAIL=trafego@revy.local
export REVY_TRAFEGO_BOOTSTRAP_SENHA='troque-isto'
export CHATBOT_API_URL=...
export CHATBOT_API_TOKEN=...
uvicorn app.main:app --reload --port 9010
```

Login: se `gestores_revy` estiver vazia, o bootstrap cria o primeiro admin.

---

## Envs principais

| Env | Default | Notas |
|---|---|---|
| `REVY_TRAFEGO_DATABASE_URL` | = `PORTAL_DATABASE_URL` | **Mesmo** Postgres do portal |
| `REVY_TRAFEGO_SESSION_SECRET` | dev | Cookie `revy_trafego_session` |
| `REVY_TRAFEGO_ENCRYPTION_KEY` | = `PORTAL_ENCRYPTION_KEY` | Tokens CAPI/Ads |
| `REVY_TRAFEGO_BOOTSTRAP_EMAIL` / `_SENHA` | bootstrap | 1º gestor |
| `CHATBOT_API_URL` / `CHATBOT_API_TOKEN` | — | Diagnóstico leads |
| `REVY_TRAFEGO_META_SPEND_SYNC_ENABLED` | `0` | Job 24h |
| `REVY_TRAFEGO_CAPI_WORKER` | `0` | Retry outbox |
| `REVY_TRAFEGO_JOB_SECRET` | vazio | `POST /internal/jobs/meta-spend-sync` |
| `REVY_TRAFEGO_SERVICE_TOKEN` | vazio | Header `X-Service-Token` nas APIs `/v1/*` |

### Portal (flags cutover — default **off**)

| Env | Default | Efeito |
|---|---|---|
| `PORTAL_TRAFEGO_UI_LEGACY` | off | `1` = devolve menus técnicos ao dono |
| `REVY_TRAFEGO_URL` | — | Base deste app |
| `REVY_TRAFEGO_SERVICE_TOKEN` | — | Mesmo token |
| `PORTAL_REVY_TRAFEGO_RESULTADOS` | `0` | `1` = cards ROI via API |
| `PORTAL_REVY_TRAFEGO_VENDA_EVENTS` | `0` | `1` = POST venda-confirmada |
| `PORTAL_REVY_TRAFEGO_TIMEOUT` | `4` | segundos |

### Catálogo

| Env | Notas |
|---|---|
| `REVY_TRAFEGO_PUBLIC_URL` | Prioridade sobre `PORTAL_PUBLIC_URL` para Pixel |
| `PORTAL_PUBLIC_URL` | Fallback / setup atual |

---

## API v1

- `GET /health/live`
- `GET /v1/lojas/{slug}/resultados?periodo=7d|mes` — ROI (service token)
- `POST /v1/lojas/{slug}/eventos/venda-confirmada` — CAPI (idempotente)
- `GET /public/v1/lojas/{slug}/pixel` — Pixel público (sem auth)

---

## Deploy mínimo (passo a passo)

1. Mesmo Postgres + mesma `PORTAL_ENCRYPTION_KEY` do portal.
2. Subir este app na **porta 9010**.
3. Bootstrap email/senha do 1º gestor.
4. Workers deste app em **0**; portal continua processando CAPI/spend.
5. Portal **sem** `PORTAL_TRAFEGO_UI_LEGACY`.
6. Smoke:

| Check | Esperado |
|---|---|
| Login Revy Tráfego | OK |
| Seletor de loja → Config / Campanhas / ROI | OK |
| Portal dono: sem menus Tráfego/Campanhas | OK |
| Portal dono: bloco Resultados | OK (se houver dados) |
| Confirmar venda no portal | CAPI ainda funciona (worker portal) |
| Catálogo Pixel | Ainda via `PORTAL_PUBLIC_URL` |

---

## Cutover (só depois do smoke)

Ordem:

1. `REVY_TRAFEGO_SERVICE_TOKEN` nos dois lados + `REVY_TRAFEGO_URL` no portal  
2. `PORTAL_REVY_TRAFEGO_RESULTADOS=1`  
3. (opc) `PORTAL_REVY_TRAFEGO_VENDA_EVENTS=1`  
4. (opc) catálogo `REVY_TRAFEGO_PUBLIC_URL`  
5. **Por último:** workers CAPI/spend **só** aqui; desligar no portal  

**Nunca** dois workers CAPI no mesmo outbox.

Rollback flags: zerar `PORTAL_REVY_TRAFEGO_*`.  
Rollback UI dono: `PORTAL_TRAFEGO_UI_LEGACY=1`.

---

## Testes

```bash
pytest -q
```

---

## Deploy (resumo)

Porta **9010**. Mesmo Postgres do portal. Não ligar workers CAPI/spend enquanto o portal ainda os processa. Detalhe e checklists: plano 6.4 na pasta `docs/plans/`.
