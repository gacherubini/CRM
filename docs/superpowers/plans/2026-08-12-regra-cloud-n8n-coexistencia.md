# Regra Cloud "humano falou" + pipeline n8n-cloud — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans. Steps usam checkbox (`- [ ]`).
> **Desbloqueado por pesquisa (2026-08-12):** os 4 payloads da coexistência (`messages`, `smb_message_echoes`, `history`, `smb_app_state_sync`) estão documentados com exemplo real (Meta webhook reference + dualhook). O parser é escrito **contra os exemplos**; o spike vira **smoke test** (confirmar que o payload real bate + onboarding funciona).

**Goal:** Fazer o WhatsApp oficial (Cloud API em coexistência) atender leads exatamente como o Baileys, aplicando a regra **"o bot responde a menos que um humano já tenha falado na conversa"** — **reusando** o mecanismo de handoff que já existe no `chatbot-api`. O trabalho novo é o **pipeline `n8n-cloud`** que recebe o webhook da Meta **direto** e o mapeia para o contrato `/webhook/mensagem` com os flags certos.

**Architecture:** Meta → **webhook direto no n8n** (o Evolution não repassa eventos de coexistência — achado da pesquisa). Um workflow `n8n-cloud` valida o token, **mapeia cada evento** para `{instance, telefone, texto, from_me, origem_bot, provider_message_id, ctwa_*}` e posta em `/webhook/mensagem` (registro + handoff) e `/v1/operacao/roteamento` (gate). O backend já faz o resto: `from_me and not origem_bot` → `conversa.bot_ativo=false` (`servico.py:1107`); no Cloud `is_saved`/`chat_found` chegam `None` → gate fail-open (bot responde lead novo).

**Tech Stack:** n8n (workflow JSON + code node JS), Meta WhatsApp Cloud API webhooks, `chatbot-api` (`MensagemEntrada`, `registrar_mensagem`, `decidir_roteamento`).

## Contrato de atribuição (o parser implementa isto)

| Webhook `field` | Origem | `telefone` (chave) | `from_me` | `origem_bot` |
|---|---|---|---|---|
| `messages` | cliente | `messages[].from` | `false` | `false` |
| `smb_message_echoes` | humano (app/linked) | `message_echoes[].to` | `true` | `false` |
| `history` (msg `from` == `metadata.display_phone_number`) | humano (pré-bot) | thread `id` | `true` | `false` |
| `history` (msg `from` == cliente) | cliente (passado) | thread `id` | `false` | `false` |
| envio do bot (nosso, via Cloud API) | bot | cliente | `true` | `true` |

`instance` = `metadata.phone_number_id` em todos os casos.

## Global Constraints

- **Regra só no Cloud.** Números Baileys não mudam (mantêm `is_saved`/`chat_found`).
- **Reuso do backend.** NÃO reescrever `/webhook/mensagem`, handoff ou gate — só alimentá-los com os flags certos.
- **Meta→n8n direto** para a linha Cloud (Evolution fica só no Baileys + envio Cloud, se usado).
- **Idempotência por `wamid`.** A Meta entrega *at-least-once*; o `provider_message_id` (=`id` do evento) é a chave de dedupe (a UNIQUE `(canal_id, provider_message_id)` já arbitra — `servico.py:1150`).
- **Responder 200 rápido** (timeout Meta 5–10s): o n8n retorna 200 e processa; posts ao backend são idempotentes.
- **`smb_app_state_sync` (contatos): ignorado na v1** — a regra usa histórico de conversa (autoria), não agenda.
- Testes: n8n JS a partir da raiz; `chatbot-api` via `.\.venv\Scripts\python.exe -m pytest -q`.

---

## FASE C1 — Parser do `n8n-cloud` (o mapeamento)

### Task 1: função `mapearEventoCloud(body)`

