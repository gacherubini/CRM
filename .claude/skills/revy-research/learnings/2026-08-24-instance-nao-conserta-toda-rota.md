---
gatilho: por uma rota do chatbot na credencial de integracao, ou achar que `instance` resolve multi-loja
produto: chatbot-api
custo: um 423 no lugar do 400, um 500 escondido e uma rota que so finge estar consertada
fonte: repo
verificado_em: 2026-08-24
---
# `instance` resolve a loja, mas nao em toda rota — e nao na mesma ordem

Migrando as rotas do bot para `auth.resolver_loja_id` (spec §6.2), tres coisas
nao estavam no plano.

**1. A resolucao vem ANTES do gate operacional.** Quase toda rota abre com
`_exigir_loja_operacional(db, ctx.loja_id)`. Com credencial de integracao
`ctx.loja_id` e `None`, e o gate responde **423** — engolindo o **400** que diz
qual e o erro de verdade ("faltou `instance`"). Resolva primeiro, passe o
`loja_id` resolvido ao gate.

**2. `GET /v1/estoque/buscar` nao dava 400: dava 500.** Ela fazia
`db.get(models_db.Loja, ctx.loja_id)` e lia `.slug` — com `loja_id` nulo isso e
`AttributeError`, nao erro de validacao. Rota que so le `ctx.loja_id` para achar
um objeto tende a estourar, nao a recusar.

**3. `GET /v1/config/catalogo-bot` era cega para loja, e `instance` nao consertava.**
Ela **nao lia `ctx.loja_id`**: quem respondia era `InventoryWriteClient.obter_loja()`,
que bate em `/v1/loja` do Estoque com **um bearer global, sem slug** — enquanto
`provider.buscar` (`inventory.py:205`) usa `/public/v1/lojas/{slug}/veiculos` e
por isso *e* multi-loja. Com N lojas no Modo 2, todas recebiam o catalogo de uma
so. Era buraco do **contrato com o Estoque**, nao da credencial.

**Resolvido em 25/08, e o conserto mostra a regra:** nao se acrescentou o
parametro, mudou-se a **fonte**. O Estoque passou a devolver `catalogo_url` em
`/public/v1/lojas/{slug}` (rota que ja era multi-loja), o chatbot passou a ler
por slug, e **so entao** `instance` foi acrescentada — a tool
`enviar_link_catalogo1` manda, e o `validate_workflow_cloud.py` exige.

**Como aplicar:** antes de dar `instance` a uma rota, pergunte de onde ela tira
a loja hoje. Se a resposta nao for `ctx.loja_id`, `instance` e teatro — e o
trabalho de verdade e mudar a fonte primeiro.

Ver [[2026-08-24-outbound-por-loja-quer-loja-id]] — o mesmo erro do outro lado:
la o worker tinha o `phone_number_id` e a funcao queria `loja_id`.
