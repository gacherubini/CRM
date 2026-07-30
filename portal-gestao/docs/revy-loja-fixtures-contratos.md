# Revy Loja — fixtures sanitizadas de contratos

**Data:** 2026-07-29  
**Plano:** [`docs/plans/2026-07-29-plano-revy-loja.md`](../../docs/plans/2026-07-29-plano-revy-loja.md)  
**Propósito:** exemplos JSON versionados (schema_version 1 onde aplicável) para integração Control ↔ Portal, Chatbot e eventos comerciais. Valores fictícios; sem tokens, senhas ou PII real.

> **F0 — Backup drill:** confirmar backup e restauração do banco do Portal é **operação de lab/ops**, não código. Ver runbook de cutover e checklist lab; este documento não substitui o drill.

---

## 1. Control → Portal — snapshot de provisionamento

**Rota (Portal):** `POST /internal/v1/provisioning/state`  
**Auth:** `X-Service-Token`  
**Serialização Control:** `revy-trafego/app/control/provisioning_outbox.py` → `snapshot_to_payload`  
**Consumo Portal:** `portal-gestao/app/provisioning.py` → `apply_payload` (envelopes `operational` monotônicos)  
**Identidade (Loja lean):** `people` / `roles` também parseados por `app/loja/control_projection.py`

### Fixture completa (sanitizada)

```json
{
  "schema_version": 1,
  "loja_id": "loja-uuid-exemplo-001",
  "loja_slug": "loja-demo",
  "operational": [
    {
      "schema_version": 1,
      "event_id": "evt-loja-v3",
      "loja_id": "loja-uuid-exemplo-001",
      "aggregate": "loja",
      "version": 3,
      "state": "ativa",
      "effective_at": "2026-07-29T12:00:00+00:00",
      "occurred_at": "2026-07-29T12:00:00+00:00",
      "reason": null
    },
    {
      "schema_version": 1,
      "event_id": "evt-vendas-v1",
      "loja_id": "loja-uuid-exemplo-001",
      "aggregate": "vendas",
      "version": 1,
      "state": "ativo",
      "effective_at": "2026-07-29T12:00:00+00:00",
      "occurred_at": "2026-07-29T12:00:00+00:00",
      "reason": null
    },
    {
      "schema_version": 1,
      "event_id": "evt-estoque-v1",
      "loja_id": "loja-uuid-exemplo-001",
      "aggregate": "estoque",
      "version": 1,
      "state": "ativo",
      "effective_at": "2026-07-29T12:00:00+00:00",
      "occurred_at": "2026-07-29T12:00:00+00:00",
      "reason": null
    }
  ],
  "people": [
    {
      "person_id": "pessoa-uuid-dono-001",
      "email": "dono@loja-demo.example",
      "name": "Dono Demo"
    },
    {
      "person_id": "pessoa-uuid-vend-001",
      "email": "vendedor@loja-demo.example",
      "name": "Vendedor Demo"
    }
  ],
  "roles": [
    {
      "assignment_id": "cargo-uuid-dono-001",
      "person_id": "pessoa-uuid-dono-001",
      "role": "dono",
      "state": "ativo",
      "started_at": "2026-07-01T10:00:00+00:00",
      "ended_at": null
    },
    {
      "assignment_id": "cargo-uuid-vend-001",
      "person_id": "pessoa-uuid-vend-001",
      "role": "vendedor",
      "state": "ativo",
      "started_at": "2026-07-10T10:00:00+00:00",
      "ended_at": null
    }
  ]
}
```

### Regras monotônicas (resumo)

| Condição | Razão retornada |
|---|---|
| `version` local > payload | `stale` (não reativa) |
| mesma `version` + mesmo `state` | `idempotent` |
| restante | `applied` |

Estados típicos: loja `ativa` \| `suspensa`; módulos `ativo` \| `suspenso`.

### Variante lean (testes de identidade Portal)

O adapter em memória também aceita `people[].roles` / `pessoa_id` (compat):

