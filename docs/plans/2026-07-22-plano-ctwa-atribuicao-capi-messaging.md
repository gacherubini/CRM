# Plano — CTWA (Click-to-WhatsApp): atribuição, persona→CTWA e CAPI messaging

> **REVISÃO 2026-08-04:** o *match de campanha* descrito aqui estava **quebrado na
> prática** (diagnóstico do dia 1: 0 leads criados no dia; `meta_campaign_id` nunca
> preenchido — a referral CTWA do WhatsApp entrega só `ad_id`, não o id da campanha).
> Corrigido/estendido pelo plano
> [CTWA por ad_id + Graph](../superpowers/plans/2026-08-04-atribuicao-ctwa-campanha.md)
> — **Fase 1 deployada** + **Fase 2 código** (cache Graph + worker gated): lead na 2ª
> mensagem, match por `ad_id` e resolução `ad_id→campaign_id` via Graph (`ads_read`).
> O **CAPI messaging Purchase** descrito neste plano continua válido.

> **FRONTEIRA FUTURA:** o fluxo CTWA implementado continua válido, mas configuração,
> Registros de Campanha e CAPI técnica migram ao [Revy Control](2026-07-29-plano-revy-control.md).
> Multi-WhatsApp por vendedor e o “Google residual” citados abaixo foram substituídos
> respectivamente pelas Fases 5 e 4 do Control.

> **Status 2026-07-22: MVP CÓDIGO** — ingestão CTWA no lead, match campanha, CAPI messaging Purchase, n8n passthrough, UI.  
> Residual: fixture real Evolution (Task 0 lab), Lead early CAPI (B2), E2E anúncio pago.  
> Origem: conversa de produto (Pixel monta persona → CTWA converte → ROI no Revy).  
> **Não** reimplementar campanhas/ROI/E10 Pixel site/`publish_conversion` Meta web já em `main`.

**Status:** **MVP implementado** — eixo **C · CRM dono** + entrada de tráfego  
**Detalha / estende:** E10 residual messaging; campanhas/ROI (6.1); event bus (6.2 F); guia `trafego-pago-loja.md`  
**Não implementa:** Ad Manager (criar/pausar anúncios); TikTok Events; multi-número por vendedor (6.3); Google (G residual de 6.2)  
**Spend automático Meta:** **fora deste arquivo** — ver plano irmão [6.2c Meta spend API](2026-07-22-plano-meta-spend-api.md) (dono não digita gasto). Compartilha `meta_campaign_id`.  
**Depende de:** lead first/last + fbclid; campanhas + `utm_campaign`; CAPI Purchase web + bus; Evolution + n8n em lab

**Goal:** O dono pode (1) rodar anúncio **CTWA** e ver o lead no Revy com origem de anúncio, (2) casar campanha/gasto/ROI nesse caminho, (3) devolver **Lead/Purchase** à Meta via CAPI de messaging com `ctwa_clid`, (4) usar o fluxo operacional **Pixel → públicos → CTWA** sem o Revy “criar anúncio”.

**Architecture:** Chatbot continua dono de lead/click ids; n8n só repassa campos de referral já normalizados (sem lógica de negócio). Portal continua dono de campanha, gasto, ROI e outbox CAPI. `confirm_sale` → `publish_conversion` → adapters: Meta **web** (já existe) e Meta **messaging** (novo), escolhidos por presença de `ctwa_clid` / config. Match de campanha CTWA: `utm_campaign` em mensagem pré-preenchida **ou** `meta_campaign_id` / código público cadastrado na campanha **ou** atribuição manual no lead (MVP).

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, pytest, httpx; n8n workflow; Evolution webhook; Meta Graph Conversions API (web + Business Messaging); Jinja2 Portal.

---

## Problema que este plano resolve

Hoje o Revy mede bem:

```text
Anúncio → Catálogo + Pixel + UTM → WhatsApp → Lead → Venda → ROI + CAPI web
```

O mercado (e o dono de loja de moto) quer também:

```text
Anúncio CTWA → WhatsApp direto → Lead → Venda → ROI + CAPI messaging
```

