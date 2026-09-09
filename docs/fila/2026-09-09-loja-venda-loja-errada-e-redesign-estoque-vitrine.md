# Loja: venda na loja errada + redesign Estoque e Vitrine

**Produto:** portal-gestao (Revy Loja) · **Origem:** conversa com o dono em 09/09/2026
(com prints da loja `teste` e da `moto-center`).

Nove tarefas no mesmo produto, sem importar `app` de outro. A correção do bug
inclui leitura e escrita de vendas na Loja. As demais tarefas tratam da UI;
sem mudanças em Control, Chatbot, Motor, n8n ou migrations.

**Entrevista (09/09):** dono autorizou corrigir o bug (Q1), aceitou reorganizar
a hierarquia e recolher detalhes preservando informações e ações (Q2), e
pediu propostas visuais do agente com `mattpocock-skills:prototype` (Q3).
Cada escolha visual continua pendente até ele comparar os protótipos.

## Global constraints

- **Só `portal-gestao`.** Integração entre produtos só por HTTP versionado.
- Mudança de UI da Loja: respeitar as 13 recusas
  (`decisoes/2026-08-07-treze-recusas-de-ux.md`) — em especial a `L5`: o aside
  "Veículos" da visão do Estoque **fica**, não sai como "duplicação".
- Skill `taste` vale como filtro negativo (sem gradiente roxo, sem bento para
  tudo, sem glassmorphism, sem emoji como ícone). Pedido do dono vence o filtro.
- **Entrevista de design com opções visuais.** Decisão do dono (09/09): usar
  `mattpocock-skills:prototype` antes de perguntar sobre escolhas de design.
  O agente prepara três alternativas de estrutura na tela existente, com
  `?variant=` e seletor flutuante, para o dono comparar e escolher ou combinar.
  Preservar o shell da Loja; ações do protótipo usam simulação sem gravação.
  O dono avalia as opções, não precisa fornecer o protótipo. A implementação
  definitiva de cada tela depende da escolha visual; preservar as direções
  já aprovadas neste card.
- Item novo de menu exigiria `page_title` + ícone em `loja_icons`
  (`tests/test_loja_navigation.py`). Aqui não há item novo.
- Testes a partir da pasta do produto: `.venv/bin/python -m pytest -q` (macOS),
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows).
- `git diff --check` e `git status --short` antes de dizer que acabou. Não
  commitar mudança alheia.

## Task 1 — bug: venda de outra loja aparece na loja `teste`

**Sintoma:** logado na loja `teste` (seletor mostra `teste`), a lista em
`/app/loja/vendas` exibe "primeira venda … bielcheeeeee@gmail.com", que é venda
de outra loja.

**Hipótese com `arquivo:linha` (confirmar contra o banco antes de corrigir):**
a lista do shell filtra pela coluna legada, não pela loja da sessão —

- `app/web/loja_vendas.py:204` — `loja_vendas_lista` filtra
  `Venda.loja_slug == usuario.loja_slug`;
- `app/web/loja_shell.py:405` — `loja_selecionar` grava a troca em
  `request.session["loja_slug"]` (`identity.SESSION_LOJA_KEY`);
- `app/auth.py:33` — `usuario_atual` devolve o `Usuario` do banco; o
  `.loja_slug` dele é a loja de origem, não a selecionada.

Ou seja: o seletor e o cabeçalho mostram a loja da **sessão**, mas a consulta
lê a loja **legada**. É o mesmo split-brain do learning
`2026-08-24-seletor-e-rota-leem-fontes-diferentes` (seletor × POST), agora entre
sessão × consulta. As rotas legadas em `app/main.py` (~:1543, :1724, :1796,
:1831, :2036) e `app/loja/sales_overview.py` (via `loja_slug=usuario.loja_slug`)
têm o mesmo padrão — levantar todas as ocorrências no fix.

**Antes de corrigir, decidir qual lado está errado** (expandir só se confirmado):

1. Se a `venda.loja_slug` está certa e a query lê a loja errada → a consulta
   passa a resolver a loja ativa pela sessão
   (`identity.session_loja_slug` + `resolve_store_context`), com fallback para
   `usuario.loja_slug`.
2. Se a venda foi **gravada** com `loja_slug` errado (criada na loja A com slug
   da B) → o fix é na escrita (`POST /app/vendas/nova`, `main.py:1587` e
   vizinhas), não na leitura.

