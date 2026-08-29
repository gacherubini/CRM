---
gatilho: mandar mensagem do lado do servidor numa loja Modo 2 (worker, rota, envio humano)
produto: chatbot-api
custo: AttributeError em producao, num caminho que teste nenhum alcancava
fonte: repo
verificado_em: 2026-08-29
---
# `outbound_para_loja` quer `loja_id`, e o worker só tem `phone_number_id`

`_OutboundPorLoja` (`chatbot-api/app/modo2_workers.py`) recebe um `instance` e chama
`outbound_para_loja(db, instance)`. Só que `instance`, no Modo 2, é o `phone_number_id`
da Meta — e `outbound_para_loja` espera `loja_id`. Ele pergunta "a loja
`<phone_number_id>` é Modo 2?", ouve **não**, e devolve o transporte do **Modo 1**.

O worker então acha que tem um outbound Cloud e tem um Evolution:

- `send_text` existe nos dois, passa, e manda para a instância errada — falha silenciosa;
- `send_template_button` e `send_interactive_button` **não existem** no Evolution e
  estouram `AttributeError`.

Traduza antes com `loja_id_do_phone_number_id` (`app/cloud_canal.py`), que repete as duas
buscas do inbound: canal Cloud primeiro, depois `lojas.evolution_instance` — a loja do
piloto não tem canal Cloud cadastrado, só a coluna.

Isto derrubava **duas** coisas ao mesmo tempo, as duas caladas: a reoferta do rodízio e o
follow-up do Modo 2. A segunda ninguém tinha notado, e consertou de carona.

Ver [[2026-08-23-canal-cloud-nao-se-cadastra-pela-api]] (por que a loja piloto não tem
canal) e [[2026-08-23-teste-verde-nao-prova-que-a-feature-existe]].

## Segunda ocorrencia, 29/08: o envio humano do Atendimento

`_enviar_texto_evolution` (`chatbot-api/app/servico.py`) chamava
**`get_whatsapp_outbound()`**, o singleton do Modo 1, em vez de
`outbound_para_loja`. Numa loja Modo 2 o `evolution_instance` do canal guarda o
`phone_number_id` da Meta, entao a resposta do vendedor saia para o Evolution
pedindo por uma instancia que nao existe la.

**Consequencia: numa loja Modo 2 o vendedor nao conseguia responder pelo
portal.** Ninguem tinha notado porque o handoff entrega a conversa ao WhatsApp
do proprio vendedor — a caixa de texto do Atendimento quase nao e usada.

Consertado em 29/08 com teste (`tests/test_envio_humano_modo2.py`), e a funcao
virou `_enviar_texto_saida`: o nome dizia Evolution e o caminho nao e mais so
dele.

**A licao que vale para a proxima:** achar um destes conserta **um** chamador,
nao a classe. Depois de corrigir um, `rg "get_whatsapp_outbound\(\)"` e olhe
todos — cada sobrevivente e um caminho que ignora o modo da loja em silencio.