```json
{
  "schema_version": 1,
  "loja_slug": "loja-c",
  "operational": [
    { "aggregate": "loja", "version": 2, "state": "ativa", "event_id": "e1" },
    { "aggregate": "vendas", "version": 1, "state": "ativo", "event_id": "e2" },
    { "aggregate": "estoque", "version": 1, "state": "ativo", "event_id": "e3" }
  ],
  "people": [
    {
      "pessoa_id": "p1",
      "loja_slug": "loja-c",
      "roles": ["dono"],
      "ativo": true
    }
  ]
}
```

---

## 2. Chatbot — lead / conversa / mensagem (com canal multi-WA)

**Auth:** Bearer da loja (`Authorization`)  
**Fontes:** `chatbot-api/app/servico.py` → `para_saida_lead`, `para_saida_conversa`, `para_saida_mensagem`

### 2.1 Lead — `GET /v1/leads` → `{ "leads": [ ... ] }`

Lead é por `(loja_id, telefone)`. Não carrega `canal_id` de WhatsApp (canal de mídia/origem de atribuição é outro campo).

```json
{
  "id": "lead-uuid-exemplo-001",
  "telefone": "5511987654321",
  "nome": "Maria Demo",
  "interesse": "Civic 2020",
  "etapa": "em_atendimento",
  "consentimento_em": "2026-07-28T15:00:00+00:00",
  "criada_em": "2026-07-28T14:55:00+00:00",
  "origem": "meta",
  "canal": "whatsapp",
  "utm_source": "facebook",
  "utm_medium": "paid",
  "utm_campaign": "promo-julho",
  "utm_content": null,
  "utm_term": null,
  "origem_first": "meta",
  "canal_first": "whatsapp",
  "utm_source_first": "facebook",
  "utm_medium_first": "paid",
  "utm_campaign_first": "promo-julho",
  "utm_content_first": null,
  "utm_term_first": null,
  "origem_last": "meta",
  "canal_last": "whatsapp",
  "utm_source_last": "facebook",
  "utm_medium_last": "paid",
  "utm_campaign_last": "promo-julho",
  "utm_content_last": null,
  "utm_term_last": null,
  "fbclid": null,
  "gclid": null,
  "gbraid": null,
  "wbraid": null,
  "ctwa_clid": null,
  "ctwa_clid_first": null,
  "meta_ad_id": null,
  "meta_ad_id_first": null,
  "meta_campaign_id": null,
  "meta_campaign_id_first": null,
  "meta_adset_id": null,
  "ctwa_source_type": null,
  "ctwa_codigo": null,
  "ctwa_codigo_first": null,
  "ctwa_atribuido_em": null,
  "veiculo_ref": "veic-uuid-exemplo",
  "catalog_interest_ref": null,
  "atribuida_em": null,
  "atualizada_em": "2026-07-28T16:10:00+00:00"
}
```

### 2.2 Conversa — `GET /v1/conversas` (query opcional `canal_id`)

Conversa multi-WA: chave `(canal_id, telefone)`. Campos de canal nulos em legado sem canal.

```json
{
  "id": "conv-uuid-exemplo-001",
  "telefone": "5511987654321",
  "bot_ativo": false,
  "status": "handoff",
  "atualizada_em": "2026-07-28T16:10:00+00:00",
  "ultima_mensagem": {
    "texto": "Tem Civic disponível?",
    "criada_em": "2026-07-28T16:09:00+00:00",
    "direcao": "entrada"
  },
  "canal_id": "canal-uuid-wa-1",
  "evolution_instance": "loja-demo-wa-1",
  "canal_label": "***4321",
  "numero_mascarado": "***4321",
  "canal_ativo": true,
  "canal_estado": "conectado"
}
```

Segundo canal (mesmo telefone, outra conversa):

```json
{
  "id": "conv-uuid-exemplo-002",
  "telefone": "5511987654321",
  "bot_ativo": true,
  "status": "aberta",
  "atualizada_em": "2026-07-28T17:00:00+00:00",
  "ultima_mensagem": {
    "texto": "Oi no segundo número",
    "criada_em": "2026-07-28T17:00:00+00:00",
    "direcao": "entrada"
  },
  "canal_id": "canal-uuid-wa-2",
  "evolution_instance": "loja-demo-wa-2",
  "canal_label": "linha-2",
  "numero_mascarado": null,
  "canal_ativo": true,
  "canal_estado": "conectado"
}
```

