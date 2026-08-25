---
gatilho: rodar as ferramentas do agente fora de uma conversa real (preview, lab, carga)
produto: chatbot-api
custo: conversa de mentira aparecendo em Conversas, com telefone que nao existe
fonte: repo
verificado_em: 2026-08-25
---
# `consultar_estoque` não é só leitura — e a gravação dela **cria `Conversa`**

Já se sabia que `consultar_estoque1` escreve: com resultado único ela grava a moto
escolhida em `POST /v1/operacao/moto-escolhida`, chaveada por telefone. Daí o telefone
sintético do preview, para não sobrescrever o estado de uma conversa real.

O que não se sabia é o passo seguinte: `salvar_moto_escolhida_conversa`
(`chatbot-api/app/servico.py:534`) chama `_get_or_create_conversa`. Telefone que nunca
falou com a loja **vira linha em `conversas`**. Telefone sintético não corrompe conversa
de ninguém, mas cria uma — e o preview, que promete ser efêmero, apareceria no
Atendimento com um número que não existe.

Por isso o modo seco do preview corta **duas** coisas em `consultar_estoque1`, e não a
tool inteira: a busca em `/v1/estoque/buscar` continua rodando (é ela que faz o teste
valer) e as duas chamadas a `moto-escolhida` — a que grava e a que limpa — saem do
código. O estado da moto escolhida segue vivo em `$getWorkflowStaticData('global')`, que
é escopado por workflow.

**Regra geral:** antes de dar telefone de mentira a uma ferramenta, pergunte se a rota que
ela chama só lê o telefone ou se o `get_or_create` está escondido lá dentro. No chatbot,
quase toda rota de operação por telefone cria conversa.

Ver [[2026-08-23-o-prompt-do-bot-mora-no-n8n]] (as tools e o `Extrair1`).