**Não faça:** ler tabela de outro produto por SQL; trocar o filtro por algo
fora da sessão sem validar membership (porta dos fundos para loja alheia);
mexer no `SESSION_LOJA_KEY`.

**Teste:** reproduzir com dois slugs (usuário com `loja_slug=A`, sessão=`B`):
a lista mostra só vendas de `B`. Rodar `tests/test_loja_vendas*.py` (o que
existir) + navegação.

## Task 2 — redesign: Situação do estoque

**Sintoma:** dono acha o design da página "horrível"
(`app/templates/loja/estoque_visao.html`, rota `app/web/loja_estoque.py`).

**Escopo:** só CSS + template. Nenhum número muda (Disponibilidade, Publicados,
Idade do estoque continuam vindos do cadastro). Manter `page_title`,
`eyebrow`, estados `erro`/`vazio`/`parcial`, e o aside "Veículos" (recusa `L5`).

**Não faça:** remover informação, reordenar por conta própria o que o dono não
pediu, reabrir `:root` em `app.css` (tokens têm fonte única).

**Feedback do dono (09/09, pós-preview):** a v1 do redesign (hero
"Disponíveis" + faixa secundária + idade em barras) continua **feia**.
Voltar com nova direção visual antes de considerar a Task 2 feita.

**v2 (09/09, aguardando preview do dono):** protótipo B lado a lado no runner
(`portal-gestao/prototype_atendimento.py`, `/app/loja/estoque/demo?variant=B`;
A segue na v1). Direção "balanço": razão em linhas com régua em vez de hero,
idade em barra única empilhada com legenda em vez de 4 barras. Mesma ordem,
mesmos números e ações; template novo em
`app/templates/loja/prototype_estoque_B.html`, CSS só com tokens existentes.

**v3 (09/09, dono escolheu C):** direção "pátio" implementada como definitiva
em `estoque_visao.html` (manifesto serif + barra de proporção + idade em
índice sem barras). Extras do dono: botões do cabeçalho lado a lado até no
mobile (`.heading-actions.keep-row`), travessão do subtítulo removido.
Protótipos B/C e `?variant=` aposentados (o runner rende o template real com
dados fictícios); CSS do B removido do `app.css`.

## Task 3 — redesign: Vitrine (config compacta, catálogo protagonista)

**Pedido do dono:** a seção "Catálogo e vitrine" (WhatsApp CTA + link) tem de
ser bem menor; o principal da página é o catálogo público
(`app/templates/loja/vitrine_ordem.html`).

**Direção aprovada na conversa:** config vira `<details>` recolhido por padrão
(uma linha: título + estado atual — nº WhatsApp ou "sem botão de contato",
"bot envia link" ou "bot sem link"), grade do catálogo sobe para protagonista.
Mesmo `action` (`/app/loja/whatsapp/catalogo`), mesmos `name`s, mesmo CSRF;
campos lado a lado via `.form-grid` existente e Salvar alinhado à direita via
`.form-actions` (o botão estica hoje porque `.stack-form` é grid — sair dele
resolve sem CSS novo). CSS novo mínimo só para o `summary`.

**Não faça:** remover os campos (o bot depende deles); mudar endpoint ou nome
de campo; quebrar o JS de ordenação (`vitrine_ordem.js`, ids `vitrine-*`).

**Teste que amarra o texto** (`tests/test_loja_catalogo.py:63`): a página precisa
continuar contendo "Catálogo e vitrine" ou "Link do catálogo" — o `summary` e o
`label` mantêm as duas strings.

**Implementado (09/09):** grade do catálogo protagonista no topo, config em
`<details>` recolhido com tira de estado (`botão <nº>`/`sem botão de contato`
· `bot envia link`/`bot sem link`; abre sozinho com erro/mensagem), campos em
`.form-grid`, Salvar em `.form-actions`, CSS novo só para o `summary`.
Preview no runner: `/app/loja/vitrine/demo` (template real, dados fictícios).

## Task 4 — simplificar/embelezar: Atendimento (workspace da conversa)

**Pedido do dono:** a conversa do Atendimento está poluída; dá para deixar mais
bonita. Telas: lista (`app/templates/loja/atendimento_lista.html`) + workspace
(`app/templates/loja/atendimento_workspace.html`, rotas em `app/loja/routes.py`).

**Escopo:** só template + CSS. Nenhum comportamento muda (polling `after_id`,
handoff, envio humano, pausa do bot). O agente apresenta opções com
`mattpocock-skills:prototype`; esta task só implementa a direção visual
aprovada pelo dono.

