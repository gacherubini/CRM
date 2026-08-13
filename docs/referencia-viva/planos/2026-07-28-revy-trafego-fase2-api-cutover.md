# Revy Tráfego Fase 2 — API de resultados + cutover

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o Revy Tráfego a **única fonte** de resultados de mídia e da config Pixel/CAPI/spend: portal e catálogo consomem HTTP; workers rodam só no Revy Tráfego; código morto de UI/cálculo duplicado sai do portal.

**Architecture:** API versionada `/v1/...` com service token. Portal ganha `clients/revy_trafego.py`. Catálogo aponta pixel para URL do Revy Tráfego. Confirmação de venda no portal faz `POST` de evento; outbox CAPI processado no Revy Tráfego. Schema ainda pode ser shared DB; escrita de mídia só via app de tráfego.

**Tech Stack:** FastAPI, httpx, pytest; envs `REVY_TRAFEGO_URL`, `REVY_TRAFEGO_SERVICE_TOKEN`.

**Spec:** `docs/referencia-viva/specs/2026-07-28-revy-trafego-separacao-portal-design.md`
**Depende de:** Fase 1 DONE e utilizável.

## Global Constraints

- Contrato de pixel público **estável** (campos JSON atuais do portal).
- ROI: uma implementação (`roi_calc` no revy-trafego); portal **não** reimplementa.
- Timeout HTTP portal→tráfego: curto (3–5s); falha → cards “indisponível” sem derrubar o CRM.
- Service token obrigatório em produção; testes usam header fixo.
- Cutover de workers: **nunca** dois CAPI workers ativos no mesmo outbox.
- Multi-tenant: service API sempre escopada por `loja_slug` do path (portal só pede a **própria** loja do usuário).

## Mapa de arquivos

| Path | Responsabilidade |
|---|---|
| `revy-trafego/app/api_v1.py` | Rotas JSON service + public pixel (se ainda em main) |
| `revy-trafego/app/service_auth.py` | Validar `X-Service-Token` |
| `portal-gestao/app/clients/revy_trafego.py` | Client resultados + venda-confirmada |
| `portal-gestao/app/main.py` | Dashboard consome client; venda POST evento; desliga workers |
| `portal-gestao/app/resultados_dono.py` | Adapter de dict da API → view model (sem SQL campanhas) |
| `catalogo-publico/app/config.py` + provider pixel | URL Revy Tráfego |
| `portal-gestao` remove rotas legadas de escrita mídia (se ainda existirem) |

---

### Task 1: Service auth + `GET` resultados

**Files:**
- Create: `revy-trafego/app/service_auth.py`
- Create: `revy-trafego/app/api_v1.py`
- Modify: `revy-trafego/app/main.py` (include router)
- Modify: `revy-trafego/app/config.py` (`service_token`)
- Create: `revy-trafego/tests/test_api_resultados.py`

**Interfaces:**
- Header: `X-Service-Token: <token>` (compare_digest).
- `GET /v1/lojas/{loja_slug}/resultados?periodo=7d|mes`
  Query opcional: `inicio`, `fim`, `modo=last|first` (default last).
- Response 200:

```json
{
  "loja_slug": "loja-x",
  "periodo": {"chave": "7d", "inicio": "2026-07-21", "fim": "2026-07-28"},
  "totais": {
    "gasto": "100.00",
    "leads": 10,
    "vendas": 2,
    "faturamento": "5000.00",
    "cpl": "10.00",
    "cpa": "50.00",
    "roas": "50.00"
  },
  "canais": [],
  "melhor_campanha": null,
  "campanhas": [],
  "vendas_sem_campanha": 0,
  "leads_sem_campanha": 0
}
```

Decimais como **string** quantize 0.01 (evitar float JSON). null para CPL/CPA/ROAS quando denominador zero.

- [ ] **Step 1: Testes 401 sem token; 200 com totais**

