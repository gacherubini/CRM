---
decidido: 2026-09-11
nao_reproponha: travar o conteudo da Loja numa largura de leitura (76rem e afins)
---
# O shell da Loja acompanha a janela

Em 11/09/2026 o `.content` do shell da Loja estava em `max-width: 76rem` (1216px),
posto no mesmo dia pelo commit `bfab10c` com a justificativa "em tela cheia o conteudo
nao estica ate a borda". O dono abriu a Loja num monitor de 1920, viu quase metade da
tela vazia a direita e recusou: **"tudo tem que ser responsivo"**.

Decisao: o conteudo **enche a largura** e so para em `110rem` (1760px). Em 1920 a area
util e ~1688px, entao na pratica ele enche a tela; o teto existe para ultrawide, onde
uma linha de tabela de 2300px fica ilegivel. Continua alinhado a esquerda, junto da
sidebar.

O dono escolheu isto sabendo da alternativa mais cara (reorganizar cada tela em duas
colunas acima de 1440px). Essa alternativa **nao foi descartada**: ficou como passo
seguinte, tela a tela, e o Resultado e o caso mais claro. Reorganizar em colunas com o
conteudo travado em 1216px nao adiantaria nada, e por isso a largura veio primeiro.

Ao mexer no shell:

- Nao devolva um teto de leitura ao `.content` da Loja. Teto de medida vai no
  componente que precisa dele (ex.: `.res-index`, rotulo de um lado e numero do outro),
  nunca na pagina inteira.
- O Control (`revy-trafego`) nunca teve esse teto. Nao o acrescente por simetria.
