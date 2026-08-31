"""O HTML do zoom continuo: `Vista` (uma por cena) -> uma pagina SVG
auto-contida com um alternador no topo.

Task 10: a pagina passa a ter duas cenas independentes (Arquitetura e
Schema, uma `Vista` cada) no MESMO documento — um `<svg id="mapa-{chave}">`
por vista, so a primeira visivel de saida, e um `Zoom.criar(...)` (arq_zoom.js)
por vista, porque as duas nao podem dividir estado de zoom.

Task 11 (a pele): o vocabulario de forma vira marca Revy — retangulo com
filete e produto, moldura tracejada verde e maquina Fly, cilindro e banco,
elipse cinza e software de terceiro — tudo em mono, com um `<filter>` de
rabisco (feTurbulence + feDisplacementMap) aplicado SO as formas, nunca ao
texto. Por isso cada caixa agora produz DOIS pedacos de HTML, nao um: a
FORMA (rect/path/ellipse/polyline, entra na camada filtrada) e o TEXTO
(so <text>, entra numa camada sem filtro, por cima). `_no_recursivo` devolve
`(forma, texto)` e `render()` monta duas camadas por svg:

    <svg id="mapa-{chave}">
      <g class="formas" filter="url(#rabisco)"> ... todo rect/path/ellipse/polyline
      <g class="textos"> ... todo <text>, com `pointer-events:none` (CSS) —
        clique sempre acerta a forma por baixo, nunca o texto por cima.

Os dois `<g>` internos de cada caixa (data-face-ate / data-k-min) SEMPRE
existem (e' a forma fixa por caixa), mas o ATRIBUTO so aparece quando o
valor e' > 0 — nivel 1 nao tem pai pra derivar o limiar contra (arq_layout.py
deixa k_min=k_face=0.0 nesse caso), e uma caixa navegavel carregando
`data-k-min` faria o `aplicarLod` (que escreve opacity a cada quadro) brigar
com o `Zoom.acender` da Task 7 — o realce de fluxo piscaria.

`arq_zoom.js` nao le nenhum outro atributo alem de: id, data-navegavel,
data-titulo, data-k-min, data-face-ate, data-dono, data-aresta. Nao inventar
outros. `data-dono` e' a chave do no daquele grupo, e existe exatamente onde
existe data-k-min/data-face-ate — e' o que a trava de linhagem le.

Stdlib apenas. Auto-contido: nenhum `http://`/`https://` no HTML gerado —
`file://` bloqueia `fetch()`, entao o JS entra inline (`js` embutido
verbatim), sem `<script src=...>`.
"""
from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass

from arq_layout import Caixa, Cena, ALTURA_TITULO, MARGEM, banda_titulo
from arq_design import Grupo
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

# Cores de shared/brand/revy-tokens.css (tema claro), copiadas como literal —
# o HTML gerado nao importa CSS de fora (ver o learning
# 2026-08-23-tokens-de-marca-tem-fonte-unica.md). Task 11: a paleta inteira,
# nao so o verde — o desenho anterior so usava BRAND/INK/LINE, generico.
PAPER = "#f9f9f9"
SURFACE = "#ffffff"
SURFACE_RAISED = "#f4f2f1"
SURFACE_SOFT = "#efeceb"
INK = "#1b1b1b"
INK_SOFT = "#57514f"
INK_MUTED = "#6b625f"
LINE = "#ded8d9"
LINE_STRONG = "#cdc6c4"
BRAND = "#1f4d3a"
BRAND_TINT = "rgba(31, 77, 58, .09)"
BRAND_LINE = "rgba(31, 77, 58, .32)"
DANGER = "#b42318"
MONO = 'ui-monospace,"SF Mono","Consolas",monospace'
BRAND_FONT = '"Newsreader",Georgia,serif'


def _fonte_titulo(c: Caixa) -> float:
    """Fonte proporcional a CAIXA, nunca ao nivel.

    Amarrar ao nivel produzia 26 no nivel 1 — numa cena de 11 mil de largura,
    3,6px na tela, ilegivel. O texto de um filho vive nas coordenadas absolutas
    do pai (sem transform de escala), entao a unica referencia que faz sentido
    e o tamanho da propria caixa: assim o titulo fica legivel exatamente quando
    a caixa enche a tela, em qualquer profundidade.
    """
    # O teto pela FAIXA e o que impede o titulo de invadir os filhos: eles
    # comecam logo abaixo dela (arq_layout.banda_titulo).
    banda = banda_titulo(max(0.0, c.w - MARGEM * 2))

    # ...e o teto pelo COMPRIMENTO e o que impede o titulo de invadir o
    # VIZINHO. Os tres tetos acima olham so a geometria da caixa, entao um
    # titulo longo numa caixa estreita transbordava pela direita: achado no
    # navegador em 30/08, "Clientes HTTP de outros produtos" saindo por cima
    # da caixa "Projecao do Control" ao lado. Quatro dos 81 titulos da cena
    # real estouravam, todos entre 15% e 18% — o teto so morde nesses, os
    # outros 77 continuam com a fonte que ja tinham.
    #
    # 0.6 e' o avanco de uma fonte monoespacada (largura do glifo / em);
    # MONO e' mono em toda a pagina, entao a conta e' exata, nao estimativa.
    # A margem de folga usa a mesma MARGEM do layout.
    largura_util = max(0.0, c.w - MARGEM)
    por_comprimento = largura_util / (len(c.titulo) * 0.6) if c.titulo else float("inf")

    # TRUNCA em vez de arredondar. `round(8.26, 1)` da 8.3, e 8.3 volta a
    # estourar a caixa por uma fracao — o teto acima e' exato, o arredondamento
    # e' que o desfazia (dois dos quatro titulos continuavam saindo). Truncar
    # nunca AUMENTA uma fonte, entao nao cria estouro em lugar nenhum.
    teto = min(c.w * 0.055, c.h * 0.30, banda * 0.62, por_comprimento)
    return max(1.5, math.floor(teto * 10) / 10)


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


# --------------------------------------------------------------------------
# Vocabulario de forma (Task 11): retangulo com filete = produto Revy, moldura
# tracejada verde = maquina Fly, cilindro = banco, elipse cinza = software de
# terceiro. So o que E' marca leva verde (nome/moldura da VM, alternador
# ativo) — a caixa de produto fica com filete NEUTRO (tinta, nao verde), e so
# fica vermelha quando o DADO diz spof=True. Nunca "vermelho porque e
# importante".
# --------------------------------------------------------------------------

def _rect_no(c: Caixa, spof: bool) -> str:
    """A caixa de um no. `c.forma` troca o DESENHO, nunca a cor.

    Vocabulario TECNICO (31/08, a pedido do dono): ele le o desenho pela
    forma antes de ler o texto, e caixa toda igual obriga a ler cada legenda
    pra saber o que e' o que — ai o diagrama vira lista. A forma diz o que a
    coisa E' (fila, worker, cache, browser); o `papel` continua dizendo de
    que dominio ela e'. Sao perguntas diferentes.

    Regra que nao se quebra: forma sai do DADO (`forma:` escrito a mao em
    `arquitetura.py`), nunca de importancia. E cor continua sendo so' o SPOF —
    nada de "vermelho porque e' importante", nem de verde pra decorar.
    """
    cor = DANGER if spof else INK
    largura = 2.4 if spof else 1.0
    base = (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="4" fill="{SURFACE}" stroke="{cor}" stroke-width="{largura}" vector-effect="non-scaling-stroke"/>'
    )
    return base + _marca_tecnica(c, cor)


