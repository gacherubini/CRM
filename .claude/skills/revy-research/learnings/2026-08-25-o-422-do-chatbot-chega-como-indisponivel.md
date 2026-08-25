---
gatilho: por um formulario do portal para gravar em rota do chatbot
produto: portal-gestao
custo: a tela culpa a conexao por um erro de digitacao, sem dizer qual campo
fonte: repo
verificado_em: 2026-08-25
---
# `ChatbotClient` transforma **todo** erro HTTP em `ChatbotIndisponivel`

`_request` (`portal-gestao/app/clients/chatbot.py`) termina em
`resposta.raise_for_status()` dentro de um `except (httpx.HTTPError, ValueError)` que
levanta `ChatbotIndisponivel`. `httpx.HTTPStatusError` **é** `httpx.HTTPError` — então
`422 Unprocessable Entity` sai de lá como "não foi possível acessar o chatbot agora".

Para leitura isso passa despercebido. Para **formulário** é um bug de produto: o lojista
digita `8:00` num horário, e a tela responde *"não foi possível salvar agora"*. Ele
recarrega, tenta de novo, o mesmo acontece — e conclui que o produto está fora do ar,
quando o que existe é um campo errado que ninguém apontou.

Só `404` e `409` tinham escape (`erro_404`, `erro_409`). O `422` ganhou o dele em
`salvar_rascunho_agente` (`erro_422=True` → `CamposAgenteInvalidos`, que carrega os
**nomes** dos campos vindos do `detail` do pydantic). Rota nova de escrita que aceite
formulário precisa do mesmo tratamento — o default do cliente é engolir.

Isto **não** aparece em pytest com fake de cliente: o fake levanta a exceção que você
mandou ele levantar. Apareceu no navegador, com portal e chatbot locais de verdade — que
é a única forma de ver o que o `raise_for_status` faz com o status real.

Ver [[2026-08-23-copiloto-so-se-verifica-no-navegador]].
