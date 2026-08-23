---
decidido: 2026-08-23
nao_reproponha: separar a revy-research em quatro skills (implementar / feature / debug / research)
---
# Uma skill so, nao quatro

A ideia de quebrar a `revy-research` em quatro skills (uma para implementar, uma para
feature, uma para debug, uma para pesquisa) foi recusada no desenho.

O motivo e mecanico: as quatro descricoes competiriam pelo **mesmo gatilho** — todas
comecam em "o dono quer mexer em algum produto do monorepo". Descricao que se sobrepoe faz
o modelo escolher errado ou carregar duas, e o custo de contexto dobra sem nenhum ganho de
precisao.

O contexto do monorepo e um so. O que muda depois dele e o **destino do roteamento**, nao a
porta.