def _marca_tecnica(c: Caixa, cor: str) -> str:
    """O tracinho que diferencia a forma tecnica, desenhado SOBRE a caixa.

    Marca, e nao silhueta trocada, por dois motivos praticos: o layout ja
    calculou largura e altura contando com um retangulo (mudar a silhueta
    moveria o texto e as pontas de aresta), e a marca some junto com a caixa
    no LOD sem tratamento nenhum. Tudo em `vector-effect="non-scaling-stroke"`
    pra a espessura nao inchar no zoom.
    """
    if not c.forma:
        return ""
    x, y, w, h = c.x, c.y, c.w, c.h
    fina = f' stroke="{cor}" stroke-width="1.0" fill="none" vector-effect="non-scaling-stroke"'

    if c.forma == "fila":
        # Tres divisorias na base = os lugares da fila. E' a unica forma que
        # aparece nos quatro produtos (toda outbox do monorepo), entao ela
        # precisa ser reconhecivel de longe e barata de desenhar.
        passo = w / 12.0
        base_y = y + h
        linhas = "".join(
            f'<line x1="{x + passo * (i + 1):.2f}" y1="{base_y - h * 0.16:.2f}" '
            f'x2="{x + passo * (i + 1):.2f}" y2="{base_y:.2f}"{fina}/>'
            for i in range(3))
        return linhas

    if c.forma == "worker":
        # Duas barras verticais junto das laterais: o simbolo classico de
        # "processo predefinido" de fluxograma. Quer dizer que aquilo roda
        # sozinho, num laco proprio, e nao quando alguem chama.
        d = min(w * 0.03, 6.0)
        return (f'<line x1="{x + d:.2f}" y1="{y:.2f}" x2="{x + d:.2f}" y2="{y + h:.2f}"{fina}/>'
                f'<line x1="{x + w - d:.2f}" y1="{y:.2f}" x2="{x + w - d:.2f}" y2="{y + h:.2f}"{fina}/>')

    if c.forma == "cache":
        # Boca de cilindro TRACEJADA no topo: guarda como um banco, mas o
        # tracejado diz que pode sumir a qualquer momento e ninguem perde
        # dado por isso (TTL do Pixel, storage_state do Playwright).
        rx = w / 2
        ry = min(max(rx * 0.10, 3.0), 14.0)
        ry = min(ry, max(1.0, h / 2 - 1))
        return (f'<path d="M{x:.2f},{y + ry:.2f} a{rx:.2f},{ry:.2f} 0 0 1 {w:.2f},0" '
                f'stroke="{cor}" stroke-width="1.0" fill="none" stroke-dasharray="5 4"'
                f' vector-effect="non-scaling-stroke"/>')

    if c.forma == "browser":
        # Barra de janela no topo: ali dentro sobe Chromium DE VERDADE. E' a
        # forma que separa o RPA de todo o resto do monorepo, e por isso ela
        # e' a mais literal das quatro.
        bh = min(h * 0.10, 10.0)
        r = min(bh * 0.22, 2.0)
        pontos = "".join(
            f'<circle cx="{x + bh * (0.7 + i * 0.75):.2f}" cy="{y + bh / 2:.2f}" '
            f'r="{r:.2f}" fill="{cor}"/>' for i in range(3))
        return (f'<line x1="{x:.2f}" y1="{y + bh:.2f}" x2="{x + w:.2f}" '
                f'y2="{y + bh:.2f}"{fina}/>' + pontos)

    raise ValueError(f"forma tecnica desconhecida: {c.forma!r} em {c.chave}")


def _rect_vm(c: Caixa) -> str:
    # Moldura, nao caixa: fill="none" e tracejado, na cor da marca. A VM e
    # infra, nao produto — o dono pediu que ela fique visualmente distinta
    # (blast radius: uma maquina caindo leva tudo que esta dentro dela
    # junto). E' o UNICO lugar (com o nome da VM e o alternador ativo) onde
    # o verde da marca aparece — ver docstring do modulo.
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="10" fill="none" stroke="{BRAND_LINE}" stroke-width="1.2"'
        f' vector-effect="non-scaling-stroke" stroke-dasharray="8 5"/>'
    )


def _cilindro(c: Caixa) -> str:
    """Grupo de banco (Schema: `tipo` "postgres" ou "banco-proprio"; e
    `suite-pg` tambem na vista Arquitetura, onde continua com `contem`
    vazio). Corpo + "costura" (arco de tras, mais claro) e o truque classico
    de desenhar cilindro em SVG so com dois `<path>`."""
    x, y, w, h = c.x, c.y, c.w, c.h
    rx = w / 2
    # A curvatura do "boca" do cilindro tem que acompanhar a LARGURA (e' o
    # que da o efeito 3D visto de frente), nao a altura — um grupo de banco
    # de nivel 1 e' tipicamente bem mais largo que alto, e um teto derivado
    # de `h` (como era antes) ficava achatado quase reto nesses casos.
    ry = min(max(rx * 0.16, 4.0), 40.0)
    ry = min(ry, max(1.0, h / 2 - 1))
    cy_topo = y + ry
    cy_base = y + h - ry
    corpo = (
        f'<path d="M{x:.2f},{cy_topo:.2f} '
        f'a{rx:.2f},{ry:.2f} 0 0 1 {w:.2f},0 '
        f'V{cy_base:.2f} '
        f'a{rx:.2f},{ry:.2f} 0 0 1 {-w:.2f},0 Z" '
        f'fill="{SURFACE}" stroke="{INK}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>'
    )
    costura = (
        f'<path d="M{x:.2f},{cy_topo:.2f} a{rx:.2f},{ry:.2f} 0 0 0 {w:.2f},0" '
        f'fill="none" stroke="{LINE_STRONG}" stroke-width="1" vector-effect="non-scaling-stroke"/>'
    )
    return corpo + costura


def _forma_roda(c: Caixa, vm: Vm) -> str:
    """Uma VM de `contem` vazio mas `roda` preenchido (motor2037, n8n2037,
    evolution2037) ganha UMA forma interna com esse rotulo — elipse se
    `terceiro` (software que nao e Revy), retangulo se nao (o worker
    Playwright do proprio Motor). So chamada quando a VM nao tem filho
    nenhum: e a unica forma interna que ela vai ter."""
    pad = MARGEM * 0.9
    ix = c.x + pad
    iy = c.y + ALTURA_TITULO + pad * 0.7
    iw = max(1.0, c.w - pad * 2)
    ih = max(1.0, c.h - ALTURA_TITULO - pad * 1.4)
    if vm.terceiro:
        rx, ry = iw / 2, ih / 2
        return (f'<ellipse cx="{ix + rx:.2f}" cy="{iy + ry:.2f}" rx="{rx:.2f}" '
                f'ry="{ry:.2f}" fill="{SURFACE_SOFT}" stroke="{INK}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>')
    return (f'<rect x="{ix:.2f}" y="{iy:.2f}" width="{iw:.2f}" height="{ih:.2f}" '
            f'rx="4" fill="{SURFACE}" stroke="{INK}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>')