```python
def test_resultados_exige_token(client):
    r = client.get("/v1/lojas/loja-teste/resultados?periodo=7d")
    assert r.status_code == 401

def test_resultados_ok(client, service_headers, seed_roi):
    r = client.get("/v1/lojas/loja-teste/resultados?periodo=7d", headers=service_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["loja_slug"] == "loja-teste"
    assert "totais" in body
    assert body["totais"]["leads"] == seed_roi.leads
```

- [ ] **Step 2: Implementar `api_v1` reusando `roi_calc` + leads chatbot como o ROI HTML já faz**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(revy-trafego): API v1 resultados com service token"
```

---

### Task 2: Client no portal + dashboard via API

**Files:**
- Create: `portal-gestao/app/clients/revy_trafego.py`
- Modify: `portal-gestao/app/config.py` (`revy_trafego_url`, `revy_trafego_service_token`, `revy_trafego_resultados_enabled`)
- Modify: `portal-gestao/app/main.py` (handler `/app` resultados)
- Modify: `portal-gestao/app/resultados_dono.py` se necessário
- Create: `portal-gestao/tests/test_client_revy_trafego.py`
- Modify: `portal-gestao/tests/test_resultados_dono.py` / dashboard tests

**Interfaces:**

```python
# clients/revy_trafego.py
def fetch_resultados(
    *,
    loja_slug: str,
    periodo: str = "7d",
    modo: str = "last",
    timeout: float | None = None,
) -> dict | None:
    """GET /v1/lojas/{slug}/resultados. None se offline/erro."""
```

- Flag `PORTAL_REVY_TRAFEGO_RESULTADOS=1` liga o caminho novo; `0` mantém cálculo local (rollback).
- UI: se `None`, mostrar “Resultados de mídia temporariamente indisponíveis” (não zerar como se fosse ROAS 0).

- [ ] **Step 1: Teste client com respx/httpx mock**

- [ ] **Step 2: Integrar no dashboard; default flag off até smoke, depois on em lab**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(portal): consome resultados de midia via Revy Trafego API"
```

---

### Task 3: Pixel público no Revy Tráfego + cutover catálogo

**Files:**
- Ensure: `GET /public/v1/lojas/{slug}/pixel` no **revy-trafego** (já Fase 1).
- Modify: `catalogo-publico/app/config.py` — `PORTAL_PUBLIC_URL` documentar alias `REVY_TRAFEGO_PUBLIC_URL` ou prioridade:
  1. `REVY_TRAFEGO_PUBLIC_URL` se set
  2. senão `PORTAL_PUBLIC_URL`
- Modify: `catalogo-publico` provider de pixel se houver hardcode de path.
- Modify: `catalogo-publico/tests` se existirem testes de pixel URL.
- Docs: `catalogo-publico/README.md`, `docs/nao-plano/tutoriais/fluxo-utm-pixel-ctwa-meta.md`

**Interfaces:**
- JSON idêntico ao portal atual (campos `loja_slug`, `pixel_id`, `enabled`, `enviar_page_view`, `enviar_lead`).

- [ ] **Step 1: Teste catálogo resolve URL do tráfego quando env set**

- [ ] **Step 2: Implementar prioridade de env**

- [ ] **Step 3: Em lab, setar env e validar PageView ainda carrega pixel_id**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(catalogo): pixel por loja via Revy Trafego URL"
```

---

### Task 4: `POST` venda-confirmada + mover worker CAPI

**Files:**
- Modify: `revy-trafego/app/api_v1.py` — `POST /v1/lojas/{slug}/eventos/venda-confirmada`
- Modify: `portal-gestao` confirmação de venda — após commit local, chamar client (fire-and-forget com log de erro; ou sincronizar se outbox local desligado)
- Modify: workers — `REVY_TRAFEGO_CAPI_WORKER=1`, `PORTAL` desliga outbox processor
- Create tests em ambos os lados
- Modify: `docs/revy-trafego-interno.md` runbook cutover

**Interfaces:**

```http
POST /v1/lojas/{loja_slug}/eventos/venda-confirmada
X-Service-Token: ...
Content-Type: application/json

