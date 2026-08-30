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
import json

from arq_layout import Caixa, Cena, ALTURA_TITULO, MARGEM
from arq_modelo import Aresta, Modelo, No, Vm

_e = html.escape

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


def _fonte_titulo(c: Caixa) -> float:
    """Fonte proporcional a CAIXA, nunca ao nivel.

    Amarrar ao nivel produzia 26 no nivel 1 — numa cena de 11 mil de largura,
    3,6px na tela, ilegivel. O texto de um filho vive nas coordenadas absolutas
    do pai (sem transform de escala), entao a unica referencia que faz sentido
    e o tamanho da propria caixa: assim o titulo fica legivel exatamente quando
    a caixa enche a tela, em qualquer profundidade.
    """
    return max(1.5, round(min(c.w * 0.055, c.h * 0.30), 1))


def _marcar_spof(no: No, prefixo: str, resultado: dict[str, bool]) -> None:
    chave = f"{prefixo}.{no.chave}" if prefixo else no.chave
    if no.spof:
        resultado[chave] = True
    for filho in no.filhos:
        _marcar_spof(filho, chave, resultado)


def _spof_por_chave(nos: tuple[No, ...], vms: tuple[Vm, ...] = ()) -> dict[str, bool]:
    """Mapeia chave-completa (mesmo esquema de arq_layout: caminho separado
    por ".") -> spof. `Caixa` nao carrega `spof` (nao esta na lista fixa de
    campos do contrato), entao esta e a unica forma de saber.

    Um produto dentro de uma VM tem a chave da Caixa prefixada por
    `vm.chave.` (arq_layout._dispor_vm) — sem isso o SPOF do Motor de
    Simulacao, por exemplo, nunca bateria contra `app2037.motor-simulacao`.
    """
    resultado: dict[str, bool] = {}
    for no in nos:
        _marcar_spof(no, "", resultado)
    for vm in vms:
        for chave_produto in vm.contem:
            for no in nos:
                if no.chave == chave_produto:
                    _marcar_spof(no, vm.chave, resultado)
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


def _rect_vm(c: Caixa) -> str:
    # Moldura, nao caixa: fill="none" e tracejado. A VM e infra, nao
    # produto — o dono pediu que ela fique visualmente distinta (blast
    # radius: uma maquina caindo leva tudo que esta dentro dela junto).
    largura = round(max(0.3, 1.5 / max(1, c.nivel)), 2)
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="6" fill="none" stroke="{INK_SOFT}" stroke-width="{largura}" '
        f'stroke-dasharray="8 5"/>'
    )


def _face(c: Caixa, spof: bool) -> str:
    fonte_titulo = _fonte_titulo(c)
    fonte_sub = round(max(1.2, fonte_titulo * 0.55), 1)
    px = c.x + fonte_titulo * 0.6
    py_titulo = c.y + fonte_titulo * 1.25
    py_sub = py_titulo + fonte_sub * 1.7
    # Cortar na largura da caixa: a `nota` de uma VM tem ~200 caracteres e sem
    # isso ela sai numa linha unica atravessando a cena inteira por cima de tudo.
    # 0.52em por caractere e a media de uma sans-serif.
    cabe = max(0, int((c.w - fonte_titulo * 1.2) / (fonte_sub * 0.52)))
    sub = c.subtitulo
    if len(sub) > cabe:
        sub = sub[:max(0, cabe - 1)] + "\u2026"

    partes = [
        f'<text x="{px:.2f}" y="{py_titulo:.2f}" font-size="{fonte_titulo}" '
        f'font-weight="600">{html.escape(c.titulo)}</text>',
        f'<text x="{px:.2f}" y="{py_sub:.2f}" font-size="{fonte_sub}" '
        f'fill="{INK_SOFT}">{html.escape(sub)}</text>',
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
    # Mesmo corte da face: o subtitulo de um item e o `arquivo:linha`, que
    # facilmente passa da largura da caixa.
    cabe = max(0, int((c.w - 8) / (fonte_sub * 0.52)))
    sub = c.subtitulo
    if len(sub) > cabe:
        sub = "\u2026" + sub[-max(0, cabe - 1):]   # o fim importa mais: :linha
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="2" fill="{SURFACE_SOFT}" stroke="{LINE_STRONG}" stroke-width=".3"/>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 5.5:.2f}" font-size="{fonte_titulo}">'
        f'{html.escape(c.titulo)}</text>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 9.5:.2f}" font-size="{fonte_sub}" '
        f'fill="{INK_SOFT}">{html.escape(sub)}</text>'
    )


def _no_recursivo(caixa: Caixa, por_pai: dict, spof_map: dict) -> str:
    filhos = por_pai.get(caixa.chave, [])
    subs_no = [f for f in filhos if f.tipo in ("no", "vm")]
    itens = [f for f in filhos if f.tipo == "item"]
    spof = spof_map.get(caixa.chave, False)

    interior = "".join(_item(i) for i in itens)
    interior += "".join(_no_recursivo(s, por_pai, spof_map) for s in subs_no)
    kmin_attr = f' data-k-min="{caixa.k_min:.3f}"' if caixa.k_min > 0 else ""
    retangulo = _rect_vm(caixa) if caixa.tipo == "vm" else _rect_no(caixa, spof)

    return (
        f'<g id="{html.escape(caixa.chave)}" data-titulo="{html.escape(caixa.titulo)}" data-navegavel>'
        + retangulo
        + _face(caixa, spof)
        + f"<g{kmin_attr}>{interior}</g>"
        + "</g>"
    )