### 2.3 Mensagens — `GET /v1/conversas/{telefone}/mensagens` (legado por telefone)

```json
{
  "telefone": "5511987654321",
  "mensagens": [
    {
      "direcao": "entrada",
      "texto": "Tem Civic disponível?",
      "criada_em": "2026-07-28T16:09:00+00:00"
    },
    {
      "direcao": "saida",
      "texto": "Temos sim!",
      "criada_em": "2026-07-28T16:10:00+00:00"
    }
  ]
}
```

### 2.4 Resposta de envio humano (composer Portal → Chatbot)

Após `POST` de mensagem humana (idempotente por `idempotency_key`):

```json
{
  "duplicada": false,
  "mensagem_id": "msg-uuid-exemplo-001",
  "telefone": "5511987654321",
  "texto": "Oi Maria, sou o vendedor.",
  "bot_ativo": false,
  "status": "handoff",
  "enviado": true,
  "canal_id": "canal-uuid-wa-1",
  "ator": "vendedor@loja-demo.example",
  "evolution_instance": "loja-demo-wa-1"
}
```

Canal inativo: UI da Loja bloqueia envio (`envio_bloqueado_canal`); Chatbot rejeita connect em canal inativo com 409.

---

## 3. Portal → Control — evento de venda confirmada

**Outbox Portal:** `portal-gestao/app/revy_trafego_outbox.py` → `enfileirar_venda_confirmada`  
**Entrega:** `POST /v1/lojas/{loja_slug}/eventos/venda-confirmada` (`X-Service-Token`)  
**Body model Control:** `VendaConfirmadaBody` em `revy-trafego/app/api_v1.py`  
**Payload cifrado no outbox** (Fernet); exemplo abaixo é o JSON em claro após decifrar.

```json
{
  "venda_id": "venda-uuid-exemplo-001",
  "lead_ref": "lead-uuid-exemplo-001",
  "valor": "85000.00",
  "moeda": "BRL",
  "status": "confirmada",
  "criada_em": "2026-07-28T18:00:00+00:00",
  "confirmada_em": "2026-07-28T18:05:00+00:00",
  "atualizada_em": "2026-07-28T18:05:00+00:00",
  "custo_veiculo": "72000.00",
  "custos_diretos_total": "500.00",
  "campanha_id_first": "camp-uuid-first",
  "campanha_id_last": "camp-uuid-last",
  "utm_campaign_first": "promo-julho",
  "utm_campaign_last": "promo-julho",
  "event_id": "purchase-venda-uuid-exemplo-001",
  "cliente_telefone": "5511987654321",
  "cliente_email": "cliente@example.com",
  "fbclid": null,
  "fbc": null,
  "gclid": "Cj0KCQjw_example_gclid",
  "gbraid": null,
  "wbraid": null,
  "ctwa_clid": null
}
```

`event_id` de outbox (dedupe local Portal):

```text
revy:{loja_slug}:venda:{venda_id}:confirmada
```

Resposta típica Control (idempotente):

```json
{
  "ok": true,
  "outbox_id": "capi-outbox-uuid",
  "idempotent": false
}
```

Snapshot sem click IDs (`venda_atualizada`) omite campos de cliente/click e usa `event_type=venda_atualizada`.

---

## 4. Aquisição — resumo read-only (Control → Loja)

Dois contratos relacionados:

### 4.1 Revy Tráfego resultados (Meta/ROI local) — usado pelo SalesOverview hoje

**Rota:** `GET /v1/lojas/{loja_slug}/resultados?periodo=7d|mes&modo=last|first`  
**Auth:** `X-Service-Token`  
**Cliente Portal:** `RevyTrafegoClient.fetch_resultados`

