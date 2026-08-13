# Gate do bot — atender só lead virgem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o bot do WhatsApp responder **somente lead virgem** (número não salvo na agenda **e** sem histórico de conversa), respeitar handoff, e não custar nenhuma chamada Evolution a mais.

**Architecture:** A mudança é toda no nó de código `Gate somente nao salvos1` do workflow `n8n/workflow-ai-nao-salvos.json`. Reinterpretamos os sinais que já temos (findChats + registro do chatbot) em vez de somar chamadas: **silêncio exige prova positiva** (salvo na agenda, conversa existente na Evolution, bot já falou antes, ou handoff ativo); na ausência de prova, atende (**fail-open**, escolha do dono). Também corrigimos o bug de handoff (o gate lia `bot_ativo` do nó errado). Teste via harness Node que extrai o jsCode do JSON e roda a matriz de cenários; guarda-costas em `validate_workflow.py`.

**Tech Stack:** n8n (nós `code`, JS), Node 24 (harness de teste, CommonJS), Python 3 (`validate_workflow.py`).

## Global Constraints

- Nenhuma chamada Evolution a mais por mensagem: mantém-se só o `Consultar contato na Evolution1` (findChats) que já existe. **Proibido** adicionar `findContacts`/`findMessages`.
- Não versionar segredos; não imprimir tokens, apikeys ou telefones completos (máscara: últimos 4 dígitos).
- `bot_ativo` (handoff) é lei: se o registrar devolve `bot_ativo: false`, o bot cala — inclusive lead virgem.
- Regra de decisão do gate (`acao` vazio): **atende ⇔ `!handoff && !salvo && !temHistorico`**, onde:
  - `salvo = chat.isSaved === true`
  - `temHistorico = chat.chatFound === true || estadoMensagem.primeira_mensagem === false`
  - `handoff = estadoMensagem.bot_ativo === false`
- Fail-open: silêncio só com prova positiva; sinal ausente/ambíguo (findChats vazio, mismatch de JID) → atende.
- O sinal de anúncio (`veioDeAnuncio`) **não** entra no gate (o fail-open já atende todo virgem, com ou sem anúncio). Ele continua indo pro prompt da IA (`veio_de_anuncio`/`titulo_anuncio`/`descricao_anuncio`) pra moldar a resposta. Toggle opcional documentado na Task 2 (anúncio reativar histórico) fica **desligado** por padrão.
- Rodar `python n8n/validate_workflow.py` antes de concluir (invariante do repo).
- Não reativar o workflow live sem os smokes dos três casos (salvo silencioso / não-salvo-com-histórico silencioso / virgem atende) + handoff silencioso.

## Escopo

**Dentro:** decisão de *quem* o bot atende (gate) + correção de handoff.
**Fora (não mexer agora):** qualidade da resposta da IA — memória/histórico injetado no prompt, saudação inteligente, tool de estoque. Isso é o eixo 3 do diagnóstico (`docs/nao-plano/tutoriais/diagnostico-bot-whatsapp-2026-08-03.md`) e vira plano próprio.

---

## File Structure

- `n8n/workflow-ai-nao-salvos.json` — **Modify**: só o `parameters.jsCode` do nó `Gate somente nao salvos1`. Nenhum outro nó, conexão ou nó novo.
- `n8n/test_gate_somente_nao_salvos.js` — **Create**: harness Node que extrai o jsCode do gate do JSON canônico e roda a matriz de cenários com `assert`. Testa o código realmente versionado (pega regressão se alguém editar o JSON).
- `n8n/validate_workflow.py` — **Modify**: adiciona invariantes que travam a regra nova (gate não pode voltar a `chat.isSaved === false`; precisa referenciar `chatFound` e `estadoMensagem.bot_ativo`).
- `docs/nao-plano/tutoriais/diagnostico-bot-whatsapp-2026-08-03.md` — **Modify**: marca correções (1) gate e (2) handoff como aplicadas e aponta pro plano/teste.

---

### Task 1: Harness de teste + matriz de cenários (RED)

Escreve o harness que roda o jsCode real do gate contra a matriz. Contra o jsCode **atual**, os cenários da regra nova falham — é a prova de que o comportamento atual está errado.

**Files:**
- Create: `n8n/test_gate_somente_nao_salvos.js`