def _resolver_produto(chave_produto: str, caixas_por_chave: dict[str, Caixa]) -> Caixa | None:
    """Acha a Caixa de um produto pra fim de aresta. Um produto dentro de
    uma VM tem a chave da Caixa prefixada (`app2037.portal-gestao`), entao
    a chave crua da Aresta (`portal-gestao`) nunca bate direto — casa pelo
    sufixo. Produto em mais de uma VM (portal-gestao: app2037 e suite-pg)
    escolhe a primeira em ordem alfabetica, sempre a mesma — determinismo,
    nao acaso — o que tambem prioriza a VM que roda o codigo (app2037) sobre
    a que so guarda o schema (suite-pg)."""
    if chave_produto in caixas_por_chave:
        return caixas_por_chave[chave_produto]
    candidatos = sorted(
        k for k in caixas_por_chave if k.endswith("." + chave_produto))
    return caixas_por_chave[candidatos[0]] if candidatos else None


def _aresta(a: Aresta, de: Caixa, para: Caixa) -> str:
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


def _fluxos_html(cena: Cena, modelo: Modelo) -> str:
    """Seletor de fluxo: um botao por `Fluxo`, que acende so as caixas dos
    seus passos (`Zoom.acender`) e lista os passos EM ORDEM (a ordem e o
    conteudo do fluxo — nunca ordenar). Um passo pode citar uma VM que nao
    e produto (`evolution2037`, `n8n2037`): deliberado, ver `FLUXOS` em
    `arquitetura.py`, nao filtrado aqui."""
    if not modelo.fluxos:
        return ""
    botoes, dados = [], {}
    for f in modelo.fluxos:
        botoes.append(f'<button data-fluxo="{_e(f.chave)}">{_e(f.titulo)}</button>')
        dados[f.chave] = {
            "titulo": f.titulo,
            "invariante": f.invariante or "",
            "passos": [{"no": p.no, "faz": p.faz, "sincrono": p.sincrono}
                       for p in f.passos],
        }
    json_fluxos = (json.dumps(dados, ensure_ascii=False, sort_keys=True)
                   .replace("<", "\\u003c"))
    # A lista e o invariante sao montados no navegador a partir do FLUXOS,
    # so para o fluxo escolhido. Concatenar os quatro no HTML fazia cada
    # clique mostrar os passos de todos os fluxos somados.
    return (f'<div id="fluxos"><b>Fluxos</b> '
            f'{"".join(botoes)}<button data-fluxo="">limpar</button>'
            f'<ol id="passos" hidden></ol><p id="inv" hidden></p></div>'
            f'<script>var FLUXOS = {json_fluxos};</script>')


def render(cena: Cena, modelo: Modelo, js: str) -> str:
    spof_map = _spof_por_chave(modelo.nos, modelo.vms)
    por_pai = _agrupar_por_pai(cena.caixas)
    raizes = sorted(por_pai.get(None, []), key=lambda c: c.chave)

    corpo_svg = "".join(_no_recursivo(r, por_pai, spof_map) for r in raizes)

    caixas_por_chave = {c.chave: c for c in cena.caixas}
    resolvidas = []
    for a in modelo.arestas:
        de = _resolver_produto(a.de, caixas_por_chave)
        para = _resolver_produto(a.para, caixas_por_chave)
        if de is not None and para is not None:
            resolvidas.append((a, de, para))
    arestas_svg = "".join(_aresta(a, de, para) for a, de, para in resolvidas)
    fluxos_html = _fluxos_html(cena, modelo)

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
  #fluxos{{position:fixed;top:12px;right:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:12px;max-width:280px}}
  #fluxos button{{font-size:11px;margin:2px 2px 0 0;border:1px solid {LINE_STRONG};
    border-radius:4px;background:{SURFACE_SOFT};color:{INK};cursor:pointer;padding:3px 7px}}
  #fluxos button:hover{{background:{LINE}}}
  #passos{{margin:6px 0 0;padding-left:18px}}
  #inv{{margin:6px 0 0;font-style:italic}}
  #passos li{{margin:2px 0}}
  #fluxos p.inv{{margin:6px 0 0;color:{INK_SOFT};font-style:italic}}
  [data-k-min],[data-face-ate]{{transition:opacity .1s linear}}
  [data-navegavel],[data-aresta]{{transition:opacity .15s linear}}
</style>
<div id="trilha">Revy</div>
<div id="dica">clique numa caixa para cair dentro · <strong>Esc</strong> volta · roda dá zoom · borda grossa é SPOF, linha tracejada é aresta assíncrona, moldura tracejada é máquina (VM)</div>
{fluxos_html}

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
  var elFluxos = document.getElementById("fluxos");
  if (elFluxos) {{
    elFluxos.addEventListener("click", function (ev) {{
      var chave = ev.target.getAttribute("data-fluxo");
      if (chave === null) return;
      var ol = document.getElementById("passos"), inv = document.getElementById("inv");
      if (!chave) {{
        Zoom.apagar(); ol.hidden = true; inv.hidden = true; return;
      }}
      var f = FLUXOS[chave];
      Zoom.acender(f.passos.map(function (p) {{ return p.no; }}));
      ol.textContent = "";
      f.passos.forEach(function (p) {{
        var li = document.createElement("li");
        li.textContent = p.faz + " \u2014 " + p.no + (p.sincrono ? "" : " (fila)");
        ol.appendChild(li);
      }});
      ol.hidden = false;
      inv.textContent = f.invariante || "";
      inv.hidden = !f.invariante;
    }});
  }}
</script>
"""