def _rotulo_roda(c: Caixa, vm: Vm) -> str:
    fonte = max(3.0, min(round(min(c.w, c.h) * 0.045, 1), 9.0))
    cx = c.x + c.w / 2
    cy = c.y + ALTURA_TITULO + (c.h - ALTURA_TITULO) / 2
    return (f'<text x="{cx:.2f}" y="{cy:.2f}" font-size="{fonte}" '
            f'text-anchor="middle">{html.escape(vm.roda)}</text>')


def _fonte_rotulo_grupo(c: Caixa, largura_cena: float) -> float:
    """Uma moldura de grupo (VM, banco) leva ETIQUETA, nao titulo de caixa.

    `_fonte_titulo` deriva da largura da caixa, e para uma caixa isso esta
    certo: mantem o titulo do mesmo tamanho na tela quando a caixa enche a
    tela, em qualquer profundidade. Mas a moldura da `app2037` ocupa 62% da
    cena, e a mesma regra dava 347 unidades — 51px na tela, contra 6px do
    nome do Catalogo ao lado. Isso nao e hierarquia, e um grito.

    A moldura nao e' o assunto: ela e' o contorno em volta do assunto. Entao
    a etiqueta sai da CENA, igual para todas as molduras, e so encolhe se
    nao couber na largura da propria moldura.
    """
    alvo = largura_cena * 0.0075
    cabe = (c.w - largura_cena * 0.004) / max(1, len(c.titulo)) / 0.60
    banda = banda_titulo(max(0.0, c.w - MARGEM * 2), 0.02)
    return max(1.5, round(min(alvo, cabe, c.h * 0.30, banda * 0.55), 1))


def _face(c: Caixa, spof: bool, largura_cena: float) -> str:
    """Titulo + subtitulo (+ SPOF) de uma caixa. So texto — nunca teve forma,
    entao nao precisou mudar de camada com a Task 11."""
    fonte_titulo = (
        _fonte_rotulo_grupo(c, largura_cena) if c.tipo == "vm"
        else _fonte_titulo(c)
    )
    fonte_sub = round(max(1.2, fonte_titulo * 0.55), 1)
    eh_grupo = c.tipo == "vm"
    px = c.x + fonte_titulo * 0.6
    if eh_grupo:
        py_titulo = c.y + fonte_titulo * 1.25
    else:
        # Na FAIXA RESERVADA do topo, sempre. Centrar na vertical ficava mais
        # bonito com o interior fechado, mas `arq_layout` reserva ALTURA_TITULO
        # no topo e comeca os filhos ABAIXO dela: fora dessa faixa o titulo cai
        # em cima dos filhos. E como face e interior fazem crossfade (as duas
        # rampas se cruzam em 50/50), nao e um quadro — e um intervalo inteiro
        # de zoom com os dois sobrepostos. Foi o que aconteceu com "Workers
        # assincronos" por cima dos quatro workers.
        py_titulo = c.y + fonte_titulo * 1.15
    py_sub = py_titulo + fonte_sub * 1.7
    # Cortar na largura: a `nota` de uma VM tem ~200 caracteres e sem isso ela
    # sai numa linha unica por cima de tudo. 0.52em por caractere e a media.
    largura_util = c.w - fonte_titulo * 1.2
    if eh_grupo:
        # Uma moldura e larga justamente porque contem coisas: deixar a nota
        # usar a largura INTEIRA dela e' atravessar por cima dos produtos que
        # estao dentro. Etiqueta de moldura e etiqueta, nao paragrafo.
        largura_util *= 0.34
    cabe = max(0, int(largura_util / (fonte_sub * 0.52)))
    sub = c.subtitulo
    if len(sub) > cabe:
        sub = sub[:max(0, cabe - 1)] + "…"

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
            f'font-weight="600" fill="{DANGER}">SPOF</text>'
        )

    atributo = (
        f' data-face-ate="{c.k_face:.3f}" data-dono="{html.escape(c.chave)}"'
        if c.k_face > 0 else ""
    )
    return f"<g{atributo}>" + "".join(partes) + "</g>"


def _item_forma(c: Caixa) -> str:
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="2" fill="{SURFACE_SOFT}" stroke="{LINE_STRONG}" stroke-width=".6" vector-effect="non-scaling-stroke"/>'
    )


def _item_texto(c: Caixa) -> str:
    fonte_titulo, fonte_sub = 4.2, 3.0
    # Mesmo corte da face: o subtitulo de um item e o `arquivo:linha`, que
    # facilmente passa da largura da caixa.
    cabe = max(0, int((c.w - 8) / (fonte_sub * 0.52)))
    sub = c.subtitulo
    if len(sub) > cabe:
        # `sub[-0:]` devolve a string INTEIRA, nao vazia — sem esta guarda,
        # cabe==0 produzia "…" + texto completo, pior que nao truncar.
        sub = "…" + sub[len(sub) - cabe + 1:] if cabe > 1 else "…"
    return (
        f'<text x="{c.x + 4:.2f}" y="{c.y + 5.5:.2f}" font-size="{fonte_titulo}">'
        f'{html.escape(c.titulo)}</text>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 9.5:.2f}" font-size="{fonte_sub}" '
        f'fill="{INK_SOFT}">{html.escape(sub)}</text>'
    )