**Files:**
- Create: `n8n/cloud_map.js` (função pura, reutilizada como código do code node)
- Test: `n8n/test_cloud_map.js` (espelha `n8n/test_fallback_estoque_temporario.js`)

**Interfaces:**
- Produces: `mapearEventoCloud(body) -> Array<{instance, telefone, texto, provider_message_id, from_me, origem_bot, ctwa_clid, meta_ad_id}>` — um item por mensagem, cobrindo `messages` / `smb_message_echoes` / `history`.

- [ ] **Step 1: Teste que falha** (usa os payloads de exemplo documentados)

```js
// n8n/test_cloud_map.js
const assert = require('assert');
const { mapearEventoCloud } = require('./cloud_map');

// smb_message_echoes = humano pelo app -> from_me true, origem_bot false, telefone = to
const echo = {object:'whatsapp_business_account', entry:[{id:'WABA', changes:[{field:'smb_message_echoes', value:{
  metadata:{display_phone_number:'15550783881', phone_number_id:'106540352242922'},
  message_echoes:[{from:'15550783881', to:'16505551234', id:'wamid.ECHO', timestamp:'1739321024', type:'text', text:{body:'oi'}}]
}}]}]};
let out = mapearEventoCloud(echo);
assert.strictEqual(out.length, 1);
assert.deepStrictEqual(
  {t: out[0].telefone, fm: out[0].from_me, ob: out[0].origem_bot, id: out[0].provider_message_id, instance: out[0].instance},
  {t: '16505551234', fm: true, ob: false, id: 'wamid.ECHO', instance: '106540352242922'}
);

// messages = cliente -> from_me false, telefone = from
const msg = {entry:[{changes:[{field:'messages', value:{
  metadata:{phone_number_id:'106540352242922'},
  messages:[{from:'16505551234', id:'wamid.IN', timestamp:'1', type:'text', text:{body:'quero simular'}}]
}}]}]};
out = mapearEventoCloud(msg);
assert.strictEqual(out[0].from_me, false);
assert.strictEqual(out[0].telefone, '16505551234');

// history: msg do negócio (from == display_phone_number) = humano; do cliente = entrada
const hist = {entry:[{changes:[{field:'history', value:{
  metadata:{display_phone_number:'15550783881', phone_number_id:'106540352242922'},
  history:[{metadata:{phase:0,chunk_order:1,progress:55}, threads:[{id:'16505551234', messages:[
    {from:'15550783881', id:'wamid.H1', timestamp:'1', type:'text', text:{body:'resposta antiga'}},
    {from:'16505551234', id:'wamid.H2', timestamp:'2', type:'text', text:{body:'msg antiga do cliente'}}
  ]}]}]
}}]}]};
out = mapearEventoCloud(hist);
assert.strictEqual(out.length, 2);
assert.strictEqual(out[0].from_me, true);   // negócio = humano
assert.strictEqual(out[0].telefone, '16505551234');
assert.strictEqual(out[1].from_me, false);  // cliente
console.log('ok');
```

- [ ] **Step 2: Rodar e ver falhar** — `node n8n/test_cloud_map.js` → `Cannot find module './cloud_map'`.

- [ ] **Step 3: Implementar** `n8n/cloud_map.js`