**Não faça:** mexer no `get_human_messaging_port` sem `Request` (vazamento
multi-loja documentado no learning de 29/08); mudar texto que teste amarra
(conferir `tests/test_atendimento*.py` antes).

**Implementado (09/09, dono escolheu A):** trilho de contexto reordenado no
template real — Próximo passo, Interesse (+etapa), ficha em dois disclosures
(Dados do contato e origem; Responsável e bot) + links. Mesmos endpoints,
nomes, CSRF, hooks do JS e textos amarrados; CSS novo só para o `summary`
(mesmo vocabulário da Vitrine). Protótipos A/B/C aposentados (7 arquivos).
Preview no runner: `/app/loja/atendimento/demo-marina` (template real).
**Conversa (09/09, pedido do dono):** bolhas no vocabulário do protótipo —
saída em tinta da marca, entrada em cartão, fundo liso, meta com remetente
(`Cliente`/`Equipe`/nome do lead + horário). Só CSS + linha do `<small>`;
hooks do JS e textos amarrados intactos.

## Task 5 — embelezar: Agente do WhatsApp

**Pedido do dono:** a visão do Agente também pode ficar bonita.
Template `app/templates/loja/agente.html` (hero "Atendimentos no mês" :78,
"Atendimentos por dia" :126).

**Escopo:** só template + CSS. Números e janelas não mudam (atenção à recusa
`C17` — "Conversão" misturando janelas — que é do Control mas vale o espírito:
não inventar métrica nova). Direção escolhida pelo dono entre as opções
visuais preparadas pelo agente com `mattpocock-skills:prototype`.

## Task 6 — simplificar: Números de WhatsApp

**Pedido do dono:** página poluída; dá para ser mais simples.
Template `app/templates/loja/whatsapp_canais.html` (seções "Seus números" e
"Conectar o WhatsApp pela Revy"; fluxo Modo 2 em `app/web/loja_whatsapp.py`).

**Escopo:** só template + CSS. Fluxo de conexão (embedded signup, QR efêmero,
fila do Modo 2) e textos de segurança ("essa escolha não volta atrás") não
mudam. Direção escolhida pelo dono entre as opções visuais preparadas pelo
agente com `mattpocock-skills:prototype`.

**Não faça:** expor API key da Evolution; mudar rota ou campo do formulário;
prometer coexistência dos dois modos (recusa de 13/08: dois modos, sem
coexistência).

## Task 7 — simplificar: Resultado

**Pedido do dono:** página poluída; dá para ser mais simples.
Template `app/templates/loja/vendas_visao.html`, dados em
`app/loja/sales_overview.py` (via `app/web/loja_vendas.py:125`).

**Escopo:** só template + CSS. Nenhum número muda; estados vazios continuam
explicando em vez de zerar (learning `2026-08-23-zero-na-tela-pode-ser-projecao-vazia`).
Direção escolhida pelo dono entre as opções visuais preparadas pelo agente
com `mattpocock-skills:prototype`.

**Não faça:** ratear despesa fixa por venda (decisão de 16/08); estimar margem
sem custo (manter "indisponível"); tocar em `FAMILIA_ANUNCIO` sem espelhar no
`chatbot-api` (duplicação consciente).

## Task 8 — simplificar: Resultado financeiro

**Pedido do dono:** mesmo problema de poluição das demais telas.
Template `app/templates/loja/financeiro_resultado.html`, dados em
`app/loja/financeiro.py` + `app/web/loja_financeiro.py`.

**Escopo:** só template + CSS. DRE do mês, ponto de equilíbrio e regra de margem
parcial não mudam (decisão de 16/08). Direção escolhida pelo dono entre as
opções visuais preparadas pelo agente com `mattpocock-skills:prototype`.

**Não faça:** rateio de despesa fixa; margem estimada sem custo; expor custo,
lucro, tokens ou credenciais para vendedor (RBAC no backend, não no menu).

## Task 9 — simplificar: Despesas fixas

**Pedido do dono:** mesmo problema de poluição das demais telas.
Template `app/templates/loja/financeiro_despesas.html`, rotas em
`app/web/loja_financeiro.py` (despesas, ajuste, encerrar).

**Escopo:** só template + CSS. Recorrência, ajustes e encerramento não mudam.
Direção escolhida pelo dono entre as opções visuais preparadas pelo agente
com `mattpocock-skills:prototype`.

**Não faça:** mudar semântica de recorrência/ajuste; esconder ação por papel no
template em vez do backend.