{
  "venda_id": "uuid",
  "lead_ref": "id-or-null",
  "valor": "10000.00",
  "moeda": "BRL",
  "campanha_id_first": null,
  "campanha_id_last": null,
  "event_id": "optional-idempotency",
  "cliente_telefone": "optional",
  "cliente_email": "optional",
  "fbclid": null,
  "ctwa_clid": null
}
```

Response: `{ "ok": true, "outbox_id": "..." }`
Idempotência: mesmo `venda_id` não cria outbox duplicado (unique/lookup).

**Cutover steps (ops):**

1. Deploy revy-trafego com worker CAPI on.
2. Portal: para de processar outbox; ainda pode **enfileirar** se shared DB e escrita local — preferir portal só notifica API e Revy grava outbox.
3. Smoke: confirmar venda → linha outbox + delivered.
4. Remover enfileiramento local do portal.

- [ ] **Step 1: Testes idempotência e 401**

- [ ] **Step 2: Implementar endpoint reutilizando `meta_capi` / messaging**

- [ ] **Step 3: Portal client + branch na confirmação de venda**

- [ ] **Step 4: Desligar worker portal (env) + doc runbook**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: cutover CAPI venda-confirmada para Revy Trafego"
```

---

### Task 5: Cutover spend job + limpeza portal

**Files:**
- Ligar spend job só no revy-trafego; `PORTAL_META_SPEND_SYNC_ENABLED=0`
- Remover do portal (ou isolar dead code):
  - rotas HTML `/app/trafego`, `/app/campanhas` se ainda legadas
  - imports só usados por UI técnica
- Manter models no portal **só se** ainda forem necessários para algo; se resultados 100% API, remover uso de `Campanha` no dashboard.
- CSV ROI no portal: ou remove, ou proxy; preferir só no revy-trafego.
- Atualizar `docs/nao-plano/tutoriais/trafego-pago-loja.md`, `docs/referencia-viva/contexto-compacto.md`, roadmap status Fase 2.

- [ ] **Step 1: Grep portal por `pode_gerir_trafego`, `/app/trafego`, `CampanhaGasto` em UI**

- [ ] **Step 2: Remover/neutralizar código morto com testes verdes**

- [ ] **Step 3: Suite completa portal + revy-trafego**

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(portal): remove midia write-path apos cutover Revy Trafego"
```

---

### Task 6: Hardening e verificação E2E

**Files:**
- Create: checklist em `docs/revy-trafego-interno.md` seção “Go-live Fase 2”
- Optional: test de contrato OpenAPI snapshot dos JSON

**Checklist E2E lab:**

1. Configurar Pixel/CAPI no Revy Tráfego loja X.
2. Catálogo loja X carrega `pixel_id` correto.
3. Campanha + UTM + lead chatbot.
4. Confirmar venda no portal → Purchase delivered.
5. ROI idêntico: UI Revy Tráfego vs cards portal (mesmos totais).
6. Sync spend manual atualiza gasto.
7. Derrubar Revy Tráfego: portal CRM funciona; cards mídia “indisponíveis”.

- [ ] **Step 1: Executar checklist e anotar gaps**

- [ ] **Step 2: Corrigir gaps críticos**

- [ ] **Step 3: Marcar Fase 2 DONE no roadmap**

```bash
git commit -m "docs: Revy Trafego Fase 2 cutover verificado"
```

---

## Rollback Fase 2

| Problema | Ação |
|---|---|
| API resultados instável | `PORTAL_REVY_TRAFEGO_RESULTADOS=0` (cálculo local se models ainda no DB) |
| Pixel catálogo | apontar de volta `PORTAL_PUBLIC_URL` para portal |
| CAPI | reabilitar worker portal; desligar worker revy-trafego; garantir um só |

## Definition of Done (Fase 2)

- [ ] Tasks 1–6
- [ ] Uma fonte de ROI observada no E2E
- [ ] Catálogo pixel via Revy Tráfego
- [ ] CAPI worker único no Revy Tráfego
- [ ] Portal sem UI/write path de mídia

**Depois (Fase 3 backlog):** split físico de DB; atribuição de lojas por gestor; audit PII completo.
