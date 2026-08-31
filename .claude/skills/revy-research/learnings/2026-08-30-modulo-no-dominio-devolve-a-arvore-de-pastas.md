---
gatilho: caixa de componente sai vazia, e as fichas aparecem numa caixa com nome de pasta
produto: .claude/skills/revy-research
custo: a arvore de pastas de volta no desenho que existia pra desfazer ela
fonte: repo
verificado_em: 2026-08-30
---
# O `modulo` no arquivo do domínio devolve a árvore de pastas

**Gatilho:** você escreveu a camada de componente de um produto, as caixas
estão certas — e no navegador elas aparecem **vazias**, com as fichas de
inventário empilhadas numa caixa automática cujo nome é uma **pasta**
(`web`, `control`, `clients`).

O `modulo` de um componente é um prefixo de caminho, e ele faz **uma** coisa:
decide quais entradas do `_frescor.json` se penduram naquela caixa
(`arq_modelo._designar_por_caminho`). Entrada que não casa prefixo nenhum cai
na raiz do produto — e a raiz agrupa por **diretório**. Então todo arquivo que
você deixou sem prefixo volta a aparecer, só que arrumado por pasta.

É por isso que o sintoma é traiçoeiro: o desenho *parece* certo no `arquitetura.py`
e os 80 testes passam. `TestProvaCabeNaCaixa` confere o termo, não o `modulo`.

**A escolha.** Quando o domínio mora num arquivo e a rota noutro — o caso normal
da Revy Loja, onde `financeiro` é `app/loja/financeiro.py` +
`app/web/loja_financeiro.py` + `app/financeiro_calc.py` — aponte o `modulo` pro
arquivo que **tem entrada de inventário**, que quase sempre é o da rota. O
extrator só emite rota/worker/modelo/flag/migration/template: um módulo de
cálculo puro não gera entrada nenhuma, e um `modulo` apontado pra ele deixa a
caixa vazia sem avisar.

A prova de existência do componente não se perde nisso: ela mora no `termo`, com
`arquivo:linha`, e continua podendo apontar o arquivo do domínio.

**Onde isso não vale:** quando o domínio tem worker próprio. Na Revy Loja o
`copiloto` aponta `app/copiloto_`, que pega os três jobs (regras, retenção,
turnos) — worker é comportamento em produção e vale mais que a única ficha de
template da rota.

**Como ver.** Só no navegador, e só com o recorte: `python3 recorte_produto.py
<produto>` e abra pelo `http.server`. A caixa automática com nome de pasta é
visível de longe; no `arquitetura.py` ela não existe.

Ver também `[[2026-08-30-getcomputedstyle-le-o-meio-da-transicao]]`.
