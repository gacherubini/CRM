# A camada de componente nos quatro produtos que faltam

> **Status (2026-08-30): FEITO, os quatro.** Catálogo (7 caixas, 8 arestas),
> Motor (10 e 17), Control (10 e 16) e Loja (10 e 15). 80 testes verdes,
> `--verificar` em 0, os quatro conferidos no navegador. O que este card
> continua servindo pra explicar é o **método** — se for dar a mesma camada a
> um produto novo, a receita abaixo vale inteira. Código e testes vencem este
> bloco.
>
> Três coisas mudaram em relação ao que o card previa, e estão registradas
> onde importa:
> - o vocabulário de protocolo interno virou **quatro** palavras (`http`
>   entrou pro wake do Motor, que atravessa VM) — o porquê está na docstring
>   de `test_o_protocolo_interno_vem_de_um_vocabulario_curto`;
> - o `modulo` de um componente aponta o arquivo que **tem entrada de
>   inventário**, que quase sempre é o da rota e não o do domínio — apontar
>   pro domínio devolve a árvore de pastas
>   (`learnings/2026-08-30-modulo-no-dominio-devolve-a-arvore-de-pastas.md`);
> - o recorte pra conferir no navegador virou script:
>   `.claude/skills/revy-research/recorte_produto.py`.

Card de handoff. Quem pegar isto **não** precisa ler a branch, o card grande da
arquitetura viva, nem a conversa que gerou isto — está tudo aqui.

Branch: `arquitetura-viva`, worktree em `.claude/worktrees/arquitetura-viva/`.
Tudo que este card cita vive em `.claude/skills/revy-research/`.

## Objetivo

Dar a **Catálogo Público, Motor de Simulação, Revy Control e Revy Loja** a mesma
camada de componente que Chatbot API e Estoque API já têm: caixas que são
*unidade de responsabilidade* com `arquivo:linha` provando que existem, mais as
arestas internas entre elas.

Hoje esses quatro mostram árvore de arquivo. As caixas que eles têm são **pasta**
(`app/web/`, `app/clients/`, `app/loja/`), quase nenhuma tem `termo`, e **nenhum
dos quatro tem uma única aresta interna**.

## O que já está pronto (não refaça, e use como molde)

| Produto | Componentes | Arestas internas |
|---|---|---|
| `chatbot-api` | 16 folhas em 4 gavetas | 20 |
| `estoque-api` | 9 folhas, sem gaveta | 11 |

Abra `arquitetura.py` e leia o bloco de `estoque-api` inteiro antes de começar —
é o exemplo mais limpo, e o mais recente. O do `chatbot-api` mostra como fica
quando há gaveta.

## A receita, que funcionou duas vezes

1. **Leia o `README.md` do produto.** A tabela **"Onde editar"** já é quase a
   lista de componentes; ela foi escrita por quem conhece o produto. Catálogo
   Público não tem essa tabela — lá use a lista de módulos de `app/`.
2. **Confirme cada caixa no código** com `rg`/`grep`, e ponha o `arquivo:linha`
   no `termo`. Componente sem prova é componente inventado.
3. **Derive as arestas de import real**, nunca de intuição:
   ```
   grep -n "^from app\.\|^from \. \|^import app\." <produto>/app/*.py
   grep -c "\bservico\." <produto>/app/main.py     # quantas vezes usa mesmo
   ```
   Onde o import engana, escreva o porquê num comentário na aresta. Dois casos
   reais do Estoque: a limpeza de mídia do worker passa pelo domínio
   (`servico.limpar_midias_orfas`) e não pelo módulo de mídia; e o domínio não
   *chama* o outbox, ele **grava** na fila e vai embora — por isso aquela é a
   única assíncrona do produto.
4. **Gaveta só onde ela diz algo que a caixa sozinha não diz.** No Chatbot:
   `workers` = as três threads sobem no *mesmo* lifespan; `integracoes` =
   produto de fora, nunca dado local. No Estoque não sobrou nenhuma — `outbox` +
   `worker` foi cogitado e recusado, porque o worker faz duas coisas (entrega o
   outbox **e** limpa mídia) e a gaveta mentiria.
5. **Seis a dez folhas por produto.** Abaixo de seis não conta a história;
   acima de dez volta a ser a lista de arquivos com outro nome. Coisa real que
   ficar de fora por esse teto deve virar comentário dizendo que ficou, e por quê
   — foi o que se fez no Chatbot com `app/operacao.py` e `app/hardening.py`.
6. **Acrescente o produto em `com_componente`**, na lista dentro de
   `test_gerar_arquitetura.py::TestProvaCabeNaCaixa`. Sem isso os termos dele
   não são conferidos.
