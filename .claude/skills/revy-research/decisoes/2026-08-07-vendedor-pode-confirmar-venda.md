---
decidido: 2026-08-07
nao_reproponha: restringir a confirmacao de venda a dono e gerente
---
# O vendedor deve poder confirmar a venda, nao so registrar

Decisao de produto do dono: o vendedor lanca a venda dentro do Revy Loja e isso dispara
sozinho a cascata inteira (projecao no Control e Purchase na Meta).

Quando a decisao foi tomada, `pode_registrar_venda` ja aceitava dono/gerente/vendedor, mas
`pode_confirmar_venda` era so dono/gerente — o vendedor criava um rascunho `registrada` e
parava ali. E a confirmacao (`POST /app/vendas/{id}/confirmar`) que dispara snapshot de
atribuicao, baixa no estoque, evento de funil e o outbox para o Control.

O motivo: atraso na confirmacao atrasa o sinal de otimizacao do anuncio na Meta. A venda
tem que entrar onde o vendedor ja trabalha, sem depender de gestao.

Nao proponha o contrario "por seguranca". Se for implementar, e mudar `pode_confirmar_venda`
para incluir `vendedor` e levar registrar + confirmar para dentro do shell da Loja.
