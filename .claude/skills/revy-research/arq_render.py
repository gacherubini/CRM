"""O HTML do zoom continuo: `Cena` + `Modelo` -> uma pagina SVG auto-contida.

O alvo visual e `arq_zoom_demo.html`, ja aprovado no navegador — esta
funcao produz a MESMA estrutura por caixa, so que gerada:

    <g id="..." data-titulo="..." data-navegavel>
      <rect .../>
      <g data-face-ate="{k_face}">   titulo grande + subtitulo. SOME ao entrar.
      <g data-k-min="{k_min}">       filhos e itens. APARECEM ao entrar.
    </g>

Os dois `<g>` internos SEMPRE existem (e' a forma fixa por caixa), mas o
ATRIBUTO `data-face-ate`/`data-k-min` so aparece quando o valor e' > 0 —
nivel 1 nao tem pai pra derivar o limiar contra (arq_layout.py deixa
k_min=k_face=0.0 nesse caso), e uma caixa navegavel carregando
`data-k-min` faria o `aplicarLod` (que escreve opacity a cada quadro)
brigar com o `Zoom.acender` da Task 7 — o realce de fluxo piscaria.

`arq_zoom.js` nao le nenhum outro atributo alem de: id, data-navegavel,
data-titulo, data-k-min, data-face-ate, data-aresta. Nao inventar outros.

Stdlib apenas. Auto-contido: nenhum `http://`/`https://` no HTML gerado —
`file://` bloqueia `fetch()`, entao o JS entra inline (`js` embutido
verbatim), sem `<script src=...>`.
"""
from __future__ import annotations

import html

from arq_layout import Caixa, Cena, ALTURA_TITULO, MARGEM
from arq_modelo import Aresta, Modelo, No

# Cores de shared/brand/revy-tokens.css. Nao inventar paleta — ver o learning
# 2026-08-23-tokens-de-marca-tem-fonte-unica.md.
PAPER = "#f9f9f9"
SURFACE = "#ffffff"
SURFACE_SOFT = "#efeceb"
INK = "#1b1b1b"
INK_SOFT = "#57514f"
LINE = "#ded8d9"
LINE_STRONG = "#cdc6c4"
BRAND = "#1f4d3a"


def _fonte_titulo(nivel: int) -> float:
    # O texto de um filho e desenhado nas coordenadas absolutas do pai (sem
    # transform de escala), entao precisa encolher junto — e o que faz o
    # texto ficar legivel exatamente quando a caixa enche a tela.
    return max(1.5, round(26 / (nivel ** 1.35), 1))


def _spof_por_chave(nos: tuple[No, ...], prefixo: str = "") -> dict[str, bool]:
    """Mapeia chave-completa (mesmo esquema de arq_layout: caminho separado
    por ".") -> spof. `Caixa` nao carrega `spof` (nao esta na lista fixa de
    campos do contrato), entao esta e a unica forma de saber."""
    resultado: dict[str, bool] = {}
    for no in nos:
        chave = f"{prefixo}.{no.chave}" if prefixo else no.chave
        if no.spof:
            resultado[chave] = True
        resultado.update(_spof_por_chave(no.filhos, chave))
    return resultado


def _agrupar_por_pai(caixas: tuple[Caixa, ...]) -> dict[str | None, list[Caixa]]:
    grupos: dict[str | None, list[Caixa]] = {}
    for c in caixas:
        grupos.setdefault(c.pai, []).append(c)
    return grupos


def _rect_no(c: Caixa, spof: bool) -> str:
    largura = round(max(0.3, (3.0 if spof else 2.0) / max(1, c.nivel)), 2)
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="6" fill="{SURFACE}" stroke="{BRAND}" stroke-width="{largura}"/>'
    )


def _face(c: Caixa, spof: bool) -> str:
    fonte_titulo = _fonte_titulo(c.nivel)
    fonte_sub = round(max(1.2, fonte_titulo * 0.55), 1)
    px = c.x + max(6.0, MARGEM / c.nivel) * 0.5
    py_titulo = c.y + max(10.0, fonte_titulo * 1.15)
    py_sub = py_titulo + fonte_sub * 1.7

    partes = [
        f'<text x="{px:.2f}" y="{py_titulo:.2f}" font-size="{fonte_titulo}" '
        f'font-weight="600">{html.escape(c.titulo)}</text>',
        f'<text x="{px:.2f}" y="{py_sub:.2f}" font-size="{fonte_sub}" '
        f'fill="{INK_SOFT}">{html.escape(c.subtitulo)}</text>',
    ]
    if spof:
        py_spof = c.y + c.h - max(8.0, fonte_sub * 1.2)
        partes.append(
            f'<text x="{px:.2f}" y="{py_spof:.2f}" font-size="{fonte_sub}" '
            f'font-weight="600" fill="{BRAND}">SPOF</text>'
        )

    atributo = f' data-face-ate="{c.k_face:.3f}"' if c.k_face > 0 else ""
    return f"<g{atributo}>" + "".join(partes) + "</g>"