7. **Regere e olhe no navegador.** Não é opcional — ver "Armadilhas" abaixo.

## Onde escrever

Tudo em `.claude/skills/revy-research/arquitetura.py`:

- os componentes vão no `"dentro"` do produto, dentro de `NOS`;
- as arestas vão numa lista nova por produto, no molde do que já existe:
  ```python
  ARESTAS_ESTOQUE = [ ... ]
  ARESTAS_INTERNAS = ARESTAS_INTERNAS + ARESTAS_ESTOQUE
  ```
  Faça `ARESTAS_CATALOGO`, `ARESTAS_MOTOR`, e assim por diante. Uma lista por
  produto mantém o diff legível e o comentário perto da aresta que ele explica.

Campos de um componente: `titulo`, `papel`, `termo` (a prova), `modulo` (prefixo
de caminho, pode cobrir vários arquivos — `app/rodizio` pega `rodizio.py` e
`rodizio_job.py`), e `decisoes` quando houver ADR.

Campos de uma aresta: `de`, `para`, `protocolo`, `sincrono`, `retry`.
Protocolos em uso: `chamada` (função chamando função, sem rótulo na tela),
`http`, `outbox`, `timer`, `tcp`.

## Ponto de partida por produto

Já levantei isto; não gaste de novo.

### Catálogo Público — o menor, comece por ele
15 entradas de inventário. Sem tabela "Onde editar" no README.
Módulos: `main.py`, `provider.py`, `outbox.py`, `events.py`, `pixel.py`,
`provisioning.py`, `contracts.py`, `config.py`, `templates/`.
Hoje tem 3 caixas: `outbox`, `pixel`, `provider`.
Fato do README que vale virar `termo`: consome **somente** o contrato HTTP
público da Estoque e guarda só os eventos de interesse em SQLite próprio.

### Motor de Simulação — 45 entradas
A tabela "Onde editar" do README já lista nove linhas, com os drivers separados
da base RPA. Hoje tem 2 caixas, e uma delas (`bancos`) é a lista de bancos.
Cuidado: **segredo bancário só vive aqui** (AGENTS.md §5) — `credenciais.py` +
`cripto.py` são componente, e nada de valor de env no termo.
Candidato a gaveta: os drivers por banco (santander, fontecred, bradesco, pan)
compartilham a base Playwright — isso é um fato, não arrumação.

### Revy Control — 256 entradas
Tabela "Onde editar" com dez linhas, e elas já são responsabilidades de verdade
(`roi_calc.py`, `vendas_projection.py`, `meta_ads_spend.py`,
`control/permissions.py`, `readiness.py`, `control/portfolio.py`). Hoje tem 4
caixas, três delas pasta. Tem 59 flags no inventário — elas se penduram sozinhas
no componente cujo `modulo` casa por prefixo.

### Revy Loja — 314 entradas, o mais caro
Tabela "Onde editar" com treze linhas. Hoje tem 6 caixas, **todas** pasta. É onde
mais se corre o risco de repetir a árvore de pastas: `app/loja/` e `app/web/`
não são responsabilidades, são camadas. Procure o domínio: atendimento,
copiloto, financeiro, metas/equipe, vendas, simulação manual, tráfego, canais de
WhatsApp, clientes HTTP.

## Invariantes

- **Stdlib apenas**, Python 3.9.6: sem `pyyaml`, sem `tomllib` (é 3.11+), sem
  `pytest`. Testes em `unittest`. Esta pasta não tem `.venv`.
- **Determinismo.** Duas gerações dão byte a byte o mesmo arquivo; `arquitetura.html`
  é commitado e `--verificar` compara. Todo `set` que vira lista passa por `sorted()`.
- **Não importe `app`** de produto nenhum (AGENTS.md §5) — leia como texto.
- Nada de secret, token ou `.env` no código, no termo ou no log.
- Os dataclasses são `frozen`: use `dataclasses.replace`.
- Mexeu em `arquitetura.py`? **Regere e commite o `arquitetura.html` junto** —
  senão o `--verificar` reprova para o próximo.

## Não faça — decisões do dono que não se re-propõem

- **Não agrupe por estágio do fluxo** ("entra / decide / sai"). Foi implementado,
  visto no navegador e **recusado**. Não estava errado no dado (19 das 20 arestas
  do Chatbot andam no mesmo sentido), o dono só não lê a arquitetura dele por
  estágio abstrato. Gaveta boa aqui nomeia coisa concreta.
- **Não faça gaveta por camada** (`web`, `clients`, `jobs`). É a árvore de pastas
  com outro nome, que é exatamente o que este card existe para desfazer.
