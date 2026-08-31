---
name: revy-research
description: Use antes de codar, corrigir, implementar, debugar ou propor qualquer coisa em qualquer produto do monorepo Revy (chatbot-api, portal-gestao, motor-simulacao, estoque-api, revy-trafego, catalogo-publico). Entrega arquivo:linha de rota, modelo, worker, migration, flag e template, as armadilhas ja conhecidas e as decisoes do dono que nao devem ser re-propostas.
---

# revy-research

694 arquivos `.py` nos seis produtos, dentro de uma arvore de 10.288: 93% do que
uma busca as cegas devolve e codigo-fonte dos cinco `.venv`. Esta skill e **porta, nao caminho** — da o
contexto que so ela tem e entrega para quem ja sabe o resto. Nao improvise
protocolo de implementar, propor ou depurar.

## 1. Tronco — sempre, antes de qualquer coisa

1. **Um produto, dos seis.** Cruzou dois? PARE e diga ao dono: entre produtos so
   ha HTTP versionado.
2. **Frescor:** `python gerar_mapa.py --frescor <produto>` (no Mac, `python3`).
   `mapa em dia`: siga calado. Listou arquivos: diga quantos e ofereca regerar.
3. **Abra `mapa/<produto>.md`**, nunca `main.py` inteiro (o do portal tem 2.609
   linhas): `arquivo:linha` de rota, modelo, worker, migration, flag e template,
   mais o comando de teste nos dois SOs.
4. **Leia `learnings/INDEX.md` e `decisoes/INDEX.md`;** abra so os que batem —
   normalmente zero, um ou dois. As decisoes sao lidas **aqui**, antes de rotear:
   depois, a skill destino ja comecou cega e re-poe o que o dono recusou.

## 2. Briefing

Empacote no formato de `docs/referencia-viva/agents/task-brief.md`: produto,
arquivos com linha, invariantes, learnings que batem, decisoes que restringem,
comando de teste nos dois SOs. Roteamento sem briefing e so um "va para la".

## 3. Roteamento

| O que o dono quer | Va para |
|---|---|
| construir algo novo, desenhar, decidir rumo | `superpowers:brainstorming` |
| bug, teste vermelho, comportamento estranho | `superpowers:systematic-debugging` |
| implementar feature ou correcao | `superpowers:test-driven-development` |
| ja tem spec, quer plano | `superpowers:writing-plans` |
| ja tem plano, quer executar | `superpowers:subagent-driven-development` |
| mudar UI da Loja/Control | `frontend-design` + as 13 recusas em `decisoes/` |
| achar que acabou | `superpowers:verification-before-completion` |

Destino nao instalado? Siga o tronco e **avise**; nunca improvise o que faltou. O
fechamento mora no `AGENTS.md` §6 — a esta altura outra skill esta no comando.

## Regras

- **O mapa nao se edita a mao.** E saida de script: erro no mapa e erro no gerador.
- **`_cruzamentos.md` e suspeita, nao erro.** Suspeita nao vira commit, vira pergunta.
- **Julgamento nao mora aqui.** Armadilha de arquitetura e "nao mexa aqui" sao do
  `README.md` do produto. O mapa aponta; nao copia.
- **Poda.** Learning sem `gatilho` ninguem acha. Ja ha um do mesmo gatilho? edite o
  existente. Seguiu um e ele nao e mais verdade? apague arquivo e linha do indice
  no mesmo commit. Passou de ~40? avise: indice de 200 linhas mata o passo 4.
- **Nao edite este `SKILL.md`.** Protocolo errado vira uma linha em `propostas.md`.
  Ele carrega em todo disparo: derivando sozinho vira 400 linhas que ninguem revisou.
- **Nao re-proponha:** separar isto em quatro skills, nem escrever protocolo proprio
  de implementar/propor/depurar. Recusado em 23/08.

Como tudo isto funciona, para humano: `como-funciona.html`.

## A pagina de arquitetura

`arquitetura.html` (gerado, commitado) tem duas cenas navegaveis por zoom:

- **Arquitetura** — produto, componente e as arestas entre eles. A intencao vem
  de `arquitetura.py`, escrito A MAO; o inventario (`worker`, `flag`) vem do
  `_frescor.json`. `rota` e `template` sao DISPENSADAS de proposito — parede de
  ficha responde "quais arquivos existem", que nao e a pergunta desta pagina.
- **Schema** — mapa conceitual de banco: uma caixa por tabela, os atributos
  dentro, e uma seta por chave estrangeira rotulada com a cardinalidade
  (`n:1`, `1:1`, `n:0..1`), lida do proprio SQLAlchemy.

O as-built, com o porque de cada decisao e o que ainda esta aberto:
`docs/referencia-viva/specs/2026-08-30-arquitetura-viva-design.md` (secao 14).

**Conferir no navegador nao e opcional** — sete defeitos desta pagina so
apareceram abrindo ela, e dois nao deixavam rastro no console. A extensao de
navegador bloqueia `file://`, entao sirva por HTTP:

    python3 -m http.server 8899
    python3 recorte_produto.py chatbot-api          # o interior de um produto
    python3 recorte_produto.py chatbot-api schema   # o mesmo na Schema

## Regerar

Windows usa `python`; o Mac do dono so tem `python3`. Vale para os dois comandos.

    cd .claude/skills/revy-research
    python gerar_mapa.py               # regera o mapa
    python gerar_mapa.py --verificar   # so confere; sai 1 se o mapa mentir
    python gerar_arquitetura.py             # regera arquitetura.html
    python gerar_arquitetura.py --verificar # so confere; sai 1 se estiver velho
