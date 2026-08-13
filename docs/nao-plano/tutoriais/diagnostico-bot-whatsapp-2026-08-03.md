# Diagnóstico: bot WhatsApp (lab Fly, 2026-08-03)

**Escopo:** workflow n8n `wAiNaoSalvos0001` (`WhatsApp IA - Somente Nao Salvos`), chatbot-api e Evolution no lab 3-VM (`n8n2037`, `app2037`, `evolution2037`).  
**Telefones mascarados** (últimos 4 dígitos). **Workflow ficou inativo de propósito** após o diagnóstico — não reativar sem corrigir os itens abaixo.

## Resumo

O bot ficou ruim por três eixos juntos:

1. **Gate `isSaved`** — `findChats` vazio na Evolution vira `isSaved: null` (fail-closed) e **bloqueia lead novo/patrocinado**; antes do fail-closed o vazio virava `false` e o bot atendia demais (incluindo salvos).
2. **Handoff furado** — `bot_ativo: false` do registrar **não é aplicado** no gate; o bot responde em cima do vendedor.
3. **IA sem contexto** — saudação engessada de “primeiro contato”, pouco uso de histórico e do texto do anúncio (CTWA).

## 1. Patrocinado que não respondeu

**Número `5571***7252` · execução n8n `10234` · ~17:47:53 UTC**

| Campo | Valor |
|---|---|
| Mensagem | `Olá! Posso ter mais informações sobre isso?` (texto padrão CTWA/Meta) |
| Anúncio | **Detectado** — `veioDeAnuncio: true`, `ctwa_clid` presente, `ctwa_source_type: ctwa_ad` |
| Produto no ad | Yamaha MT-03 2023 (`anuncioTitulo` / `anuncioDescricao` preenchidos) |
| `bot_ativo` | `true`, `primeira_mensagem: true` |
| Evolution `findChats` | Lista vazia (`chatsReturned: 0`, `chatFound: false`) |
| `isSaved` | **`null`** (fail-closed) |
| Último nó | `Gate somente nao salvos1` → **parou, sem IA e sem envio** |

O fluxo **viu** o anúncio, gravou a mensagem no chatbot, mas o gate “somente não salvos” exige `isSaved === false`. Contato novo sem chat na Evolution cai em `null` e **não responde**.

Mesmo padrão em `5533***8134` (“Qual o preço dela” / “Ano e km”): `bot_ativo true`, `isSaved null`, gate bloqueou.

### Inconsistência temporal do `isSaved`

| Momento | `findChats` vazio | Comportamento |
|---|---|---|
| Antes do fail-closed (~17:42, commit `883fb9c`) | costumava virar `isSaved: false` | Bot **atendia** quase todo mundo (incluindo casos que deviam silenciar) |
| Depois (ex.: patrocinado 17:47) | `isSaved: null` | Bot **não atende** cliente novo sem chat na Evolution |

`findChats` voltou vazio com frequência nas execuções inspecionadas (`FIND0` ≈ `{}`). Gate fail-closed + Evolution sem chat = **silêncio nos leads frescos**, inclusive CTWA.

## 2. Quando o bot respondeu, respondeu mal

### a) Ignora o conteúdo da mensagem

| Cliente disse | Bot respondeu |
|---|---|
| `Financiar` | `oi, miguel. aqui é da vitor motos. quer dar uma olhada nas motos disponíveis?` |
| `+55 19 98821-8115` | mesma saudação genérica |
| `Fica longe` | mesma saudação genérica |
| `9` | mesma saudação genérica |
| `Blz` (thread de simulação) | mesma saudação de primeiro contato |

O prompt incentiva cumprimento em `primeira_mensagem`, e o agente **não usa o pedido real** (financiar, preço, “dela”, etc.). No patrocinado, o contexto da MT-03 já estava em `anuncioTitulo`/`anuncioDescricao` — a IA nem chegou a rodar.

### b) “Sem histórico” é real

- Memória do n8n (window buffer) não puxa conversa anterior de forma útil; o bot trata quase tudo como primeiro contato.
- Ex.: `5519***9874` já tinha histórico de julho; o bot entrou com saudação genérica e “não tenho pcx”.
- `5516***9954` estava em **handoff** com “blz simular aqui”; cliente mandou “Blz” e o bot reiniciou do zero.

### c) Bot responde com conversa em handoff (`bot_ativo: false`)

Várias execuções com registrar devolvendo `bot_ativo: false` ainda chegam em `AI Agent1` / `Responder WhatsApp1`.

Causa provável no workflow (`Rotear operacao1` / gate): usa `origem` do nó `Extrair1` e só mescla `primeiraMensagem` do registrar; **não aplica `bot_ativo`**. Com `origem.bot_ativo` indefinido, `bot_ativo !== false` fica sempre verdadeiro.

Efeito: bot falando por cima do humano em threads como `***7567`, `***9874`, `***9954`.

### d) Estoque / tool

`Quer pcx` → resposta “não tenho nenhuma pcx no estoque agora…”. Validar se o estoque realmente não tem PCX ou se a tool/consulta falhou/sem match.

## 3. Casos abertos sem resposta útil (amostra)