Sem este plano:

- CTWA **atende**, mas lead fica **sem campanha**
- ROI “não fecha” com o Ads
- Persona do Pixel **não se conecta no CRM** ao CTWA (só na Meta Ads, manual)
- Não há `ctwa_clid` para treinar a Meta no funil de mensagem

---

## Fora de escopo (explícito)

| Item | Motivo |
|---|---|
| Criar/pausar anúncios na Meta | Continua no Ads Manager |
| Pixel “dentro” do WhatsApp | Impossível; CTWA não é browser |
| API de spend (puxar gasto) | Parked (6.2) |
| Multi-WhatsApp por vendedor | Plano 6.3 separado |
| Trocar Evolution por Cloud API oficial no MVP | Task 0 decide se referral chega; se **não** chegar, ver mitigação §Riscos |
| Lookalike automático via API Marketing | Dono cria público na Meta; Revy não vira Ad Manager |
| Garantir Event Match Quality máximo | MVP honesto: `ctwa_clid` + telefone hash + valor |

---

## Decisões de produto

| Tema | Decisão |
|---|---|
| Persona | Continua vinda do **Pixel no catálogo** (+ Purchase web). CTWA **consome** públicos na Meta; Revy documenta o playbook. |
| CTWA no CRM | Captura `ctwa_clid` + metadados de ad (quando existirem) no **lead** (first/last como UTM). |
| Match campanha | Ordem: (1) código/`utm_campaign` na mensagem pré-preenchida; (2) `meta_ad_id` / `meta_campaign_id` mapeado na campanha Revy; (3) canal `meta` + campanha única ativa (não inventar); (4) manual no Portal; (5) “sem campanha”. |
| CAPI messaging | Na **venda confirmada** (Purchase). Lead event opcional na 1ª correlação CTWA (fase B2) se config `enviar_lead_ctwa`. |
| Falha outbound | Nunca quebra venda / webhook inbound. |
| RBAC | Igual tráfego: dono/gerente veem e retentam; vendedor vê origem no lead. |
| Honestidade | Se Evolution não entregar referral, UI e docs dizem “CTWA sem click id — medição parcial”. |
| Relação com catálogo | Catálogo **permanece** caminho medido e de persona; CTWA é **segundo cano**, não substituto. |

### Narrativa comercial (não é código, mas trava o escopo)

> Pixel monta persona na vitrine.  
> CTWA converte no zap (volume).  
> Com persona boa, o dono **aumenta budget CTWA** mirando públicos do Pixel **na Meta**.  
> O Revy **amarra** CTWA → lead → venda → ROI e **devolve** conversão à Meta.

Não vender “fase de aprendizado”. Vender: **mesmo WhatsApp, com placar**.

---

## Contexto do que já existe (não reimplementar)

| Peça | Onde | Estado |
|---|---|---|
| Pixel browser + event_id Lead | `catalogo-publico` | Feito |
| UTM first/last, fbclid, gclid | `chatbot-api` Lead | Feito |
| Atribuição catálogo / public_ref | Chatbot + outbox | Feito |
| Campanhas + gasto + ROI last/first | Portal | Feito |
| CAPI Purchase web + outbox + retry | `meta_capi.py` | Feito |
| `publish_conversion` + `MetaAdapter` | `portal-gestao/app/conversions/` | Feito |
| `PurchaseConversion` (fbclid/gclid/phone) | `conversions/types.py` | Feito — **estender** com `ctwa_clid` |
| Webhook mensagem + n8n | Evolution → n8n → Chatbot | Feito — **estender** payload |
| Guia loja tráfego | `docs/trafego-pago-loja.md` | Feito — **estender** seção CTWA |
| Multi-WA Task 0 (payload CTWA) | plano 6.3 | **Alinha** com Task 0 deste plano |

---

## Fluxo alvo (end-to-end)

