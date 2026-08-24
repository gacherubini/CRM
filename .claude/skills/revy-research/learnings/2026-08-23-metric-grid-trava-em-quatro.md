---
gatilho: acrescentar metrica numa tela da Loja ou do Control
produto: portal-gestao
fonte: repo
verificado_em: 2026-08-24
---
# `.metric-grid` e grid fixo de 4 colunas, sem separacao entre linhas

`.metric-grid` (`portal-gestao/app/static/css/app.css`) e
`grid-template-columns: repeat(4, 1fr)` **sem row-gap**, e `.metric` usa `border-right`
entre colunas. Com 5 ou mais metricas numa grade so, a quinta cai embaixo da primeira e le
como continuacao do mesmo card. Aconteceu na primeira versao da tela Resultado financeiro
(16/08/2026), com as 6 metricas da DRE. So aparece no navegador — pytest renderiza o HTML
e nao sabe nada de layout.

Maximo **4 metricas por grade**. Precisa de mais? grade nova (ou painel novo), nunca mais
um item. Ha um teste guardando isso em
`tests/test_loja_financeiro_gate.py::test_nenhuma_grade_de_metricas_passa_de_quatro`;
vale replicar se outra tela crescer.
