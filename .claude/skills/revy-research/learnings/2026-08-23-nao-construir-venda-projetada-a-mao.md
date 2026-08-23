---
gatilho: testar projecao de venda no Control
produto: revy-trafego
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# Exercite `projetar_venda()`, nunca construa `VendaProjetada` a mao

`revy-trafego/app/vendas_projection.py` gravava `loja_slug` e nunca preenchia `loja_id`.
O dashboard do Control filtra por `loja_id`, entao a Visao Geral mostrava Vendas do mes =
0 com vendas confirmadas chegando. **Ja esta corrigido** (commit `e2ae018`, verificado em
16/08/2026): `projetar_venda` chama `_loja_id_do_slug()` so quando `loja_id` vem `None` —
uma query a menos por evento e cura retroativa das vendas orfas. Nao reabra como bug.

A licao que fica e por que o bug escapou: o teste construia `VendaProjetada` a mao,
passando `loja_id=` no construtor, e validava a query. Ele testava o modelo, nao o
contrato. Qualquer teste de projecao de venda tem que entrar por `projetar_venda()`.
