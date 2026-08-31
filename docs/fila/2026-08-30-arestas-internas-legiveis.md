# Arestas internas legíveis

**FEITO em 30/08** (commit `4e22376`). O que foi feito, o que ficou de fora e
os números medidos estão em [Resultado](#resultado); o resto do card fica como
registro do estado anterior. Quem pegar o próximo passo — replicar a fôrma de
componentes nos outros cinco produtos — lê o Resultado e para.

Card de handoff. Quem pegar isto **não** precisa ler a branch inteira nem o
card grande da arquitetura viva — está tudo o que importa aqui.

## Resultado

O dono pediu para abrir no navegador antes de escolher, e escolheu 1+2+3.

**A métrica do card estava inflada.** Ela contava 145 travessias, mas 60 delas
eram a aresta cruzando a caixa do **próprio produto** — coisa que toda aresta
interna faz por definição, porque ela vive dentro dele. Ancestral de ponta tem
a mesma natureza (sair de dentro de `workers` obriga a cruzar a borda de
`workers`). Excluindo os dois, o número honesto era **20 arestas, 16 sujas, 75
travessias**. As pontas já estavam certas: 0 de 40 fora da borda — o defeito
era só o caminho no meio.

| | antes | depois |
|---|---|---|
| arestas internas | 20 | 20 |
| que atravessam caixa alheia | 16 | 13 |
| travessias | **75** | **43** |
| arestas internas visíveis sem pedir | 20 | **0** |

Não zerou, e o card pedia que se dissesse em quanto ficou: **43**. As 43 só
aparecem quando alguém pede por elas (item 2), então o desenho parado tem
zero seta interna.

Três consertos, mais um achado no caminho:

1. **Ordem por afinidade** (`arq_layout._ordem_por_afinidade`). O
   empacotamento lia os irmãos em ordem alfabética, que não tem relação com
   quem chama quem. Agora minimiza o arranjo linear ponderado por subida de
   encosta. 75 → 43. **A semente óbvia piora**: começar pelo vizinho mais
   próximo dá 52, porque põe a Borda HTTP (que fala com quase todos) no
   começo da fila e a subida trava num ótimo local pior. Está medido na
   docstring — não "melhore" de volta sem medir.
2. **Aresta interna sob demanda.** Nasce apagada pelo CSS (`[data-interna]`),
   acende sob o mouse só as que tocam aquele componente. O renderer escreve
   `data-de`/`data-para` com o id **absoluto** para o JS testar linhagem por
   prefixo; `data-aresta` fica só na polyline, porque o valor dele carrega um
   `>` literal que quebra o regex de dois testes.
3. **Aresta entre produtos apaga quando só atravessa.** Estando dentro de um
   nó, uma aresta que não toca a linhagem dele cai para 0.10. A linha vermelha
   Loja→Motor cortando o Chatbot aberto não dizia nada sobre o Chatbot.
4. **De brinde:** quatro dos 81 títulos transbordavam por cima da caixa
   vizinha ("Clientes HTTP de outros produtos" em cima de "Projeção do
   Control"). O teto de fonte passou a olhar o comprimento — e a **truncar**,
   porque `round(8.26, 1)` dá 8.3 e reintroduzia o estouro em dois deles.

**A métrica virou teste** (`TestArestasInternasLegiveis`, teto 43, 74 no
total). Sabotar a ordenação devolve 75 e ele falha — verificado.

Verificado no navegador (não só nos testes): hover na Borda HTTP acende as 11
pontas dela e só elas; sair apaga as 11; entrar no Chatbot apaga as 12 arestas
entre produtos que não o tocam e mantém as 4 que tocam.

**Armadilha nova, que custou uma investigação errada:** `getComputedStyle(el).opacity`
lido logo depois de mexer na opacidade devolve o valor **no meio da transição**
(a folha tem `transition:opacity .15s`), não o final — mediu 0 onde já havia
"1". Leia o atributo `style` inline, ou corte a transição, quando for verificar
opacidade por script.

**O que NÃO foi feito:** a saída A (roteamento com desvio de obstáculo)
continua sem fazer, de propósito — 43 travessias escondidas atrás do hover não
justificam meio dia e o risco de `--verificar` passar a falhar sozinho.
Podar arestas também não foi feito; as 20 continuam declaradas.

## Objetivo

Fazer as setas *dentro* de um produto serem legíveis. Hoje elas ligam centro a
centro e atravessam por cima das caixas que estão no meio do caminho.

## O problema, medido

Não é impressão. Rode isto (salve no scratchpad, não no repo):

```python
"""Quantas arestas atravessam caixa por cima?"""
import json, re, sys
from pathlib import Path

BASE = Path(".claude/skills/revy-research").resolve()
sys.path.insert(0, str(BASE))
import arquitetura, arq_layout, arq_modelo

raiz = BASE.parents[2]
frescor = json.loads((BASE / "mapa" / "_frescor.json").read_text())
completo = arq_modelo.carregar(
    raiz, frescor, arquitetura.NOS,
    list(arquitetura.ARESTAS) + list(arquitetura.ARESTAS_INTERNAS),
    arquitetura.VMS, arquitetura.FLUXOS, arquitetura.BANCOS)
arq = arq_modelo.filtrar(completo, arquitetura.SECOES_ARQUITETURA, manter_manuais=True)
cena = arq_layout.dispor(arq, arq.vms)

html = (BASE / "arquitetura.html").read_text()
i = html.index('<svg id="mapa-arquitetura"')
svg = html[i:html.index("</svg>", i)]
polis = re.findall(r'<polyline data-aresta="([^"]+)" points="([^"]+)"', svg)

def segmentos(pts):
    p = [tuple(float(v) for v in par.split(",")) for par in pts.split()]
    return list(zip(p, p[1:]))

def cruza(seg, c):
    (x1, y1), (x2, y2) = seg
    if abs(y1 - y2) < 0.01:
        return (c.y < y1 < c.y + c.h) and not (max(x1, x2) <= c.x or min(x1, x2) >= c.x + c.w)
    if abs(x1 - x2) < 0.01:
        return (c.x < x1 < c.x + c.w) and not (max(y1, y2) <= c.y or min(y1, y2) >= c.y + c.h)
    return False

internas = {f'{a["de"]}->{a["para"]}' for a in arquitetura.ARESTAS_INTERNAS}
total = com = trav = 0
for marca, pts in polis:
    if marca not in internas:
        continue
    total += 1
    de, para = marca.split("->")
    n = sum(1 for seg in segmentos(pts) for c in cena.caixas
            if c.tipo != "item" and de.split(".")[0] in c.chave
            and not c.chave.endswith(de) and not c.chave.endswith(para)
            and cruza(seg, c))
    if n:
        com += 1
        trav += n
print(total, com, trav)
```

**Números de 30/08, com o Chatbot sendo o único produto com componentes:**

| | |
|---|---|
| arestas internas desenhadas | 20 |
| que passam por cima de alguma caixa | **20** |
| total de travessias | **145** |

As piores: `workers → atendimento` (12 travessias), `atendimento →
provisionamento` (11), `workers.followup → agente` (10).

Meta: **nenhuma aresta interna atravessando caixa que não seja a sua própria
ponta.** Se a abordagem escolhida não zerar, diga em quanto ficou e por quê.

## Duas saídas, e qual eu recomendo

**A. Roteamento com desvio de obstáculo.** A seta contorna as caixas em vez de
passar por cima: canais entre as caixas (os corredores de `MARGEM`) viram a
malha por onde ela anda. É o certo, é o que um Structurizr/Graphviz faz, e é
meio dia de trabalho — não meia hora. Cuidado com o determinismo: o algoritmo
tem que dar o mesmo resultado byte a byte em duas execuções, senão
`gerar_arquitetura.py --verificar` passa a falhar sozinho.

**B. Aresta sob demanda.** As setas internas nascem apagadas; passar o mouse
ou clicar num componente acende **só as que tocam aquele componente**. O
desenho fica limpo e a relação continua lá quando alguém pergunta por ela.
Barato, e a máquina de acender já existe: `Zoom.acender(ids)` /
`Zoom.apagar()` em `arq_zoom.js`, usada hoje pelo painel de fluxos.

**Recomendo B primeiro** — resolve o sintoma hoje e não impede A depois. Mas é
decisão do dono, não sua: se ele já tiver dito qual quer, siga.

Uma terceira, se for fazer A: nada impede reduzir o número de arestas. 20
arestas entre 10 componentes é denso por natureza. Vale perguntar ao dono se
alguma delas é ruído antes de investir em desenhar todas bem.

## O que existe hoje (não redescubra)

Tudo em `.claude/skills/revy-research/`. Quatro camadas, três já existiam
antes desta branch:

| Camada | Arquivo | O que é |
|---|---|---|
| inventário | `mapa/_frescor.json` | 816 entradas geradas por `gerar_mapa.py`: `secao/chave/simbolo/arquivo/linha` |
| intenção | `arquitetura.py` | **escrito à mão**: `NOS`, `ARESTAS`, `ARESTAS_INTERNAS`, `VMS`, `BANCOS`, `FLUXOS` |
| modelo | `arq_modelo.py` | funde os dois; `carregar()`, `filtrar()` |
| layout | `arq_layout.py` | `dispor(modelo, grupos) -> Cena` |
| desenho | `arq_render.py` | `render(vistas, js, tokens) -> str` |
| zoom | `arq_zoom.js` | `Zoom.criar(elemento, opts)`, ES5, sem dependência |
| tokens | `arq_design.py` | lê `shared/brand/revy-tokens.css` |

Saída: `arquitetura.html`, commitado, verificado por
`gerar_arquitetura.py --verificar`.

**Três vistas**, alternador no topo:

- **Arquitetura** — seções `worker`, `flag`, `template`. Tem arestas e fluxos.
- **Schema** — seções `modelo`, `migration`, agrupado por banco. Sem aresta,
  sem fluxo.
- **Design** — os 35 tokens da marca, lidos de `revy-tokens.css` na geração.

**A camada de componente (C4 nível 3)** existe só no `chatbot-api`: 10
componentes e 20 arestas internas, cada um com `arquivo:linha` verificado no
código. Os outros cinco produtos ainda mostram a árvore de arquivos. Replicar
a fôrma neles é o passo seguinte — **e depende deste card fechar primeiro**,
senão o problema das setas se multiplica por seis.

## Invariantes

- **Stdlib apenas.** Python 3.9.6: sem `pyyaml`, sem `tomllib` (3.11+), sem
  `pytest`. Testes em `unittest`. JS em ES5, sem CDN, sem `<script src>`.
- **Determinismo.** Duas gerações dão byte a byte o mesmo arquivo. Todo `set`
  que vira lista passa por `sorted()`.
- Não importe `app` de produto nenhum (AGENTS.md §5) — leia como texto.
- Nada de secret, token ou `.env` no código ou no log.
- Os dataclasses são `frozen`: use `dataclasses.replace`.

## Não faça — decisões do dono que não se re-propõem

- **Rota não entra na página.** 407 das 816 entradas são rota; elas viravam
  uma parede de fichas que ocupava metade do produto. Estão em
  `SECOES_DISPENSADAS` com o porquê. `mapa/<produto>.md` continua listando
  todas.
- Schema é vista separada, com alternador — não caixa dentro da arquitetura.
- Schema agrupa por banco, não por produto.
- As VMs são desenhadas (moldura tracejada). Um implementador já cortou
  alegando profundidade; foi revertido.
- `suite-pg` não contém Loja e Control: eles falam TCP com o banco. Modelar
  como contenção desenhava a árvore dos dois em duplicata.
- Vermelho só onde o dado manda: `retry=False` **e** atravessando produto.
  Dentro do mesmo processo é função chamando função — não há o que retentar.
- Rótulo de aresta é só o protocolo, e `chamada` não leva rótulo nenhum.
- Área do produto é proporcional à **raiz** da quantidade de itens, não à
  quantidade.

## Armadilhas — todas custaram caro, todas estão em `learnings/`

- **`setPointerCapture` no `<svg>` engole todo clique.** O `click` seguinte
  passa a ter o svg como alvo, `closest("[data-navegavel]")` devolve `null`, e
  **nada aparece no console**.
  (`2026-08-30-setpointercapture-no-svg-engole-o-clique.md`)
- **`hidden` não esconde um `<svg>`**, por dois motivos independentes: a folha
  do autor ganha da regra padrão `[hidden]`, e `SVGElement` não tem a
  propriedade IDL `hidden` — `svg.hidden` lê `undefined`, e um guard
  `!svg.hidden` fica sempre verdadeiro.
  (`2026-08-30-hidden-nao-esconde-svg.md`)
- **Traço em unidade de cena vira subpixel.** 1,5 unidade numa cena de 10 mil
  dá 0,09px. Use `vector-effect="non-scaling-stroke"`.
- **Fonte sai do tamanho da CAIXA, nunca do nível**, e tem teto na faixa do
  título (`arq_layout.banda_titulo`) — senão o título cai em cima dos filhos.
- **A automação de navegador vê a aba em segundo plano.** `document.hidden` é
  `true`: `requestAnimationFrame` não roda (então o voo não anima) e o
  compositor não repinta (então mexer no `viewBox` pelo DOM muda o atributo
  mas o screenshot volta do quadro antigo). **Só navegação repinta.** Para ver
  o interior de um nó, gere um HTML de recorte com o `viewBox` já no lugar e
  os atributos `data-k-min`/`data-face-ate` renomeados (sem eles o JS não
  esconde o interior), e navegue até ele.

## Como saber que acabou

A partir de `.claude/skills/revy-research/`:

```
python3 -m unittest test_gerar_arquitetura -q      # macOS
python3 gerar_arquitetura.py
python3 gerar_arquitetura.py --verificar           # exit 0
```

Windows: `.\.venv\Scripts\python.exe -m unittest test_gerar_arquitetura -q`

Os 73 testes atuais verdes, mais um teste novo que prove a melhora — a métrica
de travessias é o candidato óbvio, e ela é calculável sem navegador.

**Verificação no navegador é obrigatória.** Sete defeitos desta página só
apareceram abrindo ela, e dois não deixavam rastro no console.

## Docs permitidos

- este card
- `.claude/skills/revy-research/learnings/2026-08-30-*.md` (os dois de SVG)
- `AGENTS.md`

## Docs proibidos

Todo o resto de `docs/`. Nada de `docs/nao-plano/`, nada de handoff, nada de
ler o spec inteiro, nada de abrir outros produtos do monorepo.
