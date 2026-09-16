---
gatilho: chamada do modelo do bot no n8n volta 400 do OpenCode Go (missing x-opencode-session)
produto: n8n
fonte: externo
verificado_em: 2026-09-16
---
# OpenCode Go recusa chamada sem `x-opencode-session`

O endpoint do OpenCode Go (`https://opencode.ai/zen/go/v1`, compatível com OpenAI) **exige**
o header `x-opencode-session` em toda requisição. Sem ele a resposta é:

    Bad request - please check your parameters
    Error from provider (Console Go): Request is missing x-opencode-session and cannot be
    routed efficiently. Please see https://opencode.ai/docs/go/#where-can-i-use-it

No n8n o sintoma engana: o inbound chega, o debounce roda, o gate da config passa e a falha
aparece **no nó do modelo** (`DeepSeek Chat Model1`, tipo `lmChatOpenAi`), com a esteira
inteira verde antes dele.

O lugar do header é a **credencial**, não o workflow: a credencial OpenAI do n8n tem
`Add Custom Header`/`Header Name`/`Header Value` (o `mergeCustomHeaders` do pacote langchain
injeta em toda chamada do modelo). Fixar `x-opencode-session: revy-whatsapp-bot` funciona —
a validação é presença, não unicidade. Como é credencial, vale em runtime: editar não exige
reimportar workflow nem restart do n8n.

Verificado em 16/09 com chamada direta de dentro do container do `n8n2037`:
`POST /zen/go/v1/chat/completions` com `deepseek-v4.1-flash` + o header → **200**.

Se o Go endurecer e exigir sessão por conversa (o docs pede "um session id estável por
conversa"), não dá para fazer via credencial, que é única. Aí: endpoint Zen pay-as-you-go
(`https://opencode.ai/zen/v1`, `deepseek-v4-flash`) ou API direta da DeepSeek
(`https://api.deepseek.com`, o mesmo provedor do Copiloto).