| Tel (máscara) | Situação |
|---|---|
| `5571***7252` | CTWA MT-03 — bloqueado por `isSaved null` |
| `5533***8134` | Preço/ano/km — mesmo bloqueio |
| `5519***5932` | Só cumprimento; “Simm” sem follow-up útil |
| `5519***3097` | Cumprimento genérico; “compram ela” sem resposta |
| `5519***9737` | Várias msgs de simulação/score — nenhuma saída do bot no trecho |

## 4. Evidência operacional

- **n8n:** SQLite `/home/node/.n8n/database.sqlite` no app `n8n2037`; workflow `wAiNaoSalvos0001`.
- **Chatbot:** `GET /v1/conversas` + `/v1/conversas/{tel}/mensagens` na porta interna `8001` do `app2037`.
- **Evolution:** webhooks para `https://n8n2037.fly.dev/webhook/whatsapp-ai` (com workflow inativo → 404 esperado).
- Execuções longas (~IA) no período: dezenas; amostra de AI responses inclui `10216`, `10215`, `10201`, `10122`, `10121`, `10097`, etc.
- Patrocinado bloqueado: execução **`10234`**.

## 5. Correções recomendadas (ordem sugerida)

1. **Não atender não-salvo com histórico + fail-open Evolution cega** — **feita** (backend +
   gate n8n). Backend `decidir_roteamento` / `_decidir_cliente_ou_ignorar`:
   - `is_saved is True` → ignorar (só prova de agenda);
   - conversa com saída → cliente (em andamento);
   - `chat_found is True` no primeiro contato → ignorar;
   - `is_saved` False/**None** sem prova de histórico → **cliente** (fail-open).
   Gate n8n `atendeLeadVirgem()` (em `Gate somente nao salvos1`) reaplica a tranca em
   `acao=cliente` e no fallback: handoff, agenda, `tem_saida`, `chatFound`.
   Commits: `134aec3`, **`8effb99`**. Testes: `test_roteamento_historico.py`,
   `n8n/test_gate_somente_nao_salvos.js` (11 cenários).

2. **Respeitar handoff** — **feita**. Gate lê `estadoMensagem.bot_ativo !== false` do
   registrar; assert no `validate_workflow.py`.

   **Trade-off consciente (fail-open):** contato salvo que a Evolution não achar
   (`isSaved null`) pode levar **uma** saudação; com handoff/agenda/`chatFound` a tranca cala.

3. **Memória / histórico** — **feita no código (`8effb99`)**. Registrar devolve
   `historico_recente` (últimas msgs CRM); user prompt do Agent injeta o bloco.
   Buffer n8n (`Memoria da conversa1`) permanece; histórico CRM sobrevive restart.

4. **Primeira mensagem inteligente** — **feita no código (`8effb99`)**. System message
   com “prioridade absoluta”: responde `mensagem_atual`; template “quer ver as motos?”
   só em cumprimento puro sem pedido/anúncio/histórico.

5. **Estabilizar `findChats`** — **pendente**. Agenda via Evolution ainda é melhor esforço
   (`@lid`, lista vazia). Fail-open mitiga silêncio em lead; não substitui `findContacts`.

5b. **2ª msg silenciada após 1ª resposta (`isSaved` antes de `tem_saida`)** — **feita no
   código**. Caso `***6615` (exec n8n `10617`, “Gostei da gs310”): após a saída do bot,
   Evolution passou a devolver `isSaved: true`/`chatFound: true`; backend e gate n8n
   checavam agenda **antes** de `tem_saida` e retornavam `ignorar`. Ordem corrigida:
   `tem_saida` → agenda → `chatFound`. Testes: `test_salvo_conversa_em_andamento_atende`,
   gate S12/S13.

6. **Reativação** — código no Git; **deploy + reimport + Active** sob critério do owner.
   Smoke antes de Active ON:
   - lead CTWA/virgem (atende; pedido específico sem template genérico)
   - não-salvo com conversa no celular / `chatFound` (silêncio)
   - contato salvo (silêncio)
   - `bot_ativo: false` (silêncio)

## 6. Relacionado no repo

- Workflow canônico: `n8n/workflow-ai-nao-salvos.json`
- Guia: `n8n/GUIA-WORKFLOW.md`
- Fail-open + prompt + histórico: commit **`8effb99`**
- Histórico pré-bot no backend: commit `134aec3`
- Handoff / plano virgem: `docs/referencia-viva/planos/2026-08-03-gate-bot-somente-leads-virgens.md`
- Teste gate: `n8n/test_gate_somente_nao_salvos.js`
- Checkpoint ops: `docs/referencia-viva/handoff-contexto.md`

## 7. Status no momento do doc (atualizado pós-`8effb99`)

| Item | Estado |
|---|---|
| Código A+B no Git | **Sim** (`8effb99`) |
| Deploy `app2037` com A+B | A confirmar / fazer se ainda não subiu |
| Workflow n8n produção | **Manter inativo** até reimport + smoke |
| Correções (1)–(4) | **No código**; (5) pendente |
| Este documento | Diagnóstico + status das correções |

---

*Gerado a partir de logs/execuções do lab em 2026-08-03. Não reimprimir tokens, apikeys ou telefones completos.*
