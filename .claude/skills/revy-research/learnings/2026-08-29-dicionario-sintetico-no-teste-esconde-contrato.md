---
gatilho: escrever teste de read-model do portal que le dicionario vindo de outro produto
produto: portal-gestao
custo: feature inteira verde no CI e inerte em producao
fonte: repo
verificado_em: 2026-08-29
---

# Dicionário sintético no teste não prova que o outro produto manda aquele campo

`montar_canais_view` (`portal-gestao/app/loja/whatsapp_canais.py`) recebe uma lista de
dicionários que vem de `GET /v1/whatsapp/canais`, do `chatbot-api`. O teste monta esses
dicionários à mão — o que é certo, porque o portal não deve subir o chatbot para testar
read-model.

O buraco: **nada liga o dicionário do teste ao que o outro produto realmente serializa.**
Em 29/08 a view passou a decidir "este canal é Cloud" lendo `waba_id`, os seis testes
ficaram verdes, e `_canal_dict` (`chatbot-api/app/channels.py:27`) não devolvia `waba_id`.
Em produção a feature seria inerte: todo canal viria como Modo 1, e a tela continuaria
oferecendo o botão de QR da Evolution para um número da Cloud API.

O serializer é explícito campo a campo — o que é a decisão certa, e é o que impede segredo
de vazar. O efeito colateral é que **campo novo no modelo não aparece sozinho no payload**.

## Como escapar

Ao ler um campo novo do dicionário do outro produto, **abra o serializer dele e confirme que
o campo está listado** — são dois minutos. `rg "_canal_dict" chatbot-api/app/` acha o de
canais; os outros produtos seguem o mesmo padrão de dicionário explícito.

Se o campo não estiver lá, a task de expor é pré-requisito, não trabalho posterior: sem ela
o que você escreveu já nasce morto, com o CI dizendo que está vivo.

Parente de [[2026-08-23-teste-verde-nao-prova-que-a-feature-existe]], mas o gatilho é outro:
lá o teste testava um stub; aqui ele testa código real, com uma entrada que a realidade não
produz.
