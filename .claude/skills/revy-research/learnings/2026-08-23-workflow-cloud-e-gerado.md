---
gatilho: mexer no workflow do n8n do Modo 2 (cloud)
produto: n8n
---
# `workflow-cloud.json` e gerado — editar a mao sai 1

O `n8n/workflow-cloud.json` e **gerado** por `n8n/fork_cloud_workflow.py` a partir do
workflow do Modo 1, para que agente, Gemini, memoria e ferramentas saiam byte a byte
iguais e para que mudanca do Modo 1 se propague ao regerar. O
`n8n/validate_workflow_cloud.py` compara o arquivo com o gerador e **sai 1** se alguem
editou a mao.

O gerador tambem recusa referencia orfa a no que o recorte deixou para tras. Foi ele que
pegou dois nos citando nomes que nao existiam mais no fork; a correcao foi criar nos-ponte
de mesmo nome, nao reescrever o agente. Fork por recorte comete esse erro calado.

Contexto que continua valendo: **nao existe IA dentro do `chatbot-api`** (sem
gemini/openai/langchain). O agente vive nos workflows do n8n, nos dois modos; o produto
so expoe as ferramentas.