```json
{
  "loja_slug": "loja-demo",
  "periodo": {
    "chave": "7d",
    "inicio": "2026-07-22",
    "fim": "2026-07-28",
    "modo": "last",
    "chatbot_offline": false
  },
  "totais": {
    "gasto": "1250.00",
    "leads": 40,
    "vendas": 3,
    "faturamento": "255000.00",
    "cpl": "31.25",
    "cpa": "416.67",
    "roas": "204.00"
  },
  "canais": [
    {
      "canal": "meta",
      "gasto": "1250.00",
      "vendas": 3,
      "faturamento": "255000.00",
      "roas": "204.00",
      "roas_barra_pct": 100.0
    }
  ],
  "melhor_campanha": {
    "id": "camp-uuid-last",
    "nome": "Promo Julho",
    "canal": "meta",
    "gasto": "800.00",
    "leads": 25,
    "vendas": 2,
    "roas": "212.50"
  },
  "campanhas": [],
  "tem_campanhas": true,
  "vendas_sem_campanha": 0,
  "leads_sem_campanha": 5
}
```

### 4.2 Acquisition resumo Google (serviço Control)

**Rota:** `GET /control/v1/internal/lojas/{loja_id}/aquisicao-resumo?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`  
**Auth:** service token; flag Google habilitada  
**Serialização:** `_aquisicao_resumo_json` em `revy-trafego/app/web/control.py`

```json
{
  "loja_id": "loja-uuid-exemplo-001",
  "date_from": "2026-07-01",
  "date_to": "2026-07-28",
  "google_disponivel": true,
  "google": {
    "loja_id": "loja-uuid-exemplo-001",
    "customer_id": "1234567890",
    "date_from": "2026-07-01",
    "date_to": "2026-07-28",
    "impressions": 12000,
    "clicks": 340,
    "cost_micros": 450000000,
    "cost": "450.00",
    "conversions": "8.0",
    "conversions_value": "120000.00",
    "currency_code": "BRL",
    "ctr": "0.0283",
    "cpc": "1.32",
    "cpl": null,
    "roas": "266.67",
    "cost_per_conversion": "56.25"
  },
  "meta": null
}
```

Quando Google não está ligado na loja:

```json
{
  "loja_id": "loja-uuid-exemplo-001",
  "date_from": "2026-07-01",
  "date_to": "2026-07-28",
  "google_disponivel": false,
  "google": null,
  "meta": null
}
```

### 4.3 Shape normalizado no SalesOverview (Portal)

Após normalização local (`AquisicaoResumo.to_dict`):

```json
{
  "status": "ok",
  "investimento": "1250.00",
  "investimento_disponivel": true,
  "cac": "416.67",
  "cac_disponivel": true,
  "roas": "204.00",
  "roas_disponivel": true,
  "leads": 40,
  "vendas_atribuidas": 3,
  "faturamento_atribuido": "255000.00",
  "google_status": "indisponivel",
  "fonte": "api",
  "mensagem": null
}
```

Regra de UI: Google ausente = `indisponivel`, **nunca** gasto zero inventado.

---

## 5. Isolamento de credenciais bancárias (Control)

**Confirmado (2026-07-29):** grep em `revy-trafego` — **não há** endpoints, modelos ou payloads de credenciais de portais bancários (Motor/financeiras) no Control.

- Credenciais de bancos ficam no domínio **Portal/Motor** (`/app/financeiras`, Motor API de provedores).
- Control expõe: lojas, cargos, módulos, Meta/Google Ads, WhatsApp canais (Evolution), auditoria, aquisição read-only.
- Tokens de **serviço** entre apps (Chatbot/Estoque/Motor/Portal) existem no Control como config de integração — **não** são senhas de portais bancários.

Ver checkbox F5 no plano Loja.

---

## 6. Referências de código

| Contrato | Produção | Testes de forma |
|---|---|---|
| Provisioning snapshot | `revy-trafego/.../provisioning_outbox.py`, `portal-gestao/app/provisioning.py` | `portal-gestao/tests/test_provisioning.py`, `revy-trafego/tests/test_control_provisioning_outbox.py` |
| Lead/conversa/msg | `chatbot-api/app/servico.py` | `chatbot-api/tests/test_conversas.py`, `test_channels.py`, `test_leads.py` |
| Venda confirmada | `portal-gestao/app/revy_trafego_outbox.py`, `revy-trafego/app/api_v1.py` | `portal-gestao/tests/test_revy_trafego_outbox.py` |
| Aquisição resumo | `revy-trafego/app/web/control.py`, `api_v1.py` resultados | `portal-gestao/tests/test_loja_sales_overview.py` |
