---
gatilho: ligar o Modo 2 numa loja ou cadastrar o canal Cloud dela
produto: chatbot-api
fonte: repo
verificado_em: 2026-08-23
---
# Canal Cloud não se cadastra pela API — e o Modo 2 tem três flags, não uma

## O buraco

`POST /v1/whatsapp/canais` **não consegue criar um canal Cloud**. O schema de entrada
(`chatbot-api/app/main.py`, `CanalWhatsAppInput`) aceita só `evolution_instance` e
`e164_or_label`; `channels.register_channel` (`chatbot-api/app/channels.py:158`) nunca grava
`waba_id` nem `template_oferta`. Mas `cloud_canal.canal_cloud_da_loja`
(`chatbot-api/app/cloud_canal.py:53`) **só reconhece um canal como Cloud se `waba_id` estiver
preenchido**. As duas colunas existem no modelo (`models_db.py:75-79`) e não há caminho HTTP
até elas.

Qualquer doc que mande fazer `POST /v1/whatsapp/canais` com `waba_id` está descrevendo um
campo que não existe. Hoje só dá por escrita direta no banco.

## Por que isso não bloqueia o piloto

Um canal **sem** `waba_id` já resolve o ciclo no número de teste, porque os dois lados se
resolvem por caminhos diferentes:

- **inbound** — `_loja_por_phone_number_id` (`main.py:617`) casa o `phone_number_id` com a
  coluna `evolution_instance`. É só disso que ele precisa; é o que cura o
  `phone_number_id sem loja`.
- **outbound** — sem canal Cloud, `credenciais_cloud_da_loja` (`cloud_canal.py:64`) cai no
  ambiente campo a campo: `CHATBOT_GRAPH_PHONE_NUMBER_ID` e `CHATBOT_GRAPH_TEMPLATE_OFERTA`
  (cujo default no código já é `chama_vendedor`).

O buraco morde na **primeira loja real**: template é recurso da WABA, então cada loja precisa
da WABA e do template dela gravados — o passo 5 do §16.6, o custo manual que o embedded
signup elimina.

## São três flags, não uma

Ligar só a do Control troca o modo na tela e deixa o rodízio morto.

| Flag | Produto | Sem ela |
|---|---|---|
| `REVY_CONTROL_WHATSAPP_MODO2_ENABLED` | revy-trafego | o rádio do Modo 2 nem é desenhado (`loja_detail.html:140`) e `stores.py:269` recusa salvar |
| `CHATBOT_WHATSAPP_MODO2_ENABLED` | chatbot-api | rodízio (`rodizio.py:68`) e workers (`modo2_workers.py:95`) não rodam |
| `MULTI_WHATSAPP_ENABLED` | chatbot-api | `POST /v1/whatsapp/canais` responde **404** |

No `app2037` as três são **secrets**, e em 23/08 todas ficaram em `1` — as duas do chatbot já
estavam, o que se descobriu pelo digest: `fly secrets list` mostra digest, e **valor igual dá
digest igual**. Setar a que faltava com o valor esperado e ver o digest bater com o das
outras prova o valor delas sem nunca imprimir segredo. Ver [[2026-08-23-flags-de-rollout-sao-secrets]].
