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

1. **Não atender não-salvo com histórico** — **feita no BACKEND** `decidir_roteamento` (`chatbot-api/app/operacao.py`).  
   ⚠️ **Atenção a quem for reler:** a 1ª tentativa mexeu no nó `Gate somente nao salvos1` do n8n, mas isso estava no lugar errado — aquele ramo (`if (!acao)`) só roda no fallback. O **gate real do cliente é o backend**: `Rotear operacao1` chama `/v1/operacao/roteamento`, que decide `cliente`/`ignorar`; o nó do n8n só **aplica** o `acao` (e o handoff). A regra vive no backend porque só ele tem o estado da conversa:
   - não salvo + conversa em andamento (já existe `Mensagem.direcao='saida'`) → `cliente` (não silencia no meio);
   - não salvo + primeiro contato + `chat_found` (histórico pré-bot no WhatsApp) → `ignorar`;
   - não salvo + virgem / Evolution cega → `cliente` (fail-open).
   `Rotear operacao1` passou a enviar `chat_found`. Testes reais em `chatbot-api/tests/test_roteamento_historico.py`. Commits `bf1d4e0` (gate n8n, virou fallback) e `134aec3` (fix real no backend).

2. **Respeitar handoff** — **feita** em `docs/superpowers/plans/2026-08-03-gate-bot-somente-leads-virgens.md`.  
   Gate agora lê `estadoMensagem.bot_ativo !== false` do `Registrar mensagem e ler handoff1`, travado por assert no validador.

   **Trade-off consciente (fail-open):** voltar a atender quando `findChats` vem vazio (fail-open) reabre uma janela residual em que um contato salvo mas sem chat na Evolution (nunca conversou) pode receber uma saudação na primeira mensagem, antes de `primeira_mensagem` virar `false` e o bot calar a partir da segunda.

3. **Memória / histórico**  
   Session key estável por `instance + telefone`; injetar últimas N mensagens do chatbot na prompt do agent (além do buffer n8n).

4. **Primeira mensagem inteligente**  
   Se o texto já trouxer pedido (financiar, preço, modelo) **ou** houver `anuncioDescricao` (ex.: MT-03), não usar só o template “quer ver as motos?”.

5. **Estabilizar `findChats`**  
   Investigar por que a Evolution devolve lista vazia (body, instância multi-WA, JID `@lid` vs telefone). Enquanto cego, o gate continua frágil.

6. **Reativação** — (1) e (2) já estão **no ar** (backend `app2037` redeployado em 2026-08-03; workflow `n8n2037` republicado com `chat_found`). Workflow segue **inativo de propósito**; ligar (`active`) só após smoke em:  
   - lead CTWA/virgem sintético (atende, sem spam real)  
   - não-salvo com conversa no celular (silêncio)  
   - contato salvo (silêncio)  
   - conversa com `bot_ativo: false` (silêncio)

## 6. Relacionado no repo

- Workflow canônico: `n8n/workflow-ai-nao-salvos.json`
- Update live: `n8n/update_live_workflow.js`
- Fail-closed salvos (lista vazia ≠ não salvo): commit `883fb9c`
- **Regra de histórico (fix real, #1): backend `chatbot-api/app/operacao.py` `decidir_roteamento` + `conversa_tem_resposta` em `servico.py`; testes `chatbot-api/tests/test_roteamento_historico.py`. Commit `134aec3`.**
- Handoff + gate n8n (fallback) (#2): `docs/superpowers/plans/2026-08-03-gate-bot-somente-leads-virgens.md`; teste `n8n/test_gate_somente_nao_salvos.js`
- CTWA/atribuição: `docs/fluxo-utm-pixel-ctwa-meta.md`, plano `docs/plans/2026-07-22-plano-ctwa-atribuicao-capi-messaging.md`
- Checkpoint ops: `docs/handoff-contexto.md`

## 7. Status no momento do doc

| Item | Estado |
|---|---|
| Workflow n8n produção | **Inativo** (desligado de propósito) |
| Webhook `POST /webhook/whatsapp-ai` | 404 enquanto inativo |
| Correção (1) histórico | **No ar** no backend `app2037` (`decidir_roteamento`, commit `134aec3`) |
| Correção (2) handoff | **No ar** (gate n8n lê `bot_ativo` do registrar) |
| Correções (3)–(5) | Pendentes (memória à prova de restart, 1ª msg inteligente, `findChats`) |
| Este documento | Registro do diagnóstico; não é plano de implementação formal |

---

*Gerado a partir de logs/execuções do lab em 2026-08-03. Não reimprimir tokens, apikeys ou telefones completos.*