```js
function textoDe(m) {
  return (m && m.type === 'text' && m.text) ? (m.text.body || null) : null;
}
function referralDe(m) {
  const r = (m && (m.referral || (m.text && m.text.referral))) || null;
  return r ? { ctwa_clid: r.ctwa_clid || null, meta_ad_id: r.source_id || null } : null;
}
function item(instance, telefone, m, from_me, origem_bot) {
  const ctwa = from_me ? null : referralDe(m);
  return {
    instance, telefone, texto: textoDe(m),
    provider_message_id: m.id || null,
    from_me, origem_bot,
    ctwa_clid: ctwa ? ctwa.ctwa_clid : null,
    meta_ad_id: ctwa ? ctwa.meta_ad_id : null,
  };
}
function mapearEventoCloud(body) {
  const itens = [];
  for (const e of ((body && body.entry) || [])) {
    for (const ch of (e.changes || [])) {
      const value = ch.value || {};
      const meta = value.metadata || {};
      const instance = meta.phone_number_id;
      const numeroEmpresa = meta.display_phone_number;
      if (ch.field === 'messages') {
        for (const m of (value.messages || [])) itens.push(item(instance, m.from, m, false, false));
      } else if (ch.field === 'smb_message_echoes') {
        for (const m of (value.message_echoes || [])) {
          if (m.type === 'edit' || m.type === 'revoke') continue; // v1
          itens.push(item(instance, m.to, m, true, false));       // humano; conversa = m.to
        }
      } else if (ch.field === 'history') {
        for (const h of (value.history || [])) {
          for (const t of (h.threads || [])) {
            for (const m of (t.messages || [])) {
              const doNegocio = (m.from === numeroEmpresa);        // negócio = humano (pré-bot)
              itens.push(item(instance, t.id, m, doNegocio, false));
            }
          }
        }
      }
      // smb_app_state_sync: ignorado na v1
    }
  }
  return itens.filter((x) => x.texto || x.provider_message_id);
}
module.exports = { mapearEventoCloud };
```

- [ ] **Step 4: Rodar e ver passar** — `node n8n/test_cloud_map.js` → `ok`.
- [ ] **Step 5: Commit** — `git add n8n/cloud_map.js n8n/test_cloud_map.js && git commit -m "feat(n8n): parser de webhook Cloud/coexistencia (atribuicao humano/bot)"`

---

## FASE C2 — Backend: confirmar o reuso (handoff + gate no Cloud)

### Task 2: testes provando a semântica Cloud no `chatbot-api`

**Files:**
- Test: `chatbot-api/tests/test_cloud_handoff.py`
- (Só implementar código se algum teste falhar — a hipótese é **reuso total**.)

**Interfaces:** consome `POST /webhook/mensagem` (`MensagemEntrada`) e `decidir_roteamento`.

- [ ] **Step 1: Escrever os testes**
  - `test_echo_humano_dispara_handoff`: registrar `MensagemEntrada(instance=canal_cloud, telefone=cliente, from_me=True, origem_bot=False, texto="oi")` → `conversa.bot_ativo is False` e `status == "handoff"`.
  - `test_envio_do_bot_nao_dispara_handoff`: mesmo, com `origem_bot=True` → `bot_ativo` permanece `True`.
  - `test_gate_cloud_fail_open_lead_novo`: `decidir_roteamento(..., is_saved=None, chat_found=None)` para telefone virgem → `acao == "cliente"`.
  - `test_seed_history_marca_handoff`: registrar uma mensagem `from_me=True, origem_bot=False` (simulando history do negócio) → conversa entra em handoff (bot não engaja depois).
- [ ] **Step 2: Rodar** — `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_cloud_handoff.py -q`. **Esperado: PASS** (comportamento já existe). Se algo falhar, ajustar o mínimo em `servico.py`/`operacao.py` mantendo o Baileys intacto (rodar `tests/test_roteamento*.py` para não regredir).
- [ ] **Step 3: Commit** — `test(chatbot): semantica Cloud (echo->handoff, bot nao, gate fail-open)`.

### Task 3: resolver `phone_number_id` → canal da loja

**Files:**
- Modify: `chatbot-api/app/channels.py` / `models_db.py:WhatsAppCanal` (usar `evolution_instance` como o `phone_number_id` do número Cloud, ou adicionar coluna `cloud_phone_number_id`)
- Test: `chatbot-api/tests/test_channels_cloud.py`

**Interfaces:** `resolver_loja_e_canal_por_instancia(db, instance)` precisa achar a loja quando `instance == phone_number_id`.

