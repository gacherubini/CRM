---
gatilho: mexer no workflow do n8n do Modo 2 (cloud)
produto: n8n
fonte: repo
verificado_em: 2026-08-24
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

**O que o gerador NAO pega: saida orfa.** Um no pode sobreviver ao recorte, continuar
rodando e ter o resultado descartado por quem ficou do outro lado. Foi o caso do
`Atraso anti-ban1` em 24/08: byte a byte identico nos dois workflows, calculando o
`__delayAntiBan` que no Modo 1 faz a Evolution mostrar "digitando..." — e o
`Responder WhatsApp1` do Modo 2 manda `{ telefone, texto }`, sem o delay. No inventario
de nos o fork parecia completo; o bot so parecia menos humano. Ao comparar os dois modos,
compare tambem o que cada no **consome**, nao so quais existem.

Contexto que continua valendo: **nao existe IA dentro do `chatbot-api`** (sem
gemini/openai/langchain). O agente vive nos workflows do n8n, nos dois modos; o produto
so expoe as ferramentas.
