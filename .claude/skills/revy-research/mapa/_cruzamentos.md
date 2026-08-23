# Cruzamentos entre produtos

**Tudo aqui e SUSPEITA, nao erro.** Chamada por string montada, dispatch
dinamico, prefixo de router e funcao consumida so por template geram
falso positivo. Regra: suspeita nao vira commit, vira pergunta.

NAO editar a mao — saida de `gerar_mapa.py`.

## Rotas chamadas por cliente HTTP sem servidor declarado

Casamento de path INTEIRO normalizado, nunca de prefixo.
Duas causas conhecidas de falso positivo aqui: segmento montado em
runtime (`f"/v1/veiculos/{id}/{acao}"`) e rota declarada num router
com `prefix=` que o mapa ainda nao aplica.

- `/v1/veiculos/{}/{}` chamado em `chatbot-api/app/inventory.py` — `estoque-api` nao declara
- `/v1/veiculos/{}/{}` chamado em `portal-gestao/app/clients/estoque.py` — `estoque-api` nao declara
- `/v1/lojas/{}/eventos/venda-atualizada` chamado em `portal-gestao/app/clients/revy_trafego.py` — `revy-trafego` nao declara
- `/v1/lojas/{}/eventos/venda-confirmada` chamado em `portal-gestao/app/clients/revy_trafego.py` — `revy-trafego` nao declara
- `/v1/lojas/{}/integracoes/health` chamado em `portal-gestao/app/clients/revy_trafego.py` — `revy-trafego` nao declara
- `/v1/lojas/{}/resultados` chamado em `portal-gestao/app/clients/revy_trafego.py` — `revy-trafego` nao declara

## Funcoes publicas sem nenhum chamador

Funcao de modulo, publica, SEM decorator e sem nenhuma mencao ao
nome em nenhum produto (import conta como mencao). Handler de rota
nao entra: quem chama e o framework.

- `enfileirar_purchase_venda` — portal-gestao/app/meta_capi.py:118
- `pixel_id_valido` — portal-gestao/app/meta_pixel.py:16
- `pode_escrever_operacional` — portal-gestao/app/loja/permissions.py:68
- `require_roles` — portal-gestao/app/loja/permissions.py:58
- `atualizar_whatsapp_loja` — estoque-api/app/servico.py:1077
- `as_tuple` — revy-trafego/app/clients/meta_graph.py:117
- `chatbot_poster` — revy-trafego/app/control/provisioning_outbox.py:193
- `enfileirar_purchase_venda` — revy-trafego/app/meta_capi.py:126
- `pixel_id_valido` — revy-trafego/app/meta_pixel.py:16

## n8n x chatbot

| Arquivo | Nome | Webhook | No ar |
|---|---|---|---|
| `workflow-ai-nao-salvos.json` | WhatsApp IA - Somente Nao Salvos | `whatsapp-ai` | SIM |
| `workflow-cloud.json` | whatsapp-cloud | `whatsapp-cloud` | SIM |
| `workflow-teste-numero-autorizado.json` | WhatsApp IA - TESTE 5551980336365 | `whatsapp-ai-teste` | nao |

Fora da tabela PUBLICADOS em `cruzamentos.py` (nao conferidos): `workflow-teste-numero-autorizado.json`. Se algum entrou no ar, acrescente — senao a checagem abaixo o ignora.

Rotas chamadas pelos workflows **no ar**:

Todas as 6 estao declaradas no chatbot:

- `/v1/conversas/{}/pode-responder`
- `/v1/operacao/responder`
- `/v1/operacao/roteamento`
- `/webhook/cloud`
- `/webhook/mensagem`
- `/webhook/operacao/veiculos/foto`

## fly.toml no repo

So a lista: qual arquivo aponta para qual app. Quais desses apps
ainda existem e conhecimento humano que muda com o tempo — ver
`AGENTS.md` secao 5. Deploy so por `deploy/fly/3vm/`.

- `catalogo-publico/fly.toml` -> `catalogo2037`
- `chatbot-api/fly.toml` -> `chatbot2037`
- `deploy/fly/evolution/fly.toml` -> `evolution2037`
- `deploy/fly/n8n/fly.toml` -> `n8n2037`
- `estoque-api/fly.toml` -> `estoque2037`
- `motor-simulacao/fly.toml` -> `motor2037`
- `portal-gestao/fly.toml` -> `portal2037`
