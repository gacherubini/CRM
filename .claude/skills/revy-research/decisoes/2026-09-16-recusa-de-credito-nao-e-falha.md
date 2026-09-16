---
decidido: 2026-09-16
nao_reproponha: tratar simulação com todos os bancos recusando como `falhou`
---
# Recusa de crédito não é falha da simulação

Decisão do dono em 16/09/2026, ao revisar as simulações de produção: quando TODOS
os provedores terminam `rejeitada` (recusa de crédito, nenhum erro técnico), o
status da simulação é **`concluida`** — a consulta rodou até o fim e os bancos
disseram não. O Portal já mostra "Crédito recusado" por banco
(`portal-gestao/app/web/simulacoes.py:128`).

A alternativa de criar um status novo `rejeitada` no Motor foi considerada e
recusada: exigiria mudar o contrato `/v1/simulacoes` e o consumidor (Portal)
junto.

Limites da regra: recusa misturada com erro técnico continua `falhou`; recusa com
oferta de outro banco continua `parcial`. O dono da regra é `_status_geral` em
`motor-simulacao/app/processamento.py`.

Mesma família (decidida junto em 16/09): **captcha/rede/senha não são falha**. O
resultado `aguardando_intervencao` agora marca a tarefa como
`aguardando_intervencao` (não `falhou`) — o Portal monta o card do banco pelo
status da tarefa — e a tela mostra o veredito "Aguardando ação" (amarelo), não
"Falhou" (vermelho). Donos: `_status_de_resultados_tarefa`
(`motor-simulacao/app/processamento.py`), `STATUS_TERMINAIS_TAREFA`
(`app/fanout.py`) e `_cards_bancos_progresso`/`_grupos_resultados_por_banco`
(`portal-gestao/app/web/simulacoes.py`).