```text
[Meta Ads CTWA]
      │ clique
      ▼
WhatsApp (mensagem inbound)
      │ webhook Evolution
      ▼
n8n: extrai referral/ctwa_clid (se houver) + texto
      │ POST Chatbot (mensagem ou endpoint dedicado)
      ▼
Chatbot: lead.ctwa_clid (+ meta_ad_id, source…)
         origem/canal last = meta_ctwa / whatsapp
         tenta match campanha (código na msg / mapa id)
      │
      ├─ (opcional) enfileira Lead CAPI messaging
      ▼
Atendimento → simulação → venda no Portal
      │ confirm_sale
      ▼
publish_conversion(PURCHASE)
      ├─ MetaAdapter web (se fbclid / fluxo site / sempre best-effort atual)
      └─ MetaMessagingAdapter (se ctwa_clid e config ok)
      ▼
ROI: lead/venda com campanha_id snapshot (igual hoje)
```

Playbook paralelo (sem código de Ad Manager):

```text
Campanhas catálogo + Pixel → públicos Meta
      → nova campanha CTWA segmentada nesses públicos
```

---

## Modelo de dados

### Chatbot — `leads` (colunas novas)

```text
ctwa_clid              str(255) null   # last visto; first se null em ctwa_clid_first
ctwa_clid_first        str(255) null
meta_ad_id             str(64) null    # last
meta_ad_id_first       str(64) null
meta_campaign_id       str(64) null    # id campanha Meta, se vier no referral
meta_campaign_id_first str(64) null
meta_adset_id          str(64) null    # opcional
ctwa_source_type       str(40) null    # ex.: ad / post (sanitizado)
ctwa_atribuido_em      datetime null
```

Regras de touch: **igual UTM** — first só se vazio; last sempre atualiza com valor novo não vazio.

Serialização lead API: expor campos novos no JSON (Portal consome).

### Chatbot — opcional `ctwa_eventos` (só se Task 0 mostrar payload rico e reprocessamento)

MVP **pode** só enriquecer lead na 1ª mensagem. Tabela de eventos só se precisar idempotência de Lead CAPI no Chatbot (preferir outbox no **Portal** para outbound).

### Portal — `campanhas` (colunas novas, nullable)

```text
meta_campaign_id   str(64) null   # id numérico/string da campanha no Ads (match)
meta_ad_id         str(64) null   # opcional match mais fino
codigo_ctwa        str(40) null   # código curto na mensagem pré-preenchida (ex.: RV-JUL)
```

`utm_campaign` **continua** a chave principal de ROI.  
`codigo_ctwa` / `meta_campaign_id` são **chaves extras** para CTWA sem UTM de site.

### Portal — `PurchaseConversion` + outbox

- Campo `ctwa_clid: str | None` no dataclass.
- Outbox: reutilizar `meta_capi_outbox` com `event_name` / `action_source` **ou** coluna `modo` (`web` | `messaging`) se o payload divergir demais — decidir na Task B1 com teste.

Decisão preferida MVP:

- Mesma tabela outbox; payload JSON guarda o body Graph; `event_id` único `purchase-{venda_id}` (web) e `purchase-msg-{venda_id}` (messaging) **ou** mesmo event_id se a Meta documentar dedupe cross-product — **validar na Task B1**; se incerto, **event_ids distintos** e docs honestos.

### Lead CAPI messaging (opcional fase B2)

- `event_id = lead-ctwa-{lead_id}` ou `{ctwa_clid}` hash  
- Só se `ctwa_clid` presente e toggle loja ativo  
- Disparo: Portal job puxando leads novos **ou** Chatbot chama Portal interno — **preferir** Portal consumir lead no confirm e, para Lead early, endpoint interno Portal `POST /internal/...` **ou** enfileirar no Chatbot sem segredo CAPI no Chatbot.

**Decisão de segurança:** token CAPI **só no Portal** (como hoje). Chatbot **nunca** guarda token Meta. Lead early = Chatbot marca `ctwa_lead_pendente=true`; Portal worker/best-effort na próxima sync de funil **ou** botão “Enviar leads CTWA” na Tráfego. MVP pode **adiar Lead early** e só mandar **Purchase** (mais simples, ainda treina venda).

**MVP mínimo recomendado:** só **Purchase messaging** na confirmação de venda. Lead early = fase B2.

