"""O HTML do zoom continuo: `Vista` (uma por cena) -> uma pagina SVG
auto-contida com um alternador no topo.

Task 10: a pagina passa a ter duas cenas independentes (Arquitetura e
Schema, uma `Vista` cada) no MESMO documento — um `<svg id="mapa-{chave}">`
por vista, so a primeira visivel de saida, e um `Zoom.criar(...)` (arq_zoom.js)
por vista, porque as duas nao podem dividir estado de zoom.

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
from dataclasses import dataclass

from arq_layout import Caixa, Cena, ALTURA_TITULO, MARGEM
from arq_modelo import Aresta, Modelo, No, Vm

_e = html.escape


@dataclass(frozen=True)
class Vista:
    """Uma cena renderizavel: a vista Arquitetura ou a vista Schema (Task 10).

    `cena` e `modelo` sao SEMPRE o par que saiu do mesmo `arq_modelo.filtrar`
    + `arq_layout.dispor` — nada e compartilhado entre vistas, cada uma tem a
    propria geometria e o proprio conjunto de arestas/fluxos.
    """
    chave: str      # "arquitetura" | "schema" — vira id/atributo no HTML e no JS
    rotulo: str     # "Arquitetura" | "Schema" — texto do botao e da trilha
    cena: Cena
    modelo: Modelo

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
        # `sub[-0:]` devolve a string INTEIRA, nao vazia — sem esta guarda,
        # cabe==0 produzia "…" + texto completo, pior que nao truncar.
        sub = "\u2026" + sub[len(sub) - cabe + 1:] if cabe > 1 else "\u2026"
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


def _fluxos_html(modelo: Modelo, chave: str, oculto: bool) -> str:
    """Seletor de fluxo da vista `chave`: um botao por `Fluxo`, que acende so
    as caixas dos seus passos (`Zoom.acender`) e lista os passos EM ORDEM (a
    ordem e o conteudo do fluxo — nunca ordenar). Um passo pode citar uma VM
    que nao e produto (`evolution2037`, `n8n2037`): deliberado, ver `FLUXOS`
    em `arquitetura.py`, nao filtrado aqui.

    So `modelo.fluxos` decide se o painel existe — a vista Schema nao tem
    fluxo (fluxo e caminho de execucao, relacao de dado e outra coisa), entao
    hoje so a vista Arquitetura emite este bloco. Os ids sao sufixados por
    `chave` porque, em tese, mais de uma vista pode ter painel de fluxo na
    mesma pagina — sem sufixo, colidiriam. `oculto` marca o painel com
    `hidden` de saida quando a vista dona dele nao e a que abre.
    """
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
    hidden_attr = " hidden" if oculto else ""
    # A lista e o invariante sao montados no navegador a partir do FLUXOS,
    # so para o fluxo escolhido. Concatenar os quatro no HTML fazia cada
    # clique mostrar os passos de todos os fluxos somados.
    return (f'<div id="fluxos-{chave}"{hidden_attr}><b>Fluxos</b> '
            f'{"".join(botoes)}<button data-fluxo="">limpar</button>'
            f'<ol id="passos-{chave}" hidden></ol><p id="inv-{chave}" hidden></p></div>'
            f'<script>var FLUXOS_{chave} = {json_fluxos};</script>')


def _fluxos_script(chave: str) -> str:
    """Listener de clique do painel de fluxo da vista `chave`. Cada vista tem
    o proprio painel (ids sufixados) e a propria instancia de `Zoom`
    (`zoomInstancias[chave]`, montada em `render`) — acender/apagar tem que
    ir para o `Zoom.criar` da MESMA vista, senao o realce de fluxo de uma
    vista mexeria no zoom da outra."""
    return f"""
  var elFluxos_{chave} = document.getElementById("fluxos-{chave}");
  if (elFluxos_{chave}) {{
    elFluxos_{chave}.addEventListener("click", function (ev) {{
      var k = ev.target.getAttribute("data-fluxo");
      if (k === null) return;
      var ol = document.getElementById("passos-{chave}"), inv = document.getElementById("inv-{chave}");
      if (!k) {{
        zoomInstancias["{chave}"].apagar(); ol.hidden = true; inv.hidden = true; return;
      }}
      var f = FLUXOS_{chave}[k];
      zoomInstancias["{chave}"].acender(f.passos.map(function (p) {{ return p.no; }}));
      ol.textContent = "";
      f.passos.forEach(function (p) {{
        var li = document.createElement("li");
        li.textContent = p.faz + " — " + p.no + (p.sincrono ? "" : " (fila)");
        ol.appendChild(li);
      }});
      ol.hidden = false;
      inv.textContent = f.invariante || "";
      inv.hidden = !f.invariante;
    }});
  }}"""


def render(vistas: tuple[Vista, ...], js: str) -> str:
    """Monta a pagina inteira a partir de N `Vista`. A primeira da tupla abre
    visivel; as demais saem com `hidden`. Cada vista ganha o proprio
    `<svg id="mapa-{chave}">`, o proprio botao no alternador (`data-vista`) e
    a propria instancia de `Zoom.criar` — nada de estado, geometria ou
    arestas e compartilhado entre elas."""
    svgs, botoes = [], []
    paineis_fluxo, scripts_fluxo = [], []
    linhas_instancia, linhas_trilha = [], []
    rotulos: dict[str, str] = {}

    for i, vista in enumerate(vistas):
        ativa = i == 0
        spof_map = _spof_por_chave(vista.modelo.nos, vista.modelo.vms)
        por_pai = _agrupar_por_pai(vista.cena.caixas)
        raizes = sorted(por_pai.get(None, []), key=lambda c: c.chave)
        corpo_svg = "".join(_no_recursivo(r, por_pai, spof_map) for r in raizes)

        caixas_por_chave = {c.chave: c for c in vista.cena.caixas}
        resolvidas = []
        for a in vista.modelo.arestas:
            de = _resolver_produto(a.de, caixas_por_chave)
            para = _resolver_produto(a.para, caixas_por_chave)
            if de is not None and para is not None:
                resolvidas.append((a, de, para))
        arestas_svg = "".join(_aresta(a, de, para) for a, de, para in resolvidas)

        largura = max(vista.cena.largura, 1.0)
        altura = max(vista.cena.altura, 1.0)
        hidden_attr = "" if ativa else " hidden"
        svgs.append(
            f'<svg id="mapa-{vista.chave}" viewBox="0 0 {largura:.2f} {altura:.2f}"{hidden_attr}>\n'
            f'{corpo_svg}<g stroke="{BRAND}" stroke-width="1.5" fill="none">\n'
            f'{arestas_svg}</g>\n</svg>'
        )

        classe = ' class="ativo"' if ativa else ""
        botoes.append(f'<button data-vista="{_e(vista.chave)}"{classe}>{_e(vista.rotulo)}</button>')
        rotulos[vista.chave] = vista.rotulo

        # A vista Schema nao tem `modelo.fluxos` (fluxo e caminho de
        # execucao, nao relacao de dado) — so a vista Arquitetura emite
        # painel hoje, mas o codigo nao amarra nisso: qualquer vista com
        # fluxo ganha o proprio painel, escondido junto com o svg dela.
        fluxo_html = _fluxos_html(vista.modelo, vista.chave, oculto=not ativa)
        if fluxo_html:
            paineis_fluxo.append(fluxo_html)
            scripts_fluxo.append(_fluxos_script(vista.chave))

        linhas_instancia.append(
            f'  zoomInstancias["{vista.chave}"] = '
            f'Zoom.criar(document.getElementById("mapa-{vista.chave}"), {{}});'
        )
        linhas_trilha.append(
            f'  document.getElementById("mapa-{vista.chave}")'
            f'.addEventListener("zoom:mudou", function (ev) {{\n'
            f'    document.getElementById("trilha").textContent = ev.detail.titulo || "Revy";\n'
            f'  }});'
        )

    rotulos_json = (json.dumps(rotulos, ensure_ascii=False, sort_keys=True)
                     .replace("<", "\\u003c"))
    corpo_botoes = "".join(botoes)
    corpo_svgs = "\n".join(svgs)
    corpo_fluxos = "".join(paineis_fluxo)
    corpo_scripts_fluxo = "".join(scripts_fluxo)
    corpo_instancias = "\n".join(linhas_instancia)
    corpo_trilha = "\n".join(linhas_trilha)

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Revy — arquitetura</title>
<style>
  html,body{{margin:0;height:100%;background:{PAPER};
    font-family:system-ui,-apple-system,sans-serif;color:{INK}}}
  svg{{width:100vw;height:100vh;display:block;cursor:grab;touch-action:none}}
  /* Task 10: com duas cenas na pagina, hidden esconde a vista que nao esta
     ativa — sem esta regra, o svg{{display:block}} acima (que ja existia
     antes de haver mais de um svg) pisa a regra padrao do navegador pra
     [hidden] e as duas cenas ficam sobrepostas. */
  svg[hidden]{{display:none}}
  #alternador{{position:fixed;top:12px;left:50%;transform:translateX(-50%);
    background:{SURFACE};padding:4px;border:1px solid {LINE};border-radius:8px;
    font-size:13px;z-index:2}}
  #alternador button{{border:none;background:none;color:{INK_SOFT};cursor:pointer;
    padding:6px 14px;border-radius:6px;font-size:13px}}
  #alternador button.ativo{{background:{BRAND};color:{SURFACE}}}
  #trilha{{position:fixed;top:12px;left:12px;background:{SURFACE};padding:6px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:13px}}
  #dica{{position:fixed;bottom:12px;left:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:11px;color:{INK_SOFT}}}
  [id^="fluxos-"]{{position:fixed;top:12px;right:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:12px;max-width:280px}}
  [id^="fluxos-"] button{{font-size:11px;margin:2px 2px 0 0;border:1px solid {LINE_STRONG};
    border-radius:4px;background:{SURFACE_SOFT};color:{INK};cursor:pointer;padding:3px 7px}}
  [id^="fluxos-"] button:hover{{background:{LINE}}}
  [id^="passos-"]{{margin:6px 0 0;padding-left:18px}}
  [id^="inv-"]{{margin:6px 0 0;font-style:italic}}
  [id^="passos-"] li{{margin:2px 0}}
  [data-k-min],[data-face-ate]{{transition:opacity .1s linear}}
  [data-navegavel],[data-aresta]{{transition:opacity .15s linear}}
</style>
<div id="alternador">{corpo_botoes}</div>
<div id="trilha">Revy</div>
<div id="dica">clique numa caixa para cair dentro · <strong>Esc</strong> volta · roda dá zoom · borda grossa é SPOF, linha tracejada é aresta assíncrona, moldura tracejada é máquina (VM)</div>
{corpo_fluxos}

{corpo_svgs}

<script>
{js}
</script>
<script>
  var ROTULOS = {rotulos_json};
  var zoomInstancias = {{}};
{corpo_instancias}
{corpo_trilha}
  document.getElementById("alternador").addEventListener("click", function (ev) {{
    var alvo = ev.target.closest("[data-vista]");
    if (!alvo) return;
    mostrarVista(alvo.getAttribute("data-vista"));
  }});
  function mostrarVista(chave) {{
    var chaves = Object.keys(zoomInstancias);
    for (var i = 0; i < chaves.length; i++) {{
      var v = chaves[i];
      var svgEl = document.getElementById("mapa-" + v);
      // setAttribute, nao a propriedade `.hidden`: em SVGSVGElement (o
      // <svg> raiz) `.hidden = true` NAO reflete no atributo nem some da
      // tela neste Chrome — so aparece lendo `getAttribute`. So achado
      // abrindo no navegador; `<div>` (o painel de fluxo, abaixo) reflete
      // normalmente, so o <svg> raiz tem a quebra.
      if (svgEl) {{
        if (v !== chave) svgEl.setAttribute("hidden", ""); else svgEl.removeAttribute("hidden");
      }}
      var painel = document.getElementById("fluxos-" + v);
      if (painel) painel.hidden = (v !== chave);
      var botao = document.querySelector('[data-vista="' + v + '"]');
      if (botao) botao.className = (v === chave) ? "ativo" : "";
    }}
    var trilhaEl = document.getElementById("trilha");
    if (trilhaEl) trilhaEl.textContent = ROTULOS[chave] || "Revy";
  }}
{corpo_scripts_fluxo}
</script>
"""
