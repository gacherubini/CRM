---
gatilho: bot responde vazio ou /v1/operacao/responder devolve 422 texto com modelo de raciocinio
produto: n8n
fonte: repo
verificado_em: 2026-09-16
---
# Modelo que pensa não cabe no teto de 250

O sintoma: o fluxo inteiro verde (inbound, debounce, gate, agente) e o `Responder WhatsApp1`
falha com **422 `texto`** — corpo `{ "texto": "" }`. A causa não é o n8n nem o chatbot: é o
modelo gastando o teto de `maxTokens` (250, fixo por decisão do dono) em `reasoning_content` e
devolvendo `content` vazio.

Medido em 16/09 com chamada direta ao OpenCode Go, prompt real da loja `teste` (2.5k chars) +
"oi, vcs tem moto 150cc?", `max_tokens: 250`:

| Modelo | `reasoning_content` | `content` | Veredito |
|---|---|---|---|
| `deepseek-v4.1-flash` | 1023–1033 | **0** | teto consumido pensando; `finish=length` |
| `deepseek-v4.1-flash` + `reasoning_effort: none` | 0 | 158 | funciona — mas o nó não manda `none` |
| `deepseek-v4-flash` | 695 | 36 (cortado) | não cabe |
| `deepseek-flash` | 1073 (sem tools) / 72 (com tools) | 0 | não cabe no turno de resposta |
| `qwen3.8-flash` | 3756 | 72 | reasoning **não conta** no `max_tokens` (semântica varia!) |
| **`glm-5.3-flash`** | **0** | 82–89 | **escolhido**; 2 turnos com tool call OK |

Três consequências que valem além deste caso:

1. **`max_tokens` não significa a mesma coisa em todo provedor.** Na Go, o reasoning do
   DeepSeek conta no teto; no Qwen não. Comparar modelo por preço sem medir isso engana.
2. **`reasoning_effort: none` resolve na Go, mas o nó do n8n só envia `low`/`medium`/`high`**
   (`LmChatOpenAi.node.js`: `['low','medium','high'].includes(...)`). Não dá para desligar
   raciocínio pela UI; a saída é escolher modelo que não pense.
3. **Antes de subir modelo novo, medir com o prompt real e o teto real** — dentro do próprio
   container (`fly machine exec ... node script.js`) é barato e foi o que separou o problema
   de "modelo" do problema de "workflow".

O teste de aceite do agente com o GLM: turno 1 faz `tool_call` (`consultar_estoque`), turno 2
responde com o veículo — os dois com 0 tokens de raciocínio e dentro de 250.
