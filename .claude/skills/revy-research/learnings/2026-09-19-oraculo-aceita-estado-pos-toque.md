---
gatilho: oráculo e2e que consulta estado que humano muda
produto: chatbot-api
custo: um run e2e vermelho no T8 com jornada perfeita (oferta entregue e assumida em 8s)
fonte: repo
verificado_em: 2026-09-19
---
# Oráculo que sonda estado mutável por humano aceita o estado pós-toque

Em 19/09 o T8-oferta do loop e2e consultava só `estado=aberta`. O dono tocou
em Peguei 8s depois de a oferta nascer, 1s antes da consulta: o filtro voltou
`[]` e o run ficou vermelho com entrega + aceite perfeitos (criada 04:29:43,
travada 04:29:51, consulta 04:29:52).

Receita (`e2e-loop/cenarios.sh`, T8): sondar `aberta`; se vazio, sondar
`travada` ANTES de qualquer veredito — travada prova entrega + aceite e pula
ao reset de fim. E sondar sem emitir veredito parcial: um FALHOU da primeira
sonda ficaria no placar mesmo com a segunda verde.