- [ ] Steps TDD: no piloto, o canal Cloud é criado com `evolution_instance = <phone_number_id>` e `integration` = cloud (o campo de integração é da Fase 2 do design; no piloto pode ser setado à mão). Testar que a resolução por `phone_number_id` acha a loja. Commit `feat(chatbot): resolve loja por phone_number_id (canal Cloud)`.

---

## FASE C3 — Workflow `n8n-cloud` + seed de histórico

### Task 4: workflow `n8n/workflow-cloud.json`

**Files:**
- Create: `n8n/workflow-cloud.json`
- Validar: `python n8n/validate_workflow.py` (a partir da raiz)

Nós (espelhando o `workflow-ai-nao-salvos.json`, mas com o parser da C1):
1. **Webhook** `GET+POST /webhook/whatsapp-cloud` — `GET` responde o `hub.challenge` (verificação da Meta); `POST` recebe o evento.
2. **Verificar token** (`hub.verify_token` / assinatura) — 200 imediato.
3. **Code node** = `mapearEventoCloud($json.body)` (colar `cloud_map.js`), emitindo 1 item por mensagem.
4. **Loop/Split** → por item:
   - `POST http://chatbot-api:8000/webhook/mensagem` com `{instance, telefone, texto, provider_message_id, from_me, origem_bot, ctwa_clid, meta_ad_id}`.
   - Se `from_me=false` (entrada de cliente): `POST /v1/operacao/roteamento` com `{instance, telefone, texto, is_saved:null, chat_found:null}` → se `acao=="cliente"` e conversa não está em handoff, roda o bot e **`POST /webhook/mensagem` com `from_me:true, origem_bot:true`** (registra a resposta do bot, igual ao Baileys).

- [ ] Steps: montar o JSON; `python n8n/validate_workflow.py`; configurar o webhook da Meta apontando pra `<n8n>/webhook/whatsapp-cloud`. Commit `feat(n8n): workflow n8n-cloud (inbound coexistencia -> chatbot)`.

### Task 5: seed de histórico (mesma pipeline)

O `field:history` já é mapeado pelo parser (Task 1) e cai na mesma rota `/webhook/mensagem`. Efeito: mensagens do negócio (humano) marcam a conversa como handoff → o bot não engaja quem já conversou. Nada novo além de garantir que o volume do history (chunks grandes) não estoure timeout — processar assíncrono e idempotente (o `wamid` dedupe).

- [ ] Steps: teste de carga leve (um `history` com N mensagens → N posts idempotentes); confirmar dedupe. Commit `test(n8n): seed de history idempotente via wamid`.

---

## SPIKE reduzido — smoke test (não é mais descoberta)

Com os payloads documentados e o parser escrito, o spike vira confirmação:
1. Onboardar 1 número de teste em coexistência **direto na Meta** (app próprio em dev mode, sem BSP) e apontar o webhook da Meta pro `n8n-cloud`.
2. Mandar msg do "cliente de teste" → o bot responde (via a pipeline).
3. Responder pelo **app** → confirmar `smb_message_echoes` chega e o **bot recua** (handoff).
4. Conferir que o **payload real bate** com os exemplos (campos/nesting) — ajustar o parser se a Meta trouxer variação.
5. Medir latência e estabilidade (app + API no mesmo número).

## Self-Review (cobertura vs §4/§5/§7 do design)

- Regra "bot responde a menos que humano falou": o parser marca autoria (C1) e o handoff existente aplica (C2). **Coberto.**
- Meta→n8n direto: C3 (workflow). **Coberto.**
- History seed: C3/Task 5. **Coberto.**
- Baileys intacto: nada toca o `workflow-ai-nao-salvos.json` nem o gate Baileys. **Coberto.**
- **Aberto (smoke test):** variações reais do payload; latência; e o campo de integração `cloud`/`baileys` no `WhatsAppCanal` vira produto na Fase 2 do design.
