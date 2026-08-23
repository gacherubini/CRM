---
gatilho: propor, planejar ou "implementar" uma feature que voce ainda nao viu no codigo
produto: todos
fonte: repo
verificado_em: 2026-08-23
custo: um plano inteiro para reconstruir um modulo pronto e commitado
---
# Antes de propor feature nova, confira se ela ja existe

No ensaio cego de 23/08 o pedido foi "a Loja precisa mostrar o lucro de cada moto
vendida; hoje o Financeiro so mostra o total do mes". O agente comecou a esbocar
`VendaCusto`, migration nova, rota nova, template novo.

Estava tudo pronto havia uma semana, em `0dc9318`:
`portal-gestao/app/loja/financeiro.py:109` ja tem `LinhaVenda(... custo, lucro)`,
e `app/templates/loja/financeiro_resultado.html:136` ja renderiza o painel por
moto. O que o dono descrevia era a tela **legada** `/app/financeiro`.

A feature nao aparecia porque estava **atras de flag e de entitlement**, entao o
dono nao a via na propria conta. "Nao vejo na tela" nao e evidencia de que nao
existe — e a Loja tem gate quadruplo (sessao, flag, modulo contratado, papel).

## A receita, em ordem de custo

1. `grep -i "<assunto>" mapa/<produto>.md` — o mapa inteiro tem ~330 linhas, e
   este grep custa segundos.
2. `README.md` do produto, bloco **"O que ja funciona"**.
3. `git log --oneline -5 -- <pasta suspeita>/`.

Só depois disso escreva plano.

## Por que quase falhou mesmo com o mapa

O que salvou foi a secao **Templates** do mapa. A secao **Rotas** do mesmo
arquivo dizia que o modulo nao tinha rota nenhuma — o gerador era cego a path em
variavel, e `loja_financeiro.py` usa `@router.get(_PAGINA)`. O mapa se
contradisse e o acerto veio por sorte de ler a metade certa.

A cegueira foi consertada no mesmo dia (`0c82fb4`), e path que o gerador nao
consegue ler passou a virar aviso explicito. Mas a licao sobrevive ao conserto:
**ausencia num mapa nunca prova ausencia no codigo.** O `--verificar` so reabre o
que esta escrito no mapa; o que ficou de fora ele nao ve.

Ver [[2026-08-23-teste-verde-nao-prova-que-a-feature-existe]] e
[[2026-08-23-flags-de-rollout-sao-secrets]].