- **Rota não entra na página.** 407 das entradas são rota; elas viravam parede de
  fichas. Estão em `SECOES_DISPENSADAS` com o porquê. `mapa/<produto>.md` continua
  listando todas.
- **Vermelho só onde o dado manda:** `retry=False` **e** atravessando produto.
  Dentro do mesmo processo é função chamando função — não há o que retentar.
- Rótulo de aresta é só o protocolo, e `chamada` não leva rótulo nenhum.
- Schema é vista separada, com alternador, agrupada por banco — não caixa dentro
  da arquitetura.
- As VMs são desenhadas (moldura tracejada). Um implementador já cortou alegando
  profundidade; foi revertido.

## Armadilhas — todas custaram caro

- **Termo comprido apaga a própria prova, em silêncio.** O orçamento é de ~59
  caracteres na caixa de um componente; acima disso `arq_render._face` corta com
  "…" e come justamente o `arquivo:linha` do fim. Não dá erro e não aparece no
  console. Seis dos nove termos do Estoque nasceram assim.
  `TestProvaCabeNaCaixa` pega — **desde que você acrescente o produto na lista
  `com_componente` dele**.
- **`getComputedStyle(el).opacity` devolve o meio da transição**, não o valor
  final (a folha tem `transition:opacity .15s`). Verificando por script, leia o
  atributo `style` inline ou corte a transição.
  (`learnings/2026-08-30-getcomputedstyle-le-o-meio-da-transicao.md`)
- **`hidden` não esconde um `<svg>`**, por dois motivos independentes.
  (`learnings/2026-08-30-hidden-nao-esconde-svg.md`)
- **`setPointerCapture` no `<svg>` engole todo clique**, sem rastro no console.
  (`learnings/2026-08-30-setpointercapture-no-svg-engole-o-clique.md`)
- **A automação de navegador vê a aba em segundo plano.** `document.hidden` é
  `true`: `requestAnimationFrame` não roda e o compositor não repinta, então
  mexer no `viewBox` pelo DOM muda o atributo mas o screenshot volta do quadro
  antigo. **Só navegação repinta.** Para ver o interior de um nó, gere um HTML de
  recorte com o `viewBox` já no lugar e os atributos `data-k-min`/`data-face-ate`
  renomeados (sem isso o JS esconde o interior), e navegue até ele.
- **A métrica de travessias (`TestArestasInternasLegiveis`) já inverteu de sinal
  uma vez.** Ela mede quantas setas cortam caixa alheia, e hoje só olha o
  Chatbot. Se você mudar o agrupamento de um produto e ela reprovar, **confira o
  sinal dela antes de mexer no teto**: na fase dos estágios ela premiava o
  desenho ilegível, e subir o teto até passar não é teste, é enfeite. A história
  inteira está na docstring da classe.

## Como saber que acabou

A partir de `.claude/skills/revy-research/`:

```
python3 -m unittest test_gerar_arquitetura -q      # macOS
python3 gerar_arquitetura.py
python3 gerar_arquitetura.py --verificar           # exit 0
```

Windows: `python -m unittest test_gerar_arquitetura -q` e `python gerar_arquitetura.py`.

Os 80 testes atuais verdes, mais o produto novo dentro de `com_componente` em
`TestProvaCabeNaCaixa`.

**Verificação no navegador é obrigatória.** Sete defeitos desta página só
apareceram abrindo ela, e dois não deixavam rastro no console. Para servir o
arquivo (a extensão de navegador bloqueia `file://`):

```
cd .claude/skills/revy-research && python3 -m http.server 8899
```

E confira, no produto que você acabou de escrever: o interior abre com as caixas
legíveis, o subtítulo de cada uma termina no `arquivo:linha` **sem** "…", e passar
o mouse numa caixa acende só as setas que tocam ela.

## Bônus que já está lá e você pode usar

Arraste o **fundo** para navegar; arraste uma **caixa** para movê-la (as setas
acompanham). Dois botões no rodapé: **automático** descarta o que você moveu,
**exportar** gera o bloco `POSICOES` para colar em `arquitetura.py` — dali em
diante a posição é dado versionado. São deslocamentos, não coordenadas.

## Docs permitidos

- este card
- `README.md` do produto que você está escrevendo (um por vez)
- `.claude/skills/revy-research/learnings/2026-08-30-*.md`
- `AGENTS.md`

## Docs proibidos

Todo o resto de `docs/`. Nada de `docs/nao-plano/`, nada de handoff antigo, nada
de ler spec inteiro, nada de abrir produto que não é o da vez.
