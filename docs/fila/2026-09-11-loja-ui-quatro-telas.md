# Loja — quatro telas que o dono reprovou em 11/09

Produto: **portal-gestao** (Revy Loja). Só UI: CSS, templates e um ponto de
diagnóstico de dados. Nenhuma rota, modelo ou migration muda.

Status: aberto em 11/09/2026, nada implementado. O dono viu as telas em produção
(`app2037`, sha `9eb58f2`) num monitor de 1920 e apontou quatro problemas.

## Global constraints

- Um `?v=` por entrega: mudou `app.css`, sobe `v42 → v43` nos **5** templates
  (`base.html`, `login.html`, `convite_aceitar.html`, `senha_esqueci.html`,
  `senha_redefinir.html`). Sem isso prod serve CSS velho.
- Teste do produto a partir de `portal-gestao/`:
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows) ou
  `.venv/bin/python -m pytest -q` (macOS). Hoje: 1462 passando.
- **Pytest não vê layout.** Confira no navegador: `python prototype_atendimento.py`
  (porta 8766) renderiza os templates reais com dados fictícios, sem banco.
  Rotas do preview: `/app/loja/estoque/veiculos/demo`,
  `/app/loja/financeiro/despesas/demo`, `/app/loja/financeiro/demo`,
  `/app/loja/vendas/editar/demo`.
- Não re-proponha os 13 itens recusados em 07/08
  (`.claude/skills/revy-research/decisoes/2026-08-07-treze-recusas-de-ux.md`).
  Encosta aqui: **L20** (filtro "só pendências" na lista de veículos) e **L5**
  (o aside "Veículos" fica onde está).
- Não devolva teto de leitura ao `.content` da Loja
  (`decisoes/2026-09-11-shell-da-loja-enche-a-tela.md`): a largura é para encher.
- Responsivo nas duas pontas: 390px e 1920px, sem rolagem horizontal da página.

## Task 1 — Veículos: foto grande e linha inteira clicável

Tela: `/app/loja/estoque/veiculos`. Template `app/templates/estoque/lista.html:45-66`.
CSS: `.vei-ficha` `app.css:4784` (grid `112px minmax(0,1fr) auto`),
`.vei-foto` `app.css:4794` (112×76), `.vehicle-photo` `app.css:610` (54×44, caixa
com a inicial da marca quando não há foto), `.vei-lado` `app.css:4817`,
`.vei-preco` `4823`, `.vei-custo` `4830`.

O que o dono pediu:

1. **Foto maior.** Hoje a miniatura é 112×76 numa linha que agora tem 1688px de
   largura. Ela some na página.
2. **Foto que não aparece direito.** No print de prod, duas linhas mostram a
   inicial ("h", "H") e uma mostra o ícone de imagem quebrada — ou seja, há
   `foto_url` que **404**, não só miniatura pequena. **Diagnostique antes de
   estilizar**: o template monta
   `src="{{ v.foto_url }}?w=240"` só quando `'/public/v1/media/' in v.foto_url`
   (`lista.html:49`); `foto_url` vem do estoque-api pelo cliente
   (`app/clients/estoque.py`, sem tratamento de mídia). Descubra se a URL quebrada
   é caminho relativo, host errado ou mídia apagada. Se for dado, conserte o dado
   — não esconda com CSS.
3. **Card da direita "meio estranho".** `.vei-lado` empilha preço, "custo —" e o
   link Abrir alinhados à direita; com a linha larga o bloco fica solto.
4. **A linha inteira abre o veículo.** Clicar no título, na foto ou na linha deve
   abrir. O `<a class="table-action">Abrir</a>` (`lista.html:62`) sai. Mantenha
   alvo de teclado e foco visível: o padrão mais simples é o título virar o link
   real e a linha inteira ganhar o clique (ou `::after` esticado sobre a ficha),
   nunca um `onclick` que quebre o Tab.

Feito quando: as 4 telas do preview e a lista real abrem por clique em qualquer
ponto da linha, foto legível em 1920, `Tab` ainda percorre os veículos.

## Task 2 — Despesas fixas: vazio sem ícone, texto grande na fonte da marca

Tela: `/app/loja/financeiro/despesas`. Template
`app/templates/loja/financeiro_despesas.html:50-54` (bloco `.empty`).