**Interfaces:**
- Consumes: nó `Gate somente nao salvos1` de `n8n/workflow-ai-nao-salvos.json` (`parameters.jsCode`). O jsCode lê, via n8n runtime: `$('Normalizar isSaved Evolution1').first().json` (chat: `{isSaved, chatFound}`), `$('Extrair1').first().json` (origem: `{ehGrupo, veioDeAnuncio, telefone, ...}`), `$('Registrar mensagem e ler handoff1').first().json` (estado: `{primeira_mensagem, bot_ativo, duplicada}`), `$input.first().json` (rot: `{acao, resposta}`). Retorna `[]` (silêncio) ou `[{ json: { ..., acao: 'cliente' } }]` (atende).
- Produces: função `runGate({chat, origem, estado, rot})` e helper `atende(result)`; usados só neste arquivo.

- [ ] **Step 1: Escrever o harness com a matriz de cenários**

```javascript
#!/usr/bin/env node
/*
 * Testa o nó "Gate somente nao salvos1" do workflow canônico rodando o jsCode
 * real extraído do JSON. Regra: atende só lead virgem (não salvo na agenda E
 * sem histórico), respeita handoff, fail-open na dúvida.
 * Sem segredos, sem rede: só lógica pura do gate.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const wf = JSON.parse(
  fs.readFileSync(path.join(__dirname, "workflow-ai-nao-salvos.json"), "utf8")
);
const gateNode = wf.nodes.find((n) => n.name === "Gate somente nao salvos1");
if (!gateNode) throw new Error("nó 'Gate somente nao salvos1' não encontrado");
const gateFn = new Function("$", "$input", gateNode.parameters.jsCode);

function runGate({ chat = {}, origem = {}, estado = {}, rot = {} }) {
  const nodes = {
    "Normalizar isSaved Evolution1": chat,
    Extrair1: origem,
    "Registrar mensagem e ler handoff1": estado,
  };
  const $ = (name) => ({ first: () => ({ json: nodes[name] }) });
  const $input = { first: () => ({ json: rot }) };
  const out = gateFn($, $input);
  return Array.isArray(out) ? out : [];
}
const atende = (r) => r.length === 1 && r[0].json.acao === "cliente";

const casos = [
  {
    nome: "S1 salvo na agenda -> silêncio",
    entrada: {
      chat: { isSaved: true, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S2 não salvo COM histórico -> silêncio (incômodo principal)",
    entrada: {
      chat: { isSaved: false, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S3 virgem (findChats vazio) -> atende",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: false, veioDeAnuncio: false },
    },
    esperado: true,
  },
  {
    nome: "S4 virgem de anúncio -> atende (fail-open)",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: false, veioDeAnuncio: true },
    },
    esperado: true,
  },
  {
    nome: "S5 handoff sobre não-salvo -> silêncio (bug de handoff)",
    entrada: {
      chat: { isSaved: false, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: false },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S6 handoff no 2º passe (acao=cliente) -> silêncio",
    entrada: {
      chat: {},
      estado: { bot_ativo: false },
      origem: { ehGrupo: false },
      rot: { acao: "cliente" },
    },
    esperado: false,
  },
  {
    nome: "S7 bot já falou (Evolution cega, primeira_mensagem false) -> silêncio",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S8 grupo -> silêncio",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: true },
    },
    esperado: false,
  },
];

let falhas = 0;
for (const c of casos) {
  const got = atende(runGate(c.entrada));
  try {
    assert.strictEqual(got, c.esperado);
    console.log("ok  -", c.nome);
  } catch (_) {
    falhas++;
    console.error(`FALHOU - ${c.nome} (esperado atende=${c.esperado}, obtido=${got})`);
  }
}
if (falhas) {
  console.error(`\n${falhas} cenário(s) falharam`);
  process.exit(1);
}
console.log(`\n${casos.length} cenários passaram`);
```

- [ ] **Step 2: Rodar o teste contra o gate atual e confirmar que falha**

Run: `cd /Users/gabrielabreucherubini/Documents/codigo/CRM && node n8n/test_gate_somente_nao_salvos.js`
Expected: FALHA (exit 1). Esperado ver `FALHOU` em pelo menos: **S2** (hoje atende quem tem histórico), **S3/S4** (hoje `isSaved: null` silencia virgem), **S5/S6** (hoje ignora `bot_ativo`).

- [ ] **Step 3: Commit do teste (RED)**