---

## Mapa de arquivos

| Arquivo | Papel |
|---|---|
| `chatbot-api/alembic/versions/00xx_lead_ctwa.py` | Colunas CTWA no lead |
| `chatbot-api/app/models_db.py` | Campos Lead |
| `chatbot-api/app/servico.py` | Aplicar touch CTWA; parse referral normalizado |
| `chatbot-api/app/main.py` | Schema webhook/mensagem + serialização lead |
| `chatbot-api/tests/test_ctwa_attribution.py` | First/last ctwa_clid; sem referral |
| `n8n/workflow-ai-nao-salvos.json` (+ prepare) | Extrair referral do body Evolution |
| `docs/plans/fixtures/ctwa-evolution-sample.json` | Fixture sanitizada Task 0 |
| `portal-gestao/alembic/versions/00xx_campanha_ctwa_keys.py` | meta_campaign_id, codigo_ctwa |
| `portal-gestao/app/models.py` | Campanha + se outbox modo |
| `portal-gestao/app/campanhas.py` | Match por codigo_ctwa / meta ids |
| `portal-gestao/app/conversions/types.py` | `ctwa_clid` em PurchaseConversion |
| `portal-gestao/app/conversions/meta_messaging.py` | Novo adapter |
| `portal-gestao/app/conversions/bus.py` | Registrar adapter messaging |
| `portal-gestao/app/meta_capi.py` ou `meta_capi_messaging.py` | Montar payload messaging |
| `portal-gestao/app/main.py` | UI campanha + tráfego status |
| `portal-gestao/app/templates/campanhas/form.html` | Campos Meta/código CTWA |
| `portal-gestao/app/templates/leads/detalhe.html` | Mostrar ctwa_clid / origem |
| `portal-gestao/app/templates/trafego/form.html` | Status messaging + toggle Lead early se B2 |
| `portal-gestao/tests/test_ctwa_match.py` | Match campanha |
| `portal-gestao/tests/test_meta_messaging_capi.py` | Payload + outbox |
| `portal-gestao/tests/test_conversion_bus.py` | Ambos adapters |
| `docs/trafego-pago-loja.md` | Seção CTWA + playbook Pixel→públicos→CTWA |
| `docs/tutorial-dono.md` | Parágrafo operacional |
| `docs/contexto-compacto.md` + `plans/README.md` | Índice / eixo |

---

## Fases e LOE

| Fase | Nome | LOE | Entrega |
|---|---|---|---|
| **0** | Descoberta Evolution/CTWA | S | Fixture real sanitizada + go/no-go |
| **A** | Ingestão + lead CTWA | M | `ctwa_clid` no lead via n8n/Chatbot |
| **B** | CAPI messaging Purchase | M | Venda → Meta messaging |
| **B2** | Lead early CAPI (opcional) | S | Toggle + outbox Lead |
| **C** | Match campanha + ROI | M | codigo_ctwa / meta ids + snapshot venda |
| **D** | UX Portal + alertas | S | Lead detalhe, form campanha, Tráfego |
| **E** | Docs + playbook dono | S | Guia sem jargão “aprendizado” |
| **F** | Lab E2E | S | Anúncio teste → lead → venda → Events Manager |

**Ordem:** `0 → A → C → B → D → E → F` (C antes de B para snapshot de campanha na venda já útil; B2 depois de B se sobrar).

```text
0  Fixture / viabilidade
A  Lead guarda ctwa_clid
C  Campanha casa com CTWA
B  Purchase messaging
D  UI
E  Docs playbook Pixel→CTWA
F  E2E lab
```

---

## Fase 0 — Descoberta (obrigatória antes de A)

### Objetivo

Provar **com payload real** se a Evolution (lab `evolution2037`) entrega `referral` / `ctwa_clid` em mensagem vinda de anúncio CTWA.

### Aceite

- [ ] Anúncio CTWA de teste (conta Meta da loja lab) → 1 mensagem no número conectado  
- [ ] Webhook bruto capturado (PII removido) em `docs/plans/fixtures/ctwa-evolution-sample.json`  
- [ ] Doc curto no topo do plano ou `docs/plans/fixtures/README-ctwa.md`: caminhos JSON onde está o click id  
- [ ] Decisão escrita:

| Resultado | Ação |
|---|---|
| `ctwa_clid` presente | Seguir fases A–F |
| Só ids parciais de ad | A com campos disponíveis; match por `meta_ad_id` / código msg |
| **Nada** de referral | MVP: **código pré-preenchido** na mensagem CTWA (`codigo_ctwa`) + docs; CAPI messaging **só se** depois migrar Cloud API — não fingir `ctwa_clid` |

### Tasks

- [ ] **0.1** Rodar 1 CTWA de teste no lab; capturar body n8n/Evolution (sem commitar telefone/nome reais).  
- [ ] **0.2** Normalizar schema de entrada Chatbot (campos opcionais flat):

```text
ctwa_clid, meta_ad_id, meta_campaign_id, meta_adset_id, ctwa_source_type
```

- [ ] **0.3** Atualizar este plano com “Resultado Task 0: …” no topo (1 parágrafo).  
- [ ] Commit: `docs(plans): fixture CTWA Evolution + decisão Task 0`

**Nota:** Alinhar com Task 0 do plano multi-WhatsApp (6.3) para **não** duplicar captura; uma fixture serve aos dois.

---

## Fase A — Ingestão e lead

### Aceite

- Mensagem inbound com campos CTWA preenche `ctwa_clid` (first/last).  
- Sem campos: lead orgânico/normal, zero erro.  
- Idempotência: mesma mensagem não corrompe first.  
- API lead JSON expõe campos para o Portal.  
- Testes unitários com fixture da Fase 0.

### Design de ingestão

Preferência: estender o fluxo **já usado** de registro de mensagem / criação de lead no webhook que o n8n chama — não criar segundo pipeline paralelo se já houver um único `registrar_mensagem`.

Contrato n8n → Chatbot (exemplo de campos extras no body JSON já existente):

```json
{
  "telefone": "5511999999999",
  "texto": "Olá! Vim do anúncio",
  "ctwa_clid": "ARAxxxx",
  "meta_ad_id": "12033...",
  "meta_campaign_id": "12033...",
  "ctwa_source_type": "ad"
}
```

n8n: função JS defensiva — se path não existir, envia `null`s; **nunca** quebra o fluxo de texto.

### Tasks

- [ ] **A1** Migration lead CTWA + model.  
- [ ] **A2** `_aplicar_touch_ctwa(lead, dados)` espelhando `_aplicar_touch_do_atributo`.  
- [ ] **A3** Wire no registro de mensagem / lead.  
- [ ] **A4** Serialização lead.  
- [ ] **A5** Testes `test_ctwa_attribution.py`.  
- [ ] **A6** n8n: mapear referral → body (lab + prepare-workflow).  
- [ ] Commit: `feat(chatbot): capturar ctwa_clid e meta ad ids no lead`

---

## Fase C — Match de campanha e ROI

### Aceite

- Campanha com `codigo_ctwa=RV-JUL` casa lead cuja mensagem/texto ou campo dedicado contém o código (normalizar casefold/strip).  
- Campanha com `meta_campaign_id` casa lead com mesmo id.  
- `aplicar_snapshot_venda` usa as novas chaves além de utm.  
- ROI last/first continua; leads CTWA com match entram na linha da campanha.  
- Lead CTWA sem match → “sem campanha” (honesto).

### Tasks

- [ ] **C1** Migration Portal campanha (`codigo_ctwa`, `meta_campaign_id`, `meta_ad_id` opcional).  
- [ ] **C2** `resolver_campanha_para_lead(lead, campanhas, modo)` estendido.  
- [ ] **C3** Form criar/editar campanha (labels BR: “Código na mensagem do anúncio”, “ID da campanha no Meta”).  
- [ ] **C4** Testes match + snapshot venda.  
- [ ] **C5** Cliente Portal `obter_lead` já lê JSON novo (sem mudança se dict genérico).  
- [ ] Commit: `feat(portal): match de campanha CTWA por código e meta ids`