def _no_recursivo(caixa: Caixa, por_pai: dict, spof_map: dict,
                   grupos_por_chave: dict[str, Vm],
                   largura_cena: float) -> tuple[str, str]:
    """Devolve `(forma, texto)` — a caixa inteira dividida nas duas camadas
    que o filtro de rabisco exige (ver docstring do modulo). Recursivo: cada
    filho contribui a propria forma e o proprio texto pras duas somas."""
    filhos = por_pai.get(caixa.chave, [])
    subs_no = [f for f in filhos if f.tipo in ("no", "vm")]
    itens = [f for f in filhos if f.tipo == "item"]
    spof = spof_map.get(caixa.chave, False)

    interior_forma = "".join(_item_forma(i) for i in itens)
    interior_texto = "".join(_item_texto(i) for i in itens)
    for s in subs_no:
        f_forma, f_texto = _no_recursivo(s, por_pai, spof_map, grupos_por_chave,
                                         largura_cena)
        interior_forma += f_forma
        interior_texto += f_texto

    extra_forma = ""
    extra_texto = ""
    if caixa.tipo == "vm":
        vm = grupos_por_chave.get(caixa.chave)
        eh_banco = vm is not None and vm.tipo in ("postgres", "banco-proprio")
        retangulo = _cilindro(caixa) if eh_banco else _rect_vm(caixa)
        if vm is not None and vm.roda and not filhos:
            extra_forma = _forma_roda(caixa, vm)
            extra_texto = _rotulo_roda(caixa, vm)
    else:
        retangulo = _rect_no(caixa, spof)

    # `data-dono` anda junto do limiar: sem ele o LOD e' so escala, e caixas
    # irmas de tamanho parecido abrem o interior JUNTAS — entrar no Chatbot
    # mostrava o interior do Portal ao lado. Ver a trava de linhagem em
    # arq_zoom.js.
    kmin_attr = (
        f' data-k-min="{caixa.k_min:.3f}" data-dono="{html.escape(caixa.chave)}"'
        if caixa.k_min > 0 else ""
    )

    # `data-x/y/w/h`: a geometria ORIGINAL da caixa, pra o JS nao precisar de
    # getBBox nem de decifrar o <rect> (uma VM-banco nem tem rect, tem path).
    # Arrastar soma um deslocamento a estes numeros; o valor no atributo nunca
    # muda, entao "voltar ao automatico" e' so jogar o deslocamento fora.
    geo = (f' data-x="{caixa.x:.2f}" data-y="{caixa.y:.2f}"'
           f' data-w="{caixa.w:.2f}" data-h="{caixa.h:.2f}"')
    chave_esc = html.escape(caixa.chave)
    forma = (
        f'<g id="{chave_esc}" data-titulo="{html.escape(caixa.titulo)}" data-navegavel{geo}>'
        + retangulo + extra_forma
        + f"<g{kmin_attr}>{interior_forma}</g>"
        + "</g>"
    )
    # `data-texto-de` casa esta camada com a forma de mesma chave. Forma e
    # texto vivem em <g> IRMAOS (o filtro de rabisco so pode pegar a forma —
    # ver docstring do modulo), entao mover uma caixa e' mover DOIS grupos; sem
    # marca, o texto ficaria para tras. O <g> do texto nao pode levar `id`:
    # `svg.getElementById` e o `voarPara` acertariam o alvo errado.
    texto = (
        f'<g data-texto-de="{chave_esc}">' + _face(caixa, spof, largura_cena) + extra_texto
        + f"<g{kmin_attr}>{interior_texto}</g>"
        + "</g>"
    )
    return forma, texto


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


# --------------------------------------------------------------------------
# Arestas ortogonais (Task 11): no maximo dois cotovelos, saindo pela borda
# mais proxima da caixa de destino — nunca mais centro a centro. Ligar dois
# pontos com no maximo um "meio" perpendicular (cotovelo duplo) garante que
# TODO segmento e' horizontal ou vertical por construcao, nunca por sorte de
# arredondamento.
# --------------------------------------------------------------------------

_LADO_OPOSTO = {"direita": "esquerda", "esquerda": "direita", "cima": "baixo", "baixo": "cima"}


def _lado_saida(de: Caixa, para: Caixa) -> str:
    dx = (para.x + para.w / 2) - (de.x + de.w / 2)
    dy = (para.y + para.h / 2) - (de.y + de.h / 2)
    if abs(dx) >= abs(dy):
        return "direita" if dx >= 0 else "esquerda"
    return "baixo" if dy >= 0 else "cima"


def _ponto_borda(c: Caixa, lado: str, deslocamento: float) -> tuple[float, float]:
    if lado == "direita":
        return c.x + c.w, c.y + c.h / 2 + deslocamento
    if lado == "esquerda":
        return c.x, c.y + c.h / 2 + deslocamento
    if lado == "baixo":
        return c.x + c.w / 2 + deslocamento, c.y + c.h
    return c.x + c.w / 2 + deslocamento, c.y  # "cima"