```bash
git add n8n/test_gate_somente_nao_salvos.js
git commit -m "test(n8n): matriz de cenários do gate somente-virgem (RED)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Reescrever o gate (GREEN)

Troca só o `jsCode` do nó `Gate somente nao salvos1`: nova regra de decisão + `bot_ativo` vindo do registrar (corrige handoff). Mantém intactas as ramificações `cliente`/`cadastro`/`cadastro_controle`/`operacao_controle`.

**Files:**
- Modify: `n8n/workflow-ai-nao-salvos.json` (nó `Gate somente nao salvos1`, campo `parameters.jsCode`, ~linha 202)

**Interfaces:**
- Consumes: mesmos nós de entrada da Task 1.
- Produces: mesmo contrato de saída (`[]` ou `[{json:{...,acao:'cliente'}}]`). Ramos de `acao` já roteado inalterados.

- [ ] **Step 1: Substituir o jsCode do nó**

Substituir o `jsCode` atual (que começa com `let chat = {};` e decide por `chat.isSaved === false && botAtivo`) por exatamente este conteúdo. É o mesmo texto, com o `const botAtivo` agora vindo de `estadoMensagem`, o bloco `if (!acao)` reescrito, e as ramificações seguintes preservadas:

```javascript
let chat = {};
try { chat = $('Normalizar isSaved Evolution1').first().json || {}; } catch (e) {}
let origem = $('Extrair1').first().json;
const rot = $input.first().json || {};
const acao = rot.acao;
let estadoMensagem = {};
try { estadoMensagem = $('Registrar mensagem e ler handoff1').first().json || {}; } catch (e) {}
origem = { ...origem, primeiraMensagem: estadoMensagem.primeira_mensagem === true };
// Handoff manda no bot: bot_ativo vem do registrar (ler handoff), NAO do Extrair1.
const botAtivo = estadoMensagem.bot_ativo !== false;
if (!acao) {
  if (origem.ehGrupo) return [];
  // Atende so lead virgem: nao salvo na agenda E sem historico conhecido.
  // Silencio exige prova positiva; ausencia de prova (findChats vazio/mismatch) -> atende (fail-open).
  const salvo = chat.isSaved === true;                       // agenda do celular
  const temHistorico = chat.chatFound === true               // conversa no cel (desde o connect da Evolution)
    || estadoMensagem.primeira_mensagem === false;           // bot ja falou com esse numero (pega mismatch da Evolution)
  const atende = botAtivo && !salvo && !temHistorico;
  return atende ? [{ json: { ...origem, acao: 'cliente' } }] : [];
}
if (acao === 'cliente') {
  if (origem.ehGrupo || !botAtivo) return [];
  return [{ json: { ...origem, acao } }];
}
if (acao === 'cadastro') {
  return [{ json: { ...origem, acao } }];
}
if (acao === 'cadastro_controle' || acao === 'operacao_controle') {
  const resposta = String(rot.resposta || '').trim();
  if (!resposta) return [];
  return [{ json: { ...origem, acao, output: resposta } }];
}
return [];
```

No arquivo, o valor de `jsCode` é uma string única com `\n` escapados. Use a ferramenta Edit para trocar o valor do campo mantendo o JSON válido (uma linha). **Toggle opcional (deixar comentado, desligado):** se um dia quiser que anúncio reative lead com histórico velho da Evolution, trocar `chat.chatFound === true` por `(chat.chatFound === true && !origem.veioDeAnuncio)` — isso mantém `salvo` e `primeira_mensagem === false` (bot em conversa viva) como silêncio, mas deixa o anúncio furar só o histórico da Evolution. Não aplicar sem o dono pedir.

- [ ] **Step 2: Validar que o JSON continua parseável**

Run: `cd /Users/gabrielabreucherubini/Documents/codigo/CRM && node -e "JSON.parse(require('fs').readFileSync('n8n/workflow-ai-nao-salvos.json','utf8')); console.log('json ok')"`
Expected: `json ok`

- [ ] **Step 3: Rodar o harness e confirmar verde**

Run: `cd /Users/gabrielabreucherubini/Documents/codigo/CRM && node n8n/test_gate_somente_nao_salvos.js`
Expected: `8 cenários passaram` (exit 0).

- [ ] **Step 4: Commit (GREEN)**

```bash
git add n8n/workflow-ai-nao-salvos.json
git commit -m "fix(n8n): bot atende so lead virgem e respeita handoff

Gate somente nao salvos1: silencio exige prova positiva (salvo na agenda,
conversa na Evolution, bot ja falou, ou handoff). Fail-open na duvida.
bot_ativo passa a vir do registrar (corrige atropelo do vendedor).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Guarda-costas no validador + doc

Trava a regra nova no `validate_workflow.py` (pra não reverterem sem querer) e atualiza o diagnóstico.