### Fallback operacional (se Task 0 sem referral)

Mensagem pré-preenchida no CTWA:

```text
Olá! Quero saber mais. Cód: RV-JUL
```

Dono cadastra `codigo_ctwa=RV-JUL` na campanha Revy.  
Match por substring/token no texto da 1ª mensagem (cuidado para não false-positive — preferir token `Cód: XXX` ou `ref:XXX`).

---

## Fase B — CAPI messaging (Purchase)

### Aceite

- Venda confirmada com lead que tem `ctwa_clid` enfileira evento messaging.  
- Payload inclui `user_data.ctwa_clid` (e ph hash se telefone).  
- `action_source` / `messaging_channel` conforme doc Meta Business Messaging vigente na implementação (fixar na Task B1 com link da doc).  
- Falha não reverte venda.  
- Retry na Tráfego reprocessa outbox messaging.  
- Lead **sem** `ctwa_clid`: adapter messaging no-op (web adapter segue se aplicável).

### Tasks

- [ ] **B1** Ler doc Meta CAPI Business Messaging; fixar shape do JSON + URL Graph no código com comentário da versão.  
- [ ] **B2** `PurchaseConversion.ctwa_clid` + `from_sale`.  
- [ ] **B3** `meta_capi_messaging.py` (ou extensão clara em `meta_capi.py` sem misturar payloads).  
- [ ] **B4** `MetaMessagingAdapter` + `default_adapters()`.  
- [ ] **B5** Testes mock httpx; bus chama web + messaging.  
- [ ] **B6** UI último envio messaging (ou unificado se outbox compartilhada).  
- [ ] Commit: `feat(portal): CAPI messaging Purchase com ctwa_clid`

### Pseudocontrato payload (ajustar na B1 se a doc divergir)

```python
{
  "data": [{
    "event_name": "Purchase",
    "event_time": 1710000000,
    "event_id": "purchase-msg-{venda_id}",
    "action_source": "business_messaging",
    "messaging_channel": "whatsapp",
    "user_data": {
      "ctwa_clid": "...",
      "ph": ["sha256..."]
    },
    "custom_data": {"value": 15000.0, "currency": "BRL"}
  }]
}
```

---

## Fase B2 — Lead early (opcional)

Só se B estiver estável e dono pedir otimização de “lead” no Ads.

- Toggle `enviar_lead_ctwa` na config Meta da loja.  
- Quando lead ganha `ctwa_clid` e ainda não enviou: Portal outbox `Lead` messaging.  
- Idempotency: um Lead por `lead_id`+`ctwa_clid`.  
- Chatbot **não** envia à Meta.

---

## Fase D — UX Portal

### Aceite

- Detalhe do lead: bloco “WhatsApp Ads” com ctwa_clid mascarado (últimos 6), meta_ad_id, origem.  
- Form campanha: campos CTWA.  
- ROI / resultados: canal Meta inclui vendas CTWA matched (sem gráfico novo obrigatório).  
- Alerta opcional: “N vendas CTWA sem campanha no período” em `resultados_dono` se barato.

### Tasks

- [ ] **D1** Template lead.  
- [ ] **D2** Form/lista campanha.  
- [ ] **D3** Alerta sem match (se couber em `alertas_trafego`).  
- [ ] **D4** Testes de render/RBAC smoke.  
- [ ] Commit: `feat(portal): UI origem CTWA e chaves de campanha`

---

## Fase E — Docs e playbook

### Aceite

- `docs/trafego-pago-loja.md` com seções:

  1. CTWA medido no Revy (código na msg + ctwa_clid)  
  2. Playbook **Pixel → públicos → CTWA** (sem prometer aprendizado; linguagem de dinheiro)  
  3. Checklist “números não batem” atualizado  

- Tutorial dono: 1 página operacional.  
- `contexto-compacto.md` + `plans/README.md` apontam este plano.

### Copy proibida / permitida