def _item(c: Caixa) -> str:
    fonte_titulo, fonte_sub = 4.2, 3.0
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="2" fill="{SURFACE_SOFT}" stroke="{LINE_STRONG}" stroke-width=".3"/>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 5.5:.2f}" font-size="{fonte_titulo}">'
        f'{html.escape(c.titulo)}</text>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 9.5:.2f}" font-size="{fonte_sub}" '
        f'fill="{INK_SOFT}">{html.escape(c.subtitulo)}</text>'
    )


def _no_recursivo(caixa: Caixa, por_pai: dict, spof_map: dict) -> str:
    filhos = por_pai.get(caixa.chave, [])
    subs_no = [f for f in filhos if f.tipo == "no"]
    itens = [f for f in filhos if f.tipo == "item"]
    spof = spof_map.get(caixa.chave, False)

    interior = "".join(_item(i) for i in itens)
    interior += "".join(_no_recursivo(s, por_pai, spof_map) for s in subs_no)
    kmin_attr = f' data-k-min="{caixa.k_min:.3f}"' if caixa.k_min > 0 else ""

    return (
        f'<g id="{html.escape(caixa.chave)}" data-titulo="{html.escape(caixa.titulo)}" data-navegavel>'
        + _rect_no(caixa, spof)
        + _face(caixa, spof)
        + f"<g{kmin_attr}>{interior}</g>"
        + "</g>"
    )


def _aresta(a: Aresta, caixas_por_chave: dict[str, Caixa]) -> str:
    de, para = caixas_por_chave[a.de], caixas_por_chave[a.para]
    x1, y1 = de.x + de.w / 2, de.y + de.h / 2
    x2, y2 = para.x + para.w / 2, para.y + para.h / 2

    tracejado = ' stroke-dasharray="6 4"' if not a.sincrono else ""
    marca = f"{html.escape(a.de)}->{html.escape(a.para)}"
    linha = (
        f'<line data-aresta="{marca}" x1="{x1:.2f}" y1="{y1:.2f}" '
        f'x2="{x2:.2f}" y2="{y2:.2f}"{tracejado}/>'
    )
    if not a.sincrono and not a.retry:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        linha += (
            f'<text x="{mx:.2f}" y="{my:.2f}" font-size="8" fill="{INK_SOFT}">'
            "· sem retry</text>"
        )
    return linha


def render(cena: Cena, modelo: Modelo, js: str) -> str:
    spof_map = _spof_por_chave(modelo.nos)
    por_pai = _agrupar_por_pai(cena.caixas)
    raizes = sorted(por_pai.get(None, []), key=lambda c: c.chave)

    corpo_svg = "".join(_no_recursivo(r, por_pai, spof_map) for r in raizes)

    caixas_por_chave = {c.chave: c for c in cena.caixas}
    arestas_svg = "".join(
        _aresta(a, caixas_por_chave)
        for a in modelo.arestas
        if a.de in caixas_por_chave and a.para in caixas_por_chave
    )

    largura = max(cena.largura, 1.0)
    altura = max(cena.altura, 1.0)

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Revy — arquitetura</title>
<style>
  html,body{{margin:0;height:100%;background:{PAPER};
    font-family:system-ui,-apple-system,sans-serif;color:{INK}}}
  svg{{width:100vw;height:100vh;display:block;cursor:grab;touch-action:none}}
  #trilha{{position:fixed;top:12px;left:12px;background:{SURFACE};padding:6px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:13px}}
  #dica{{position:fixed;bottom:12px;left:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:11px;color:{INK_SOFT}}}
  [data-k-min],[data-face-ate]{{transition:opacity .1s linear}}
</style>
<div id="trilha">Revy</div>
<div id="dica">clique numa caixa para cair dentro · <strong>Esc</strong> volta · roda dá zoom · borda grossa é SPOF, linha tracejada é aresta assíncrona</div>

<svg id="mapa" viewBox="0 0 {largura:.2f} {altura:.2f}">
{corpo_svg}<g stroke="{BRAND}" stroke-width="1.5" fill="none">
{arestas_svg}</g>
</svg>

<script>
{js}
</script>
<script>
  var svg = document.getElementById("mapa");
  svg.addEventListener("zoom:mudou", function (ev) {{
    document.getElementById("trilha").textContent = ev.detail.titulo || "Revy";
  }});
  Zoom.init(svg, {{}});
</script>
"""
