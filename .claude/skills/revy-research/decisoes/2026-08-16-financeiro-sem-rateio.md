---
decidido: 2026-08-16
nao_reproponha: rateio de despesa fixa no lucro por moto
---
# Despesa fixa nao entra no lucro de cada moto

O dono viu as tres opcoes lado a lado (sem rateio, rateio por quantidade, rateio
proporcional a receita) e escolheu **nao ratear**. O modelo tem dois niveis que nao se
misturam: por moto e **lucro bruto** (preco menos custo do veiculo menos custos diretos);
pelo mes e **lucro operacional** (lucro bruto menos despesa fixa). A ponte entre os dois e
o **ponto de equilibrio**, nao o rateio.

Ratear e custeio por absorcao: faria o lucro de uma moto depender de quantas outras foram
vendidas no mes e mudar retroativamente a cada venda nova, levando o lojista a recusar
negocio que era bom.

Nao e falta de implementacao — foi escolha do dono. Nao re-propor nem como opcao de
configuracao. Se aparecer "essa moto pagou a estrutura?", a resposta e ponto de equilibrio
(`app/loja/financeiro.py`). E manter a indisponibilidade honesta: margem parcial suprime
lucro operacional e ponto de equilibrio, cada um com motivo proprio, sem virar estimativa.