| Evitar | Preferir |
|---|---|
| “Fase de aprendizado do Pixel” | “Campanha de vitrine que já manda pro zap e mostra qual anúncio vendeu” |
| “Pixel no WhatsApp” | “Público de quem visitou o site, usado no anúncio de WhatsApp” |

---

## Fase F — E2E lab

### Aceite

- [ ] CTWA teste → lead no Portal com ctwa_clid **ou** codigo_ctwa  
- [ ] Campanha matched  
- [ ] Venda confirmada  
- [ ] Outbox messaging `sent` **ou** skipped documentado se Task 0 sem clid  
- [ ] ROI mostra 1 venda na campanha  
- [ ] Events Manager (teste) recebe evento se token teste configurado  

Não automatizar Playwright Ads; checklist manual no `go-live` ou no guia loja.

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Evolution não envia referral | Task 0; fallback `codigo_ctwa` na mensagem; roadmap Cloud API se necessário |
| Usuário apaga contexto do anúncio no WA | Meta documenta; first message sem clid → sem messaging CAPI |
| Dono só quer CTWA e ignora catálogo | Playbook: CTWA volume + fatia catálogo para persona; produto não força % |
| Confundir CAPI web e messaging | Adapters separados; event_ids distintos se preciso |
| PII em logs | Igual hardening atual: não logar ctwa_clid completo em info; mascarar |
| Acoplar a multi-WA | CTWA MVP em **1 número/loja**; 6.3 depois reusa campos no canal |

---

## Critérios de “DONE” do plano

1. Task 0 concluída com decisão escrita.  
2. Lead pode carregar origem CTWA (`ctwa_clid` e/ou código).  
3. Campanha Revy casa e ROI conta venda.  
4. Purchase messaging best-effort na venda quando houver `ctwa_clid`.  
5. Docs ensinam Pixel→público→CTWA + CTWA medido.  
6. Lab E2E manual assinado (checkbox Fase F).

**Não** é DONE: lookalike automático, spend API, multi-número, 100% Event Match Quality.

---

## Estimativa de esforço (ordem de grandeza)

| Fase | Dev focado |
|---|---|
| 0 | 0,5–1 dia (+ dependência de anúncio Meta) |
| A | 1–2 dias |
| C | 1–2 dias |
| B | 2–3 dias |
| D | 1 dia |
| E | 0,5 dia |
| F | 0,5–1 dia |
| **Total MVP (sem B2)** | **~1,5–2 semanas** |

---

## Ordem de PRs sugerida

1. `docs`: fixture Task 0 + decisão  
2. `feat(chatbot)`: colunas + ingestão CTWA  
3. `feat(n8n)`: map referral  
4. `feat(portal)`: match campanha CTWA  
5. `feat(portal)`: messaging CAPI + bus  
6. `feat(portal)`: UI  
7. `docs`: guia loja + contexto  

---

## Relação com outros planos

| Plano | Relação |
|---|---|
| 6.1 Tráfego pago | Base ROI/campanha — não reabrir |
| 6.2 Conversões | Bus + Meta web — estender; Google foi movido para Control 4 |
| 6.2c Meta spend | Import automático de gasto — compartilha `meta_campaign_id`; faz ROI CTWA sem digitação |
| 6.3 Multi-WA | Task 0 payload compartilhada; canais multi-número **depois** |
| #5A Catálogo | Persona Pixel permanece lá |
| Eixo A go-live WA | CTWA precisa WA estável; não bloqueia menu/cadastro E2E |

---

## Próximo passo humano (antes de codar A)

1. Executar **Fase 0** no lab com 1 anúncio CTWA barato.  
2. Colar resultado (go/no-go) no topo deste arquivo.  
3. Só então implementar A→C→B.

---

## Checklist de auto-revisão do plano

- [x] Persona Pixel → CTWA coberto (docs + playbook; sem Ad API)  
- [x] Ingestão ctwa_clid  
- [x] Match campanha + ROI  
- [x] CAPI messaging Purchase  
- [x] Segurança token só Portal  
- [x] Fallback sem referral  
- [x] Não reimplementa E8/E10 web  
- [x] Fora de escopo explícito  
- [x] Arquivos e fases com aceite  