def _pontos_ortogonais(p1: tuple[float, float], lado1: str,
                        p2: tuple[float, float]) -> list[tuple[float, float]]:
    x1, y1 = p1
    x2, y2 = p2
    if lado1 in ("esquerda", "direita"):
        xm = (x1 + x2) / 2
        return [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
    ym = (y1 + y2) / 2
    return [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]


def _offsets_de_saida(resolvidas: list) -> dict[int, float]:
    """Quando duas arestas saem da MESMA borda da MESMA caixa, desloca o
    ponto de saida pra elas nao se sobreporem — espalhadas em torno do
    centro da borda, na ordem em que aparecem (`resolvidas` ja vem
    deterministico: `arq_modelo.carregar` ordena as arestas por
    (de, para, protocolo))."""
    PASSO = 9.0
    grupos: dict[tuple[str, str], list[int]] = {}
    for idx, (a, de, para) in enumerate(resolvidas):
        lado = _lado_saida(de, para)
        grupos.setdefault((de.chave, lado), []).append(idx)
    offsets: dict[int, float] = {}
    for idxs in grupos.values():
        n = len(idxs)
        for pos, idx in enumerate(idxs):
            offsets[idx] = (pos - (n - 1) / 2) * PASSO
    return offsets


def _pontos_da_aresta(de: Caixa, para: Caixa, deslocamento: float) -> list[tuple[float, float]]:
    lado_de = _lado_saida(de, para)
    lado_para = _LADO_OPOSTO[lado_de]
    p1 = _ponto_borda(de, lado_de, deslocamento)
    p2 = _ponto_borda(para, lado_para, 0.0)
    return _pontos_ortogonais(p1, lado_de, p2)


def _sem_rede(a: Aresta) -> bool:
    """A aresta fica dentro do mesmo produto?

    Isso decide a COR. `retry=False` significa risco quando a chamada
    atravessa fronteira de processo: se o outro lado esta fora do ar, o
    evento se perde. Dentro do mesmo produto e' funcao chamando funcao — nao
    ha o que retentar, e nao ha risco nenhum a sinalizar. Pintar as duas
    coisas de vermelho fazia o interior do Chatbot sair inteiro em vermelho
    e o vermelho parar de querer dizer qualquer coisa.
    """
    return a.de.split(".")[0] == a.para.split(".")[0]


def _marcas_da_aresta(a: Aresta, de: Caixa, para: Caixa, idx: int) -> str:
    """Atributos que `arq_zoom.js` le pra decidir a opacidade de cada seta.

    `data-de`/`data-para` sao os ids ABSOLUTOS (com prefixo de VM), nao as
    chaves cruas de `Aresta`. O JS precisa perguntar "esta ponta esta dentro
    do no em foco?", que e' teste de prefixo — e `chatbot-api.workers` nunca
    e' prefixo de `app2037.chatbot-api.workers`. Resolver isso no JS por
    sufixo (como `Zoom.acender` faz) funciona pro caso raso e erra assim que
    a pergunta e' de linhagem; aqui o render ja sabe a resposta certa, entao
    ele escreve.

    `data-interna` marca aresta que nao cruza fronteira de produto — as 20
    do Chatbot. Sao elas que nascem apagadas e so acendem sob o mouse.

    Estes tres vao na forma E no rotulo, pra os dois acenderem juntos.
    `data-aresta` NAO: o valor dele carrega um `>` literal (`de->para`), e
    dois testes leem o SVG com regex `<text[^>]*...>` — o `[^>]*` para no
    sinal de dentro do atributo. Alem disso `data-aresta` e' o que
    `test_5_vermelho_so_em_aresta_sem_retry_e_no_spof` conta pra saber
    quantas arestas existem; repetir no rotulo contaria cada uma duas vezes.
    Por isso o seletor do JS e' `[data-de]`, nao `[data-aresta]`.
    """
    interna = ' data-interna=""' if _sem_rede(a) else ""
    # `data-i` e' o indice da aresta na lista resolvida. A forma e o rotulo
    # levam o MESMO indice: e' por ele que o JS acha os dois pedacos da mesma
    # seta ao recalcular o tracado enquanto voce arrasta uma caixa.
    return (f' data-i="{idx}" data-de="{html.escape(de.chave)}"'
            f' data-para="{html.escape(para.chave)}"{interna}')


def _aresta_forma(a: Aresta, de: Caixa, para: Caixa, deslocamento: float, idx: int) -> str:
    pontos = _pontos_da_aresta(de, para, deslocamento)
    marca = f"{html.escape(a.de)}->{html.escape(a.para)}"
    marcador = "seta-sem" if not a.retry and not _sem_rede(a) else "seta"
    tracejado = ' stroke-dasharray="6 4"' if not a.sincrono else ""
    # Vermelho SO onde o dado manda: `retry=False` E atravessando produto.
    # Nada de "vermelho porque e importante" — ver docstring do modulo.
    cor = f' stroke="{DANGER}"' if not a.retry and not _sem_rede(a) else ""
    txt_pontos = " ".join(f"{x:.2f},{y:.2f}" for x, y in pontos)
    return (
        f'<polyline data-aresta="{marca}" points="{txt_pontos}"'
        f'{_marcas_da_aresta(a, de, para, idx)}{tracejado}{cor} '
        f'marker-end="url(#{marcador})"/>'
    )


def _aresta_texto(a: Aresta, de: Caixa, para: Caixa, deslocamento: float, idx: int) -> str:
    # Rotulo e' SO o protocolo — sincrono/assincrono ja esta no tracejado da
    # forma, e "sem retry" ja esta na cor vermelha; repetir em texto era
    # ruido (e a palavra "retry" nunca aparece em texto nenhum).
    pontos = _pontos_da_aresta(de, para, deslocamento)
    mx = (pontos[1][0] + pontos[2][0]) / 2
    my = (pontos[1][1] + pontos[2][1]) / 2
    cor = DANGER if not a.retry and not _sem_rede(a) else INK_SOFT
    # `class="protocolo"` so pra marcar QUAL <text> e' rotulo de aresta —
    # arquivo:linha de item (app/cloud_retry.py) legitimamente contem a
    # palavra "retry" em outro lugar da cena, entao o teste que garante
    # "rotulo de aresta nunca diz retry" precisa mirar so' nestes.
    # "chamada" e' o protocolo mudo: dentro do mesmo processo, uma funcao
    # chamando outra. Rotular todas fazia a palavra aparecer catorze vezes no
    # interior do Chatbot, sobrepondo as proprias linhas — e nao dizia nada
    # que a seta ja nao dissesse. O rotulo fica so onde ele acrescenta:
    # http, outbox, tcp, timer.
    if a.protocolo == "chamada":
        return ""
    # As mesmas marcas da forma: o rotulo tem que acender e apagar JUNTO com
    # a seta dele. Sem isso, esconder as arestas internas deixaria as
    # palavras soltas boiando no vazio, apontando pra nada.
    return (f'<text{_marcas_da_aresta(a, de, para, idx)} x="{mx:.2f}" y="{my:.2f}" '
            f'font-size="8" fill="{cor}" class="protocolo">'
            f'{html.escape(a.protocolo)}</text>')


def _amostra(tok) -> str:
    """A amostra tem que MOSTRAR o token, nao descrever. Cor vira mancha,
    raio vira canto, fonte vira frase, sombra vira sombra."""
    if tok.tipo == "cor":
        return f'<span class="dsw" style="background:{_e(tok.valor)}"></span>'
    if tok.tipo == "forma":
        return (f'<span class="dsw dbox" style="border-radius:{_e(tok.valor)}">'
                f'</span>')
    if tok.tipo == "fonte":
        return (f'<span class="dfonte" style="font-family:{_e(tok.valor)}">'
                f'Revy 123</span>')
    if tok.tipo == "sombra":
        return f'<span class="dsw dbox" style="box-shadow:{_e(tok.valor)}"></span>'
    return '<span class="dsw dbox"></span>'


def _design_html(grupos: tuple[Grupo, ...], oculto: bool) -> str:
    """A vista Design: os tokens de `shared/brand/revy-tokens.css`.

    Nao e' uma cena de caixas, entao nao e' uma `Vista` com `Cena`/`Modelo` —
    e' HTML, e o alternador trata as duas coisas do mesmo jeito (ver
    `mostrarVista`). Forcar isso a virar SVG so pra caber no molde daria uma
    pagina pior por simetria.
    """
    if not grupos:
        return ""
    secoes = []
    for g in grupos:
        chips = []
        for tok in g.tokens:
            # A heranca so aparece quando existe: `--brand: var(--green-700)`
            # diz mais que `--brand: #1f4d3a`, porque diz de ONDE vem.
            heranca = (f'<em class="dher">{_e(tok.bruto)}</em>'
                       if tok.bruto != tok.valor else "")
            chips.append(
                f'<div class="dchip">{_amostra(tok)}'
                f'<code>{_e(tok.nome)}</code>'
                f'<em>{_e(tok.valor)}</em>{heranca}</div>'
            )
        secoes.append(f'<section><h3>{_e(g.titulo)}</h3>'
                      f'<div class="dchips">{"".join(chips)}</div></section>')
    hidden_attr = " hidden" if oculto else ""
    return (f'<div id="painel-design"{hidden_attr}>'
            f'<p class="dfonte-arq">lido de <code>shared/brand/revy-tokens.css</code>'
            f' na geracao — nao copiado. Editar la muda esta pagina.</p>'
            f'{"".join(secoes)}</div>')


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
    # `<details>` fechado de saida: aberto, o painel cobria as molduras da
    # direita (evolution2037, motor2037) justamente na visao de escopo, que e'
    # a que precisa estar desobstruida. Elemento nativo, sem JS.
    return (f'<details id="fluxos-{chave}"{hidden_attr}>'
            f'<summary>Fluxos</summary>'
            f'{"".join(botoes)}<button data-fluxo="">limpar</button>'
            f'<ol id="passos-{chave}" hidden></ol><p id="inv-{chave}" hidden></p></details>'
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


def _defs_compartilhadas() -> str:
    """Um `<filter id="rabisco">` por DOCUMENTO (nao por vista): as duas
    vistas dividem o mesmo filtro e os mesmos marcadores de seta, referidos
    por `url(#...)` de qualquer um dos dois `<svg>` — ids sao globais no
    documento, nao escopados por raiz de svg. Fica num `<svg>` proprio,
    0x0, so pra hospedar `<defs>`: nao pertence a nenhuma das duas cenas.

    `feTurbulence`/`feDisplacementMap` ganham id proprio (`rabisco-*`)
    porque `arq_zoom.js` reescreve `baseFrequency`/`scale` a cada quadro,
    a partir do `k` — ver a docstring de `aplicarLod` la."""
    return (
        '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
        "<defs>"
        '<filter id="rabisco" x="-3%" y="-3%" width="106%" height="106%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.028" numOctaves="2" '
        'seed="9" result="n" id="rabisco-turbulencia"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="2.8" '
        'xChannelSelector="R" yChannelSelector="G" id="rabisco-deslocamento"/>'
        "</filter>"
        f'<marker id="seta" markerWidth="9" markerHeight="8" refX="7.2" refY="3.2" orient="auto">'
        f'<path d="M0.4,0.4 L7,3.2 L0.4,6" fill="none" stroke="{INK_SOFT}" stroke-width="1.2"/>'
        "</marker>"
        f'<marker id="seta-sem" markerWidth="9" markerHeight="8" refX="7.2" refY="3.2" orient="auto">'
        f'<path d="M0.4,0.4 L7,3.2 L0.4,6" fill="none" stroke="{DANGER}" stroke-width="1.2"/>'
        "</marker>"
        "</defs></svg>"
    )


# As formas tecnicas que a legenda desenha. `_marca_tecnica` levanta em
# forma desconhecida e `test_toda_forma_tecnica_usada_esta_na_legenda` liga as
# duas pontas: vocabulario sem legenda e' codigo secreto, e o dono le o
# desenho pela forma antes de ler o texto.
FORMAS_TECNICAS: frozenset[str] = frozenset({"fila", "worker", "cache", "browser"})


def _legenda_html() -> str:
    """A caixa de legenda do vocabulario (mockup aprovado). Conteudo fixo —
    as formas sao o contrato desta pagina, nao dado do modelo — entao nao ha
    nada aqui pra derivar de `Modelo`. Fica dentro do MESMO filtro
    compartilhado pra combinar com o resto do desenho.

    Duas colunas: a esquerda diz O QUE A CAIXA E' no mundo (produto, maquina,
    terceiro, banco), a direita, o que ela E' TECNICAMENTE (fila, worker,
    cache, browser) mais o que as setas querem dizer. As duas perguntas sao
    diferentes, e por isso as duas colunas existem.
    """
    return f'''<div id="legenda"><b>Vocabulário</b>
<svg viewBox="0 0 268 214" width="268" height="214">
<g filter="url(#rabisco)">
<rect x="4" y="4" width="30" height="18" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<rect x="4" y="30" width="30" height="18" rx="8" fill="none" stroke="{BRAND_LINE}" stroke-width="1.3" stroke-dasharray="5 4"/>
<ellipse cx="19" cy="66" rx="15" ry="9" fill="{SURFACE_SOFT}" stroke="{INK}" stroke-width="1.3"/>
<path d="M4,90 a15,4 0 0 1 30,0 v14 a15,4 0 0 1 -30,0 z" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<line x1="168" y1="14" x2="198" y2="14" stroke="{INK_SOFT}" stroke-width="1.2" marker-end="url(#seta)"/>
<line x1="168" y1="34" x2="198" y2="34" stroke="{INK_SOFT}" stroke-width="1.2" stroke-dasharray="5 4" marker-end="url(#seta)"/>
<rect x="164" y="52" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{DANGER}" stroke-width="2.4"/>
</g>
<text x="42" y="17" font-size="9">produto Revy</text>
<text x="42" y="43" font-size="9">máquina Fly</text>
<text x="42" y="70" font-size="9">software de terceiro</text>
<text x="42" y="101" font-size="9">banco</text>
<text x="204" y="17" font-size="9">síncrono</text>
<text x="204" y="37" font-size="9">assíncrono</text>
<text x="200" y="63" font-size="9">SPOF</text>
<g filter="url(#rabisco)">
<rect x="4" y="126" width="30" height="18" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<line x1="11.5" y1="141" x2="11.5" y2="144" stroke="{INK}" stroke-width="1"/>
<line x1="19" y1="141" x2="19" y2="144" stroke="{INK}" stroke-width="1"/>
<line x1="26.5" y1="141" x2="26.5" y2="144" stroke="{INK}" stroke-width="1"/>
<rect x="4" y="150" width="30" height="18" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<line x1="8" y1="150" x2="8" y2="168" stroke="{INK}" stroke-width="1"/>
<line x1="30" y1="150" x2="30" y2="168" stroke="{INK}" stroke-width="1"/>
<rect x="4" y="174" width="30" height="18" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<path d="M4,177 a15,3 0 0 1 30,0" fill="none" stroke="{INK}" stroke-width="1" stroke-dasharray="4 3"/>
<rect x="4" y="198" width="30" height="18" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="1.3"/>
<line x1="4" y1="203" x2="34" y2="203" stroke="{INK}" stroke-width="1"/>
<circle cx="7.5" cy="200.5" r="1" fill="{INK}"/>
<circle cx="11" cy="200.5" r="1" fill="{INK}"/>
<circle cx="14.5" cy="200.5" r="1" fill="{INK}"/>
</g>
<text x="42" y="139" font-size="9">fila (outbox)</text>
<text x="42" y="163" font-size="9">worker</text>
<text x="42" y="187" font-size="9">cache</text>
<text x="42" y="211" font-size="9">browser (RPA)</text>
</svg></div>'''


def render(vistas: tuple[Vista, ...], js: str,
           tokens: tuple[Grupo, ...] = ()) -> str:
    """Monta a pagina inteira a partir de N `Vista`. A primeira da tupla abre
    visivel; as demais saem com `hidden`. Cada vista ganha o proprio
    `<svg id="mapa-{chave}">`, o proprio botao no alternador (`data-vista`) e
    a propria instancia de `Zoom.criar` — nada de estado, geometria ou
    arestas e compartilhado entre elas.

    Task 11: cada svg tem DUAS camadas — `<g class="formas" filter=...>`
    (todo rect/path/ellipse/polyline, inclusive as arestas) e
    `<g class="textos">` (todo <text>, sem filtro — CSS `pointer-events:none`
    faz o clique sempre acertar a forma por baixo)."""
    svgs, botoes = [], []
    paineis_fluxo, scripts_fluxo = [], []
    linhas_instancia, linhas_trilha = [], []
    rotulos: dict[str, str] = {}

    design_html = _design_html(tokens, oculto=True)

    for i, vista in enumerate(vistas):
        ativa = i == 0
        spof_map = _spof_por_chave(vista.modelo.nos, vista.modelo.vms)
        por_pai = _agrupar_por_pai(vista.cena.caixas)
        raizes = sorted(por_pai.get(None, []), key=lambda c: c.chave)
        grupos_por_chave: dict[str, Vm] = {v.chave: v for v in vista.modelo.vms}
        grupos_por_chave.update({v.chave: v for v in vista.modelo.bancos})
        pares = [_no_recursivo(r, por_pai, spof_map, grupos_por_chave,
                               vista.cena.largura) for r in raizes]
        corpo_forma = "".join(p[0] for p in pares)
        corpo_texto = "".join(p[1] for p in pares)

        caixas_por_chave = {c.chave: c for c in vista.cena.caixas}
        resolvidas = []
        for a in vista.modelo.arestas:
            de = _resolver_produto(a.de, caixas_por_chave)
            para = _resolver_produto(a.para, caixas_por_chave)
            if de is not None and para is not None:
                resolvidas.append((a, de, para))
        offsets = _offsets_de_saida(resolvidas)
        arestas_forma = "".join(
            _aresta_forma(a, de, para, offsets[idx], idx)
            for idx, (a, de, para) in enumerate(resolvidas))
        arestas_texto = "".join(
            _aresta_texto(a, de, para, offsets[idx], idx)
            for idx, (a, de, para) in enumerate(resolvidas))

        largura = max(vista.cena.largura, 1.0)
        altura = max(vista.cena.altura, 1.0)
        hidden_attr = "" if ativa else " hidden"
        svgs.append(
            f'<svg id="mapa-{vista.chave}" viewBox="0 0 {largura:.2f} {altura:.2f}"{hidden_attr}>\n'
            f'<g class="formas" filter="url(#rabisco)">{corpo_forma}'
            f'<g stroke="{INK_SOFT}" stroke-width="1.4" fill="none"'
            f' vector-effect="non-scaling-stroke">{arestas_forma}</g></g>\n'
            f'<g class="textos">{corpo_texto}{arestas_texto}</g>\n'
            f'</svg>'
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
    botao_design = ('<button data-vista="design">Design</button>' if design_html else "")
    chaves_vistas = [v.chave for v in vistas] + (["design"] if design_html else [])
    vistas_json = json.dumps(chaves_vistas).replace("<", "\\u003c")
    if design_html:
        rotulos["design"] = "Design"
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
    font-family:{MONO};color:{INK}}}
  text{{font-family:{MONO};fill:{INK};pointer-events:none}}
  svg[id^="mapa-"]{{position:fixed;top:41px;left:0;width:100vw;
    height:calc(100vh - 41px);display:block;cursor:grab;touch-action:none}}
  /* Task 10: com duas cenas na pagina, hidden esconde a vista que nao esta
     ativa — sem esta regra, o svg{{display:block}} acima (que ja existia
     antes de haver mais de um svg) pisa a regra padrao do navegador pra
     [hidden] e as duas cenas ficam sobrepostas. */
  svg[hidden]{{display:none}}
  /* Task 11: custo do filtro de rabisco — desliga durante o voo (a camera
     move rapido, a tremida de quadro a quadro nao acrescenta nada e o
     recalculo do displacement em ~1600 formas custa quadro) e religa
     quando assenta. arq_zoom.js alterna a classe. */
  svg.voando g.formas{{filter:none}}
  /* Segundo corte: com o k grande (caixa ja enche a tela), a tremida em
     pixel de tela fica invisivel de qualquer jeito — desligar o filtro
     ali de cima nao muda o visual e poupa o recalculo. `K_LIMIAR_FILTRO`
     em arq_zoom.js alterna esta classe a cada quadro (aplicarFiltro). */
  svg.k-alto g.formas{{filter:none}}
  #cromo{{position:fixed;top:0;left:0;right:0;height:41px;z-index:3;
    display:flex;align-items:center;gap:14px;padding:0 16px;
    background:{SURFACE};border-bottom:1px solid {LINE};box-sizing:border-box}}
  .marca{{font-family:{BRAND_FONT};font-size:15px;letter-spacing:-.01em}}
  .marca b{{color:{BRAND};font-weight:600}}
  #painel-design{{position:fixed;top:41px;left:0;right:0;bottom:0;overflow:auto;
    background:{PAPER};padding:22px 26px 60px;z-index:1}}
  #painel-design section{{margin:0 0 26px}}
  #painel-design h3{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;
    color:{BRAND};margin:0 0 10px;font-weight:600}}
  #painel-design .dchips{{display:flex;flex-wrap:wrap;gap:10px}}
  #painel-design .dchip{{display:flex;align-items:center;gap:8px;background:{SURFACE};
    border:1px solid {LINE};border-radius:6px;padding:7px 11px;font-size:11px}}
  #painel-design code{{color:{INK};font-size:11px}}
  #painel-design em{{font-style:normal;color:{INK_MUTED};font-size:10.5px}}
  #painel-design .dher{{color:{BRAND};opacity:.75}}
  #painel-design .dsw{{width:26px;height:18px;border-radius:3px;
    border:1px solid {LINE_STRONG};display:inline-block;flex:none}}
  #painel-design .dbox{{background:{SURFACE_SOFT}}}
  #painel-design .dfonte{{font-size:15px;color:{INK}}}
  #painel-design .dfonte-arq{{margin:0 0 22px;font-size:11px;color:{INK_MUTED}}}
  #alternador{{display:inline-flex;border:1px solid {LINE_STRONG};border-radius:3px;
    overflow:hidden;font-size:11px}}
  #alternador button{{border:none;background:{SURFACE};color:{INK_SOFT};cursor:pointer;
    padding:5px 14px;font-family:{MONO};font-size:11px}}
  #alternador button.ativo{{background:{BRAND};color:{SURFACE}}}
  #trilha{{margin-left:auto;font-size:11px;color:{INK_MUTED}}}
  #dica{{position:fixed;bottom:12px;left:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:11px;color:{INK_SOFT};z-index:2}}
  #legenda{{position:fixed;bottom:12px;right:12px;background:{SURFACE};padding:8px 10px;
    border:1px solid {LINE};border-radius:6px;font-size:10px;color:{INK_SOFT};z-index:2}}
  #legenda b{{display:block;margin-bottom:4px;letter-spacing:.04em;color:{INK_MUTED};
    font-weight:600;font-size:10px}}
  #legenda svg{{width:268px;height:214px;display:block;pointer-events:none}}
  #legenda text{{fill:{INK_SOFT}}}
  [id^="fluxos-"]{{position:fixed;top:53px;right:12px;background:{SURFACE};padding:8px 12px;
    border:1px solid {LINE};border-radius:6px;font-size:12px;max-width:280px;z-index:2}}
  [id^="fluxos-"] summary{{cursor:pointer;font-weight:600;font-size:11px;
    letter-spacing:.04em;color:{INK_MUTED};list-style:none}}
  [id^="fluxos-"] summary::-webkit-details-marker{{display:none}}
  [id^="fluxos-"] summary::after{{content:" ▾"}}
  [id^="fluxos-"][open] summary::after{{content:" ▴"}}
  [id^="fluxos-"] button{{font-size:11px;margin:2px 2px 0 0;border:1px solid {LINE_STRONG};
    border-radius:4px;background:{SURFACE_SOFT};color:{INK};cursor:pointer;padding:3px 7px;
    font-family:{MONO}}}
  [id^="fluxos-"] button:hover{{background:{LINE}}}
  [id^="passos-"]{{margin:6px 0 0;padding-left:18px}}
  [id^="inv-"]{{margin:6px 0 0;font-style:italic}}
  [id^="passos-"] li{{margin:2px 0}}
  [data-k-min],[data-face-ate]{{transition:opacity .1s linear}}
  [data-navegavel],[data-aresta],[data-de]{{transition:opacity .15s linear}}
  /* Aresta dentro do mesmo produto nasce APAGADA. Medido em 30/08: as 20
     do Chatbot davam 43 travessias de caixa alheia mesmo depois do layout
     por afinidade, e ninguem esta perguntando por todas as 20 ao mesmo
     tempo. `arq_zoom.js` acende as do componente sob o mouse escrevendo
     opacity inline, que ganha desta regra; `Zoom.apagar()` limpa o inline e
     elas voltam a sumir sozinhas. */
  [data-interna]{{opacity:0}}
  /* Rodape esquerdo, nao topo: em cima ela cobria o rotulo da VM
     (`app2037`), que fica no canto superior esquerdo da cena. */
  #posicoes{{position:fixed;left:12px;bottom:52px;z-index:6;display:flex;gap:6px;
    align-items:center;background:{SURFACE};border:1px solid {LINE};border-radius:6px;
    padding:5px 8px;font-size:11px;color:{INK_MUTED}}}
  #posicoes button{{font-size:11px;font-family:{MONO};cursor:pointer;padding:3px 7px;
    border:1px solid {LINE_STRONG};border-radius:4px;background:{SURFACE_SOFT};color:{INK}}}
  #posicoes button:hover{{background:{LINE}}}
  #saida-posicoes{{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);
    z-index:9;background:{SURFACE};border:1px solid {LINE_STRONG};border-radius:8px;
    padding:14px;width:min(620px,90vw);box-shadow:0 8px 30px rgba(0,0,0,.18)}}
  #saida-posicoes p{{margin:0 0 8px;font-size:12px;color:{INK_MUTED};line-height:1.5}}
  #saida-posicoes textarea{{width:100%;font-family:{MONO};font-size:11px;
    border:1px solid {LINE};border-radius:4px;padding:8px;background:{SURFACE_SOFT};
    color:{INK};resize:vertical;box-sizing:border-box}}
  #saida-posicoes button{{margin-top:8px;font-size:11px;font-family:{MONO};cursor:pointer;
    padding:3px 9px;border:1px solid {LINE_STRONG};border-radius:4px;
    background:{SURFACE_SOFT};color:{INK}}}
