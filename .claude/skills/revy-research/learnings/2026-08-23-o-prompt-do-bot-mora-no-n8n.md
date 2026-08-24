---
gatilho: mudar o prompt do bot, o tom da IA ou o que ela pode responder
produto: n8n
custo: um deploy do bundle inteiro sem efeito nenhum
fonte: repo
verificado_em: 2026-08-23
---
# O prompt do bot nao esta no chatbot-api

O `systemMessage` do AI Agent mora em **`n8n/workflow-ai-nao-salvos.json`** (no
`workflow-cloud.json`, para o Modo 2). O `chatbot-api` nao tem nenhum prompt de
LLM: ele so monta o texto compacto das ultimas mensagens **para** esse prompt
(`chatbot-api/app/servico.py:713`) e expoe as tools HTTP que o agente chama.

Consequencia no deploy: mexer no prompt e deployar o `app2037` nao muda nada — o
bot continua falando igual. O alvo e o **n8n2037**, com a sequencia de
`2026-08-23-import-do-n8n-desativa-o-workflow.md`.

O canonico e gerado: nao editar o `*.ready.json`, e no Modo 2 nao editar o
`workflow-cloud.json` a mao (ver `2026-08-23-workflow-cloud-e-gerado.md`).