**Files:**
- Modify: `n8n/validate_workflow.py`
- Modify: `docs/nao-plano/tutoriais/diagnostico-bot-whatsapp-2026-08-03.md`

**Interfaces:**
- Consumes: `n8n/workflow-ai-nao-salvos.json` (já carregado como `data` no `main()`), nó `Gate somente nao salvos1`.
- Produces: nada (script de validação; `assert` levanta em regressão).

- [ ] **Step 1: Adicionar invariantes do gate no `validate_workflow.py`**

Dentro de `main()`, depois das checagens existentes de webhook, inserir:

```python
    gate = next(
        (n for n in data.get("nodes", []) if n.get("name") == "Gate somente nao salvos1"),
        None,
    )
    assert gate is not None, "nó 'Gate somente nao salvos1' sumiu"
    gate_code = gate.get("parameters", {}).get("jsCode", "")
    assert "chat.isSaved === false" not in gate_code, (
        "gate voltou a atender por isSaved===false (regra antiga)"
    )
    assert "chat.chatFound === true" in gate_code, (
        "gate não checa histórico (chatFound)"
    )
    assert "estadoMensagem.bot_ativo !== false" in gate_code, (
        "gate não lê bot_ativo do registrar (handoff furado)"
    )
```

- [ ] **Step 2: Rodar o validador**

Run: `cd /Users/gabrielabreucherubini/Documents/codigo/CRM && python n8n/validate_workflow.py && echo VALIDADO`
Expected: `VALIDADO` (sem AssertionError).

- [ ] **Step 3: Marcar as correções no diagnóstico**

Editar `docs/nao-plano/tutoriais/diagnostico-bot-whatsapp-2026-08-03.md`, seção "5. Correções recomendadas": marcar (1) exceção de gate e (2) handoff como **feitas** neste plano, e na tabela da seção 7 mudar "(1)–(2)" para "aplicadas em `docs/referencia-viva/planos/2026-08-03-gate-bot-somente-leads-virgens.md`; (3)–(5) pendentes". Acrescentar uma linha apontando o teste `n8n/test_gate_somente_nao_salvos.js`. Registrar em uma frase o trade-off do fail-open (ver seção "Risco" abaixo).

- [ ] **Step 4: Commit**

```bash
git add n8n/validate_workflow.py docs/nao-plano/tutoriais/diagnostico-bot-whatsapp-2026-08-03.md
git commit -m "test(n8n): trava regra do gate no validador + atualiza diagnóstico

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Risco consciente (fail-open reverte parte do 883fb9c)

O commit `883fb9c` tornou "findChats vazio → silêncio" pra parar de atender todo mundo. Este plano volta a "vazio → atende" (fail-open, decisão do dono). A diferença que segura a barra: agora o `primeira_mensagem === false` do chatbot silencia quem o bot **já atendeu**, mesmo com a Evolution cega. Efeito residual aceito: um contato **salvo mas sem chat na Evolution** (nunca conversou) pode receber **uma** saudação na primeira mensagem; a partir da segunda, `primeira_mensagem` vira `false` e cala. Documentar isso no diagnóstico (Task 3, Step 3).

## Deploy / reativação (fora do escopo de código, checklist)

Depois dos 3 commits e testes verdes, **não reativar** o workflow live sem:
1. Aplicar o JSON no n8n live (`n8n/update_live_workflow.js`) — ver `n8n/GUIA-WORKFLOW.md`.
2. Smoke, com telefone mascarado nos logs:
   - lead CTWA sintético (virgem) → **atende**;
   - número com conversa na Evolution, não salvo → **silêncio**;
   - contato salvo na agenda → **silêncio**;
   - conversa com `bot_ativo: false` → **silêncio**.
3. Evidência de health + execução sem imprimir segredos.

---

## Self-Review

- **Cobertura do pedido:** regra 1 (salvo → silêncio) = S1 + invariante; regra 2 (não salvo + histórico → silêncio) = S2/S5/S7; virgem atende = S3/S4; anúncio via fail-open = S4; handoff respeitado = S5/S6 + `bot_ativo` do registrar; zero chamada Evolution a mais = Global Constraints + nenhum nó novo. ✓
- **Placeholders:** nenhum — todo passo tem código/comando real. ✓
- **Consistência de tipos:** `runGate`/`atende` definidos e usados na Task 1; nomes de nós idênticos entre harness, gate e validador (`Gate somente nao salvos1`, `Normalizar isSaved Evolution1`, `Extrair1`, `Registrar mensagem e ler handoff1`). ✓