</style>
{_defs_compartilhadas()}
<header id="cromo">
  <span class="marca">Revy · <b>arquitetura</b></span>
  <nav id="alternador">{corpo_botoes}{botao_design}</nav>
  <span id="trilha">Revy</span>
</header>
<div id="posicoes">
  <span>arraste as caixas</span>
  <button id="btn-auto" title="descarta o que você moveu e volta ao layout calculado">automático</button>
  <button id="btn-exportar" title="gera o bloco POSICOES para colar em arquitetura.py">exportar</button>
</div>
<div id="saida-posicoes" hidden>
  <p>Cole este bloco no lugar do <code>POSICOES</code> em <code>arquitetura.py</code> e rode <code>gerar_arquitetura.py</code>. A partir daí a posição é dado versionado, não só deste navegador.</p>
  <textarea id="texto-posicoes" readonly rows="10" spellcheck="false"></textarea>
  <button id="btn-fechar-posicoes">fechar</button>
</div>
<div id="dica">clique numa caixa para cair dentro · <strong>Esc</strong> volta · roda dá zoom · arraste o <strong>fundo</strong> para navegar · <strong>passe o mouse</strong> numa caixa para ver o que ela chama · borda grossa vermelha é SPOF, tracejado é assíncrono, moldura tracejada é máquina (VM)</div>
{_legenda_html()}
{corpo_fluxos}
{design_html}

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
  // A lista vem do gerador, nao de `Object.keys(zoomInstancias)`: a vista
  // Design nao tem instancia de Zoom (nao e' cena), e derivar as chaves das
  // instancias a deixaria de fora do alternador.
  var VISTAS = {vistas_json};
  function mostrarVista(chave) {{
    var chaves = VISTAS;
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
      var pagina = document.getElementById("painel-" + v);
      if (pagina) pagina.hidden = (v !== chave);
      var botao = document.querySelector('[data-vista="' + v + '"]');
      if (botao) botao.className = (v === chave) ? "ativo" : "";
    }}
    var trilhaEl = document.getElementById("trilha");
    if (trilhaEl) trilhaEl.textContent = ROTULOS[chave] || "Revy";
    // A dica de navegacao e o vocabulario de forma falam de CENA. Na vista
    // Design nao ha caixa pra clicar nem forma pra decifrar, e deixa-los la
    // seria instrucao para uma coisa que nao esta na tela.
    var temCena = !!document.getElementById("mapa-" + chave);
    var dica = document.getElementById("dica");
    if (dica) dica.hidden = !temCena;
    var legenda = document.getElementById("legenda");
    if (legenda) legenda.hidden = !temCena;
    // O filtro compartilhado (um `<filter>` so pro documento) guarda os
    // parametros da ULTIMA vista que mexeu nele — sem isto, trocar de vista
    // deixaria a tremida no k tunado da vista anterior ate o proximo pan/zoom.
    if (zoomInstancias[chave] && zoomInstancias[chave].atualizarFiltro) {{
      zoomInstancias[chave].atualizarFiltro();
    }}
  }}

  // ---- barra de posicoes ----
  // A vista visivel e' a dona dos botoes: cada <svg> tem a propria instancia
  // de Zoom, com o proprio conjunto de caixas movidas.
  function instanciaVisivel() {{
    for (var chave in zoomInstancias) {{
      if (!zoomInstancias[chave].elemento.hasAttribute("hidden")) return zoomInstancias[chave];
    }}
    return null;
  }}
  document.getElementById("btn-auto").addEventListener("click", function () {{
    var z = instanciaVisivel();
    if (z) z.voltarAoAutomatico();
  }});
  document.getElementById("btn-exportar").addEventListener("click", function () {{
    var z = instanciaVisivel();
    if (!z) return;
    var movidos = z.posicoesMovidas();
    // `sort`: o bloco exportado tem que sair igual duas vezes, senao colar
    // duas vezes seguidas produz diff de ordem no git sem nada ter mudado.
    var chaves = Object.keys(movidos).sort();
    var linhas = ['POSICOES: dict[str, tuple[float, float]] = {{'];
    for (var i = 0; i < chaves.length; i++) {{
      var m = movidos[chaves[i]];
      linhas.push('    "' + chaves[i] + '": (' +
                  m.dx.toFixed(1) + ', ' + m.dy.toFixed(1) + '),');
    }}
    linhas.push('}}');
    var texto = chaves.length ? linhas.join("\\n")
              : "# nada movido ainda — arraste uma caixa primeiro";
    var area = document.getElementById("texto-posicoes");
    area.value = texto;
    document.getElementById("saida-posicoes").hidden = false;
    area.focus(); area.select();
    // Copiar pode ser negado (file:// sem permissao, foco perdido): o
    // textarea ja esta selecionado, entao Cmd+C funciona de qualquer jeito.
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(texto).catch(function () {{}});
    }}
  }});
  document.getElementById("btn-fechar-posicoes").addEventListener("click", function () {{
    document.getElementById("saida-posicoes").hidden = true;
  }});
{corpo_scripts_fluxo}
</script>
"""