O ícone é `.empty::before` (`app.css:2404-2411`): um quadrado de 40px com máscara
SVG de caixa de entrada pintada de `var(--brand)`. O dono quer ele **fora** e o
texto **grande, na fonte de design** — `var(--font-brand)` (Newsreader, definida em
`static/css/revy-tokens.css:57`), a mesma dos números grandes de
`.res-lede`/`.estc-lede`.

**Armadilha de alcance:** `.empty` é compartilhada. O mesmo ícone aparece no
Editar venda ("Nenhum custo direto lançado", Task 4) e em outras telas. Decida e
escreva no commit: ou o vazio vira um componente novo só para estes casos, ou o
`.empty` inteiro perde o ícone — e aí reveja todas as telas que o usam antes.

Feito quando: o vazio das Despesas é só a frase, grande, sem ícone, e nenhuma
outra tela ficou com vazio quebrado.

## Task 3 — Resultado financeiro: a caixa não estica

Tela: `/app/loja/financeiro`. Template `app/templates/loja/financeiro_resultado.html:43-62`.

Causa conhecida, **não procure outra**: em 11/09 (commit `9eb58f2`) `.res-index`
ganhou `max-width: 64rem` (`app.css:4586`) para o valor não ficar a mil pixels do
rótulo. O efeito colateral é o que o dono viu: dentro de um painel de 1688px, as
linhas "Custo das motos / Custos diretos / Lucro bruto" param em 1024px e o painel
parece cortado.

Resolva os dois de uma vez, sem voltar ao estado anterior: a linha precisa encher
o painel **e** manter rótulo e número perto. Caminhos a considerar (o card não
decide): colunas de largura fixa em vez de `space-between`; a régua de leitura
virar padding do painel; ou o painel "Como o mês fechou" ganhar duas colunas acima
de 1440px, que é a reorganização que o dono já disse ser o passo seguinte.

**As duas telas têm o defeito, não só o Financeiro.** Em `/app/loja/vendas`
(Resultado), com venda no período, cortam no mesmo 1024px: "Margem (lucro bruto)"
no painel *Receita e vendas*, e "Investimento" / "CAC" no painel *Investimento e
retorno* (`app/templates/loja/vendas_visao.html:51` e `:129`). O contraste fica
pior porque o painel do meio, *Leads e conversão*, usa `.res-flow`
(`app.css:4602`) e **enche** a largura: dois painéis largos com um cortado no meio.
Vale também para o bloco `Estrutura` do Resultado financeiro.

Feito quando: em 1920 o conteúdo do painel vai até a borda interna dele nas duas
telas, com e sem venda no período, e em 390 nada empilha errado.

## Task 4 — Editar venda: redesenhar

Tela: `/app/loja/vendas/<id>/editar`. Template `app/templates/loja/venda_editar.html`.
CSS: `.vnd-corpo` `app.css:5040` (duas colunas `1.15fr / .85fr`), `.vnd-custos`
`5061`, `.vnd-custo-novo` `5095`, `.vnd-form-acoes` `5051`.

O dono chamou de "muito feia". O que dá para ver no print, para guiar o redesenho:

- **UUID cru na cara do usuário**: "Lead: 10071317-407c-… · Veículo: 975fab47-…"
  (`venda_editar.html`, bloco abaixo dos campos). Ninguém lê isso. Mostre nome do
  lead e o veículo por marca/modelo, com o id em `title`/`details` se precisar.
- Dois campos curtos (Preço de venda, Custo do veículo) sozinhos num painel que
  ocupa 60% da largura.
- `Cancelar` / `Salvar alterações` flutuam entre as duas colunas, longe do que
  editam.
- Coluna da direita: vazio com o mesmo ícone da Task 2, e logo abaixo o
  disclosure "Lançar custo" já aberto com categoria, valor e botão — dois pesos
  na mesma coluna.
- O painel "Apagar esta venda" é um bloco de texto corrido de três parágrafos.

Constraints de produto: o vínculo lead↔veículo é fixo depois da confirmação e a
edição reenvia o resultado ao Control — o texto pode encolher, o comportamento
não muda. Cancelar venda continua com motivo obrigatório (é histórico); apagar
continua separado e explicado.

Feito quando: a tela cabe numa olhada, sem UUID visível, com as ações junto do que
editam, e a suíte segue verde.

## Ordem sugerida

3 → 2 → 1 → 4. A Task 3 é a regressão do dia e a mais barata; a 4 é a única que
pede desenho de verdade e merece o card inteiro para ela.
