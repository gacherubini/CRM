"""O HTML do zoom continuo: `Vista` (uma por cena) -> uma pagina SVG
auto-contida com um alternador no topo.

Task 10: a pagina tem cenas independentes (Arquitetura e Schema, uma `Vista`
cada) no MESMO documento — um `<svg id="mapa-{chave}">` por vista, so a
primeira visivel de saida, e um `Zoom.criar(...)` (arq_zoom.js) por vista,
porque as duas nao podem dividir estado de zoom.

01/09 — a pele de design system, depois de o dono abrir a pagina e dizer
que estava feia. O que mudou, e por que:

- **Cor por produto.** Cada produto Revy tem um matiz proprio
  (`PALETA_PRODUTO`), validado pelo validador de paleta categorica: seis
  matizes com luminosidade parecida, separacao para daltonismo e contraste
  contra o papel. A cor anda com a ENTIDADE: a seta herda a cor de quem
  chama, a banda do titulo leva a tinta, o componente leva um filete. O
  vermelho continua sendo SO' o dado dizendo risco (SPOF, seta sem retry) —
  nunca "vermelho porque e' importante".
- **A face do nivel 1 tem conteudo.** Antes o produto era um retangulo oco
  com titulo. Agora a banda do titulo fica sempre (e' o cabecalho que
  sobrevive ao zoom), e o RESUMO — termo, contagem de componentes por forma
  tecnica, os nomes dos componentes — e' o que some quando o interior abre.
- **Seta desvia de caixa** (`arq_rotas.py`), tem ponta cheia na cor da
  origem e rotulo numa pilula. A pilula e' um `<rect>` na camada de forma e
  um `<text>` na de texto, os dois com as mesmas marcas `data-*` pra
  acenderem juntos.
- **Sem rabisco.** O filtro de feTurbulence saiu: traco limpo, canto de
  `--radius-srf`, e o zoom ficou mais leve (era o que custava quadro).
- **Tipografia da marca.** Titulo e nome em `--font-ui` (Hanken Grotesk e
  os fallbacks do sistema — a pagina e' auto-contida, nao baixa fonte);
  `arquivo:linha`, contagem e protocolo continuam em mono. Nada aqui e'
  baixado: `file://` bloqueia `fetch()`.
- **Legenda e' rodape, nao painel flutuante.** Cromo em cima (marca,
  alternador, trilha, fluxos, posicoes) e vocabulario embaixo, fora da
  cena — nada cobre caixa.

As duas camadas por svg continuam (`<g class="formas">` e
`<g class="textos">`): o texto com `pointer-events:none` por cima garante
que o clique sempre acerta a forma, e o arrasto move os dois grupos irmaos
(`id` na forma, `data-texto-de` no texto).

`arq_zoom.js` le so: id, data-navegavel, data-titulo, data-k-min,
data-face-ate, data-dono, data-aresta, data-de/para/i/interna, data-x/y/w/h
e data-rw/rh (largura e altura da pilula de rotulo). Nao inventar outros.

Stdlib apenas. Auto-contido: nenhum `src=`/`href=` externo — o JS entra
inline (`js` embutido verbatim).
"""
from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass

import arq_rotas
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
    # Task 14. Na Arquitetura, aresta dentro do mesmo produto nasce APAGADA e
    # so acende sob o mouse — sao 99 marcadores, e ninguem pergunta pelas 20
    # do Chatbot ao mesmo tempo. Na Schema a regra se inverte: a seta E' o
    # conteudo. Um mapa conceitual de banco com as relacoes escondidas e' uma
    # lista de tabelas, que e' exatamente o que ele existe pra deixar de ser.
    arestas_sempre_visiveis: bool = False


# Cores de shared/brand/revy-tokens.css (tema claro), copiadas como literal —
# o HTML gerado nao importa CSS de fora (ver o learning
# 2026-08-23-tokens-de-marca-tem-fonte-unica.md).
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
FONTE_UI = '"Hanken Grotesk","Segoe UI",ui-sans-serif,system-ui,-apple-system,sans-serif'
BRAND_FONT = '"Newsreader",Georgia,serif'

# Paleta categorica dos produtos — SO' aqui, nunca nos tokens da marca: e'
# codificacao de dado (qual produto), nao identidade. Seis matizes em OKLCH
# (L 0.48–0.66, C >= 0.11), validados com o validador da skill `dataviz`
# em 01/09: banda de luminosidade, piso de croma, separacao para daltonismo
# entre vizinhos e contraste >= 3:1 contra o papel. O teal fica em C 0.098
# (o sRGB nao alcanca mais nesse matiz) — aceito porque a cor nunca anda
# sozinha: o nome do produto esta sempre ao lado.
#
# (traco, tinta): o traco vai na borda, na seta e no filete; a tinta na
# banda do titulo e no fundo do chip.
PALETA_PRODUTO: dict[str, tuple[str, str]] = {
    "chatbot-api":      ("#246e3a", "#e3efe6"),
    "estoque-api":      ("#1a95d8", "#e2f0f9"),
    "portal-gestao":    ("#aa442b", "#f6e6e1"),
    "revy-trafego":     ("#008991", "#dff0f1"),
    "catalogo-publico": ("#b576c3", "#f3e8f5"),
    "motor-simulacao":  ("#ab8704", "#f5efd9"),
}
COR_NEUTRA = (INK_SOFT, SURFACE_SOFT)      # terceiro, banco, produto sem cor
COR_TERCEIRO = ("#57514f", "#efeceb")
COR_BANCO = ("#6b625f", "#f4f2f1")


def _cor_de(chave: str) -> tuple[str, str]:
    """(traco, tinta) da caixa: o primeiro segmento do caminho pontuado que
    e' produto conhecido. `app2037.chatbot-api.workers` -> a cor do Chatbot.
    Sem produto no caminho (VM, banco, produto de teste) -> neutra."""
    for seg in chave.split("."):
        if seg in PALETA_PRODUTO:
            return PALETA_PRODUTO[seg]
    return COR_NEUTRA


def _slug(cor: str) -> str:
    return cor.lstrip("#").replace("(", "").replace(")", "").replace(",", "").replace(" ", "").replace(".", "")


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
    # VIZINHO. Um titulo longo numa caixa estreita transbordava pela direita:
    # achado no navegador em 30/08. 0.6 era o avanco da mono; a fonte de UI
    # e' mais estreita, mas o 0.6 fica como margem de seguranca — truncar
    # nunca AUMENTA uma fonte, entao nao cria estouro em lugar nenhum.
    largura_util = max(0.0, c.w - MARGEM)
    por_comprimento = largura_util / (len(c.titulo) * 0.6) if c.titulo else float("inf")

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
    por ".") -> spof. Um produto dentro de uma VM tem a chave da Caixa
    prefixada por `vm.chave.` (arq_layout._dispor_vm)."""
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
# Vocabulario de forma: retangulo com borda na cor do produto = produto Revy,
# moldura tracejada verde = maquina Fly, cilindro = banco, elipse cinza =
# software de terceiro. Marca tecnica (fila, worker, cache, browser) por cima.
# --------------------------------------------------------------------------

def _texto(x: float, y: float, txt: str, fs: float, *, cls: str = "t-ui",
           fill: str = INK, peso: str = "", anchor: str = "", extra: str = "") -> str:
    attrs = f'x="{x:.2f}" y="{y:.2f}" font-size="{fs:.1f}" class="{cls}"'
    if fill != INK:
        attrs += f' fill="{fill}"'
    if peso:
        attrs += f' font-weight="{peso}"'
    if anchor:
        attrs += f' text-anchor="{anchor}"'
    if extra:
        attrs += " " + extra
    return f"<text {attrs}>{_e(txt)}</text>"


def _largura_texto(txt: str, fs: float, mono: bool = False) -> float:
    return len(txt) * fs * (0.62 if mono else 0.55)


def _rect_no(c: Caixa, spof: bool, cor: str = INK) -> str:
    """A caixa de um no. `c.forma` troca o DESENHO, nunca a cor.

    Vocabulario TECNICO (31/08, a pedido do dono): ele le o desenho pela
    forma antes de ler o texto, e caixa toda igual obriga a ler cada legenda
    pra saber o que e' o que — ai o diagrama vira lista. A forma diz o que a
    coisa E' (fila, worker, cache, browser); o `papel` continua dizendo de
    que dominio ela e'. Sao perguntas diferentes.

    `cor` e' a cor do PRODUTO (01/09): borda do produto, filete do
    componente. O vermelho continua sendo so o SPOF — quem chama sem `cor`
    (os testes de forma) recebe a caixa neutra de sempre.
    """
    traco = DANGER if spof else cor
    largura = 2.6 if spof else 1.3
    base = (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="{min(10.0, c.w * 0.03):.1f}" fill="{SURFACE}" stroke="{traco}" '
        f'stroke-width="{largura}" vector-effect="non-scaling-stroke"/>'
    )
    return base + _marca_tecnica(c, DANGER if spof else INK_SOFT)


def _marca_tecnica(c: Caixa, cor: str) -> str:
    """O tracinho que diferencia a forma tecnica, desenhado SOBRE a caixa.

    Marca, e nao silhueta trocada: o layout ja calculou largura e altura
    contando com um retangulo, e a marca some junto com a caixa no LOD sem
    tratamento nenhum. Tudo em `vector-effect="non-scaling-stroke"`.
    """
    if not c.forma:
        return ""
    x, y, w, h = c.x, c.y, c.w, c.h
    fina = f' stroke="{cor}" stroke-width="1.0" fill="none" vector-effect="non-scaling-stroke"'

    if c.forma == "fila":
        # Tres divisorias na base = os lugares da fila.
        passo = w / 12.0
        base_y = y + h
        return "".join(
            f'<line x1="{x + passo * (i + 1):.2f}" y1="{base_y - h * 0.16:.2f}" '
            f'x2="{x + passo * (i + 1):.2f}" y2="{base_y:.2f}"{fina}/>'
            for i in range(3))

    if c.forma == "worker":
        # Duas barras verticais junto das laterais: "processo predefinido".
        d = min(w * 0.03, 6.0)
        return (f'<line x1="{x + d:.2f}" y1="{y:.2f}" x2="{x + d:.2f}" y2="{y + h:.2f}"{fina}/>'
                f'<line x1="{x + w - d:.2f}" y1="{y:.2f}" x2="{x + w - d:.2f}" y2="{y + h:.2f}"{fina}/>')

    if c.forma == "cache":
        # Boca de cilindro TRACEJADA no topo: guarda como um banco, mas pode
        # sumir a qualquer momento.
        rx = w / 2
        ry = min(max(rx * 0.10, 3.0), 14.0)
        ry = min(ry, max(1.0, h / 2 - 1))
        return (f'<path d="M{x:.2f},{y + ry:.2f} a{rx:.2f},{ry:.2f} 0 0 1 {w:.2f},0" '
                f'stroke="{cor}" stroke-width="1.0" fill="none" stroke-dasharray="5 4"'
                f' vector-effect="non-scaling-stroke"/>')

    if c.forma == "browser":
        # Barra de janela no topo: ali dentro sobe Chromium DE VERDADE.
        bh = min(h * 0.10, 10.0)
        r = min(bh * 0.22, 2.0)
        pontos = "".join(
            f'<circle cx="{x + bh * (0.7 + i * 0.75):.2f}" cy="{y + bh / 2:.2f}" '
            f'r="{r:.2f}" fill="{cor}"/>' for i in range(3))
        return (f'<line x1="{x:.2f}" y1="{y + bh:.2f}" x2="{x + w:.2f}" '
                f'y2="{y + bh:.2f}"{fina}/>' + pontos)

    raise ValueError(f"forma tecnica desconhecida: {c.forma!r} em {c.chave}")


def _rect_vm(c: Caixa) -> str:
    # Moldura, nao caixa: tracejada na cor da marca, com um fundo quase
    # transparente pra o olho ler o agrupamento (blast radius: a maquina que
    # cai leva tudo que esta dentro).
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="14" fill="rgba(31, 77, 58, .035)" stroke="{BRAND_LINE}" stroke-width="1.4"'
        f' vector-effect="non-scaling-stroke" stroke-dasharray="9 6"/>'
    )


def _cilindro(c: Caixa) -> str:
    """Grupo de banco: corpo + costura (arco de tras) — o cilindro classico
    em dois `<path>`."""
    x, y, w, h = c.x, c.y, c.w, c.h
    rx = w / 2
    ry = min(max(rx * 0.12, 4.0), 40.0)
    ry = min(ry, max(1.0, h / 2 - 1))
    cy_topo = y + ry
    cy_base = y + h - ry
    corpo = (
        f'<path d="M{x:.2f},{cy_topo:.2f} '
        f'a{rx:.2f},{ry:.2f} 0 0 1 {w:.2f},0 '
        f'V{cy_base:.2f} '
        f'a{rx:.2f},{ry:.2f} 0 0 1 {-w:.2f},0 Z" '
        f'fill="{COR_BANCO[1]}" stroke="{COR_BANCO[0]}" stroke-width="1.4" vector-effect="non-scaling-stroke"/>'
    )
    costura = (
        f'<path d="M{x:.2f},{cy_topo:.2f} a{rx:.2f},{ry:.2f} 0 0 0 {w:.2f},0" '
        f'fill="none" stroke="{COR_BANCO[0]}" stroke-width="1" vector-effect="non-scaling-stroke"/>'
    )
    return corpo + costura


def _geometria_roda(c: Caixa) -> tuple[float, float, float, float]:
    """A forma interna de uma VM sem produto ocupa ~70% da moldura, centrada
    — antes enchia a moldura inteira e o nome no meio saia com 4px."""
    banda = banda_titulo(max(0.0, c.w - MARGEM * 2), 0.02)
    iw = c.w * 0.70
    ih = min((c.h - banda) * 0.62, iw * 0.5)
    ix = c.x + (c.w - iw) / 2
    iy = c.y + banda + ((c.h - banda) - ih) / 2
    return ix, iy, iw, ih


def _forma_roda(c: Caixa, vm: Vm) -> str:
    """Uma VM de `contem` vazio mas `roda` preenchido (motor2037, n8n2037,
    evolution2037) ganha UMA forma interna: elipse se `terceiro`, retangulo
    se e' codigo Revy (o worker Playwright do Motor)."""
    ix, iy, iw, ih = _geometria_roda(c)
    if vm.terceiro:
        rx, ry = iw / 2, ih / 2
        return (f'<ellipse cx="{ix + rx:.2f}" cy="{iy + ry:.2f}" rx="{rx:.2f}" '
                f'ry="{ry:.2f}" fill="{COR_TERCEIRO[1]}" stroke="{COR_TERCEIRO[0]}" '
                f'stroke-width="1.4" vector-effect="non-scaling-stroke"/>')
    cor = _cor_de("motor-simulacao") if "motor" in c.chave else COR_NEUTRA
    return (f'<rect x="{ix:.2f}" y="{iy:.2f}" width="{iw:.2f}" height="{ih:.2f}" '
            f'rx="10" fill="{SURFACE}" stroke="{cor[0]}" stroke-width="1.4" '
            f'vector-effect="non-scaling-stroke"/>')


def _rotulo_roda(c: Caixa, vm: Vm) -> str:
    ix, iy, iw, ih = _geometria_roda(c)
    fonte = max(3.0, round(min(iw * 0.062, ih * 0.20), 1))
    cx = ix + iw / 2
    cy = iy + ih / 2
    legenda = "software de terceiro" if vm.terceiro else "código Revy, fora do HTTP"
    return (_texto(cx, cy - fonte * 0.15, vm.roda, fonte, peso="600", anchor="middle")
            + _texto(cx, cy + fonte * 1.05, legenda, fonte * 0.55, cls="t-data",
                     fill=INK_MUTED, anchor="middle"))


def _fonte_rotulo_grupo(c: Caixa, largura_cena: float, tem_filhos: bool = True) -> float:
    """Uma moldura de grupo (VM, banco) leva ETIQUETA, nao titulo de caixa:
    sai da CENA, igual para todas as molduras, e so encolhe se nao couber.

    A banda so limita quando ha filho embaixo dela (e' a faixa que o layout
    reservou pra etiqueta nao cair em cima do produto). Numa moldura sem
    produto (motor2037, n8n2037) nao ha o que invadir — e a banda de 2% de
    uma moldura pequena dava 34 unidades, 4px de etiqueta no nivel 1."""
    alvo = largura_cena * 0.011
    cabe = (c.w - largura_cena * 0.004) / max(1, len(c.titulo)) / 0.60
    banda = banda_titulo(max(0.0, c.w - MARGEM * 2), 0.02)
    teto_banda = banda * 0.55 if tem_filhos else c.h * 0.09
    return max(1.5, round(min(alvo, cabe, c.h * 0.30, teto_banda), 1))


def _truncar(txt: str, cabe: int) -> str:
    if len(txt) <= cabe:
        return txt
    return txt[:max(0, cabe - 1)] + "…"


# --------------------------------------------------------------------------
# A face: o que a caixa mostra de si mesma. Devolve dois pares (forma, texto):
# o FIXO (cabecalho, sobrevive ao zoom) e o que SOME quando o interior abre.
# --------------------------------------------------------------------------

ROTULO_FORMA = {"fila": "fila", "worker": "worker", "cache": "cache", "browser": "browser"}


def _face_vm(c: Caixa, largura_cena: float, tem_filhos: bool) -> tuple[str, str]:
    fonte = _fonte_rotulo_grupo(c, largura_cena, tem_filhos)
    fonte_sub = round(max(1.2, fonte * 0.62), 1)
    px = c.x + fonte * 0.9
    py = c.y + fonte * 1.35
    largura_util = (c.w - fonte * 1.8) * (0.42 if tem_filhos else 0.92) - _largura_texto(c.titulo, fonte, True) - fonte
    cabe = max(0, int(largura_util / (fonte_sub * 0.55)))
    nota = _truncar(c.subtitulo.split(". ")[0], cabe)
    texto = _texto(px, py, c.titulo, fonte, cls="t-data", fill=BRAND, peso="700",
                   extra='letter-spacing=".04em"')
    if nota:
        texto += _texto(px + _largura_texto(c.titulo, fonte, True) + fonte * 0.8,
                        py, nota, fonte_sub, fill=INK_MUTED)
    return "", texto


def _chip(x: float, y: float, txt: str, fs: float, *, fill: str, traco: str,
          cor_texto: str, mono: bool = True, peso: str = "") -> tuple[str, str, float]:
    """Pilula com texto. Devolve (forma, texto, largura)."""
    w = _largura_texto(txt, fs, mono) + fs * 1.3
    h = fs * 1.7
    borda = f' stroke="{traco}" stroke-width="1" vector-effect="non-scaling-stroke"' if traco else ""
    forma = (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
             f'rx="{h / 2:.2f}" fill="{fill}"{borda}/>')
    texto = _texto(x + fs * 0.65, y + h * 0.5 + fs * 0.36, txt, fs,
                   cls="t-data" if mono else "t-ui", fill=cor_texto, peso=peso)
    return forma, texto, w


def _face_produto(c: Caixa, spof: bool, cor: tuple[str, str],
                  filhos: list[Caixa], formas: dict[str, int]) -> tuple[tuple[str, str], tuple[str, str]]:
    """Banda de titulo (fixa) + resumo (some quando o interior abre)."""
    traco, tinta = cor
    banda = banda_titulo(max(0.0, c.w - MARGEM * 2))
    fs = min(_fonte_titulo(c), banda * 0.5)
    rx = min(10.0, c.w * 0.03)
    # A banda: um rect arredondado + um rect reto cobrindo a metade de
    # baixo, pra os cantos inferiores da banda sairem retos.
    forma_fixa = (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{banda:.2f}" '
        f'rx="{rx:.1f}" fill="{tinta}"/>'
        f'<rect x="{c.x:.2f}" y="{c.y + banda / 2:.2f}" width="{c.w:.2f}" '
        f'height="{banda / 2:.2f}" fill="{tinta}"/>'
        f'<line x1="{c.x:.2f}" y1="{c.y + banda:.2f}" x2="{c.x + c.w:.2f}" '
        f'y2="{c.y + banda:.2f}" stroke="{traco}" stroke-width="1" '
        f'vector-effect="non-scaling-stroke" opacity=".45"/>'
    )
    px = c.x + fs * 0.7
    py = c.y + banda / 2 + fs * 0.36
    texto_fixo = _texto(px, py, c.titulo, fs, peso="700")
    x_chip = px + _largura_texto(c.titulo, fs) + fs * 0.6
    if c.papel:
        chip_fs = fs * 0.52
        f, t, w = _chip(x_chip, c.y + banda / 2 - chip_fs * 0.85, c.papel, chip_fs,
                        fill=SURFACE, traco=traco, cor_texto=traco)
        forma_fixa += f
        texto_fixo += t
        x_chip += w + fs * 0.4
    if spof:
        chip_fs = fs * 0.52
        w = _largura_texto("SPOF", chip_fs, True) + chip_fs * 1.3
        x = c.x + c.w - fs * 0.7 - w
        f, t, _ = _chip(x, c.y + banda / 2 - chip_fs * 0.85, "SPOF", chip_fs,
                        fill=DANGER, traco="", cor_texto=SURFACE, peso="700")
        forma_fixa += f
        texto_fixo += t

    # ---- o resumo, que some ----
    # A fonte do resumo sai da AREA do corpo, nao da banda: o produto e' uma
    # caixa grande (o tamanho vem do interior empacotado) e um resumo em
    # fonte de banda deixava 80% dela vazia — o retangulo oco de antes, so
    # que com letra miuda no canto. Meta: as pilulas de nome ocupam ~45% do
    # corpo. Teto em banda*0.5 pra o resumo nao gritar mais que o titulo.
    forma_some, texto_some = "", ""
    corpo_h = max(1.0, c.h - banda - MARGEM * 1.5)
    corpo_w = max(1.0, c.w - fs * 1.4)
    eh_schema = bool(filhos) and all(f.papel in ("tabela", "migration") for f in filhos)
    n_itens = sum(1 for f in filhos if f.papel != "migration") if eh_schema else len(filhos)
    substantivo = "tabela" if eh_schema else "componente"
    chips = [f"{n_itens} {substantivo}{'s' if n_itens != 1 else ''}"]
    for forma in ("worker", "fila", "cache", "browser"):
        n = formas.get(forma, 0)
        if n:
            chips.append(f"{n} {ROTULO_FORMA[forma]}{'s' if n != 1 else ''}")
    nomes = [f.titulo for f in filhos]
    # area de cada pilula em unidades de fs^2: (len*0.55 + 1.3) largura x
    # 1.7 altura, mais 0.6 de respiro em cada eixo.
    area_pilulas = sum((len(n) * 0.55 + 1.9) * 2.3 for n in nomes)
    area_chips = sum((len(t) * 0.62 + 1.9) * 2.3 for t in chips) * 0.9 ** 2
    linhas_fixas = 2.2 + (1.9 if c.subtitulo and c.subtitulo != c.papel else 0.0)
    disponivel = corpo_w * corpo_h * 0.55
    denominador = max(1.0, area_pilulas + area_chips + linhas_fixas * corpo_w / max(fs, 1.0))
    nome_fs = math.sqrt(disponivel / denominador)
    nome_fs = max(fs * 0.34, min(nome_fs, banda * 0.66))
    chip_fs = nome_fs * 0.9
    fs_sub = round(max(1.2, nome_fs * 0.95), 1)

    y = c.y + banda + MARGEM * 0.7
    direita = c.x + c.w - fs * 0.7
    if c.subtitulo and c.subtitulo != c.papel:
        cabe = max(0, int((c.w - fs * 1.4) / (fs_sub * 0.55)))
        texto_some += _texto(px, y + fs_sub * 0.9, _truncar(c.subtitulo, cabe), fs_sub,
                             fill=INK_SOFT)
        y += fs_sub * 1.9

    # Contagem por forma tecnica: "11 componentes · 1 worker · 1 fila".
    x = px
    y += chip_fs * 0.3
    for txt in chips:
        f, t, w = _chip(x, y, txt, chip_fs, fill=SURFACE_SOFT, traco="", cor_texto=INK_SOFT)
        if x + w > direita and x > px:
            x = px
            y += chip_fs * 1.7 + chip_fs * 0.5
            f, t, w = _chip(x, y, txt, chip_fs, fill=SURFACE_SOFT, traco="", cor_texto=INK_SOFT)
        forma_some += f
        texto_some += t
        x += w + chip_fs * 0.6
    y += chip_fs * 1.7 + chip_fs * 1.1

    # Os nomes dos componentes, em pilulas de contorno. Para onde nao couber.
    x = px
    limite_y = c.y + c.h - MARGEM * 0.6
    faltam = 0
    for i, txt in enumerate(nomes):
        w = _largura_texto(txt, nome_fs) + nome_fs * 1.3
        if x + w > direita and x > px:
            x = px
            y += nome_fs * 1.7 + nome_fs * 0.55
        if y + nome_fs * 1.7 > limite_y:
            faltam = len(nomes) - i
            break
        f, t, w = _chip(x, y, txt, nome_fs, fill=SURFACE, traco=LINE_STRONG,
                        cor_texto=INK_SOFT, mono=False)
        forma_some += f
        texto_some += t
        x += w + nome_fs * 0.6
    if faltam:
        texto_some += _texto(x, y + nome_fs * 1.7 * 0.5 + nome_fs * 0.36,
                             f"+{faltam}", nome_fs, cls="t-data", fill=INK_MUTED)

    return (forma_fixa, texto_fixo), (forma_some, texto_some)


def _face_componente(c: Caixa, spof: bool, cor: tuple[str, str],
                     tem_filhos: bool) -> tuple[tuple[str, str], tuple[str, str]]:
    """Titulo na banda (fixo) + termo (some so quando ha filhos pra por no
    lugar). Filete na cor do produto pela esquerda."""
    traco, _ = cor
    fonte_titulo = _fonte_titulo(c)
    fonte_sub = round(max(1.2, fonte_titulo * 0.55), 1)
    px = c.x + fonte_titulo * 0.6
    # Na FAIXA RESERVADA do topo, sempre: arq_layout reserva a banda e
    # comeca os filhos ABAIXO dela.
    py_titulo = c.y + fonte_titulo * 1.15
    py_sub = py_titulo + fonte_sub * 1.7
    # Cortar na largura. 0.52em por caractere e' a media (mesma conta de
    # TestProvaCabeNaCaixa — se mudar aqui, muda la).
    largura_util = c.w - fonte_titulo * 1.2
    cabe = max(0, int(largura_util / (fonte_sub * 0.52)))
    sub = _truncar(c.subtitulo, cabe)

    filete_w = max(1.5, min(3.0, c.w * 0.009))
    forma_fixa = (f'<rect x="{c.x + 1.2:.2f}" y="{c.y + 3:.2f}" width="{filete_w:.2f}" '
                  f'height="{max(1.0, c.h - 6):.2f}" rx="{filete_w / 2:.2f}" fill="{traco}"/>')
    texto_fixo = _texto(px, py_titulo, c.titulo, fonte_titulo, peso="600")
    texto_sub = _texto(px, py_sub, sub, fonte_sub, cls="t-data", fill=INK_SOFT) if sub else ""
    if spof:
        texto_fixo += _texto(px, c.y + c.h - max(8.0, fonte_sub * 1.2), "SPOF", fonte_sub,
                             cls="t-data", fill=DANGER, peso="700")
    if tem_filhos:
        return (forma_fixa, texto_fixo), ("", texto_sub)
    return (forma_fixa, texto_fixo + texto_sub), ("", "")


def _item_forma(c: Caixa) -> str:
    if c.estilo == "coluna":
        return (f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
                f'fill="{SURFACE}" stroke="{LINE}" stroke-width=".5" vector-effect="non-scaling-stroke"/>')
    return (
        f'<rect x="{c.x:.2f}" y="{c.y:.2f}" width="{c.w:.2f}" height="{c.h:.2f}" '
        f'rx="3" fill="{SURFACE_RAISED}" stroke="{LINE_STRONG}" stroke-width=".6" vector-effect="non-scaling-stroke"/>'
    )


def _item_texto(c: Caixa) -> str:
    if c.estilo == "coluna":
        # Linha de tabela ER: nome a esquerda, tipo/papel a direita.
        fonte = 4.0
        cabe = max(0, int((c.w * 0.55) / (fonte * 0.62)))
        detalhe = c.subtitulo
        if len(detalhe) > cabe:
            detalhe = detalhe[:max(0, cabe - 1)] + "…"
        peso = "700" if "PK" in c.subtitulo else ""
        return (_texto(c.x + 3, c.y + c.h * 0.5 + fonte * 0.36, c.titulo, fonte,
                       cls="t-data", peso=peso)
                + _texto(c.x + c.w - 3, c.y + c.h * 0.5 + fonte * 0.36, detalhe, fonte * 0.85,
                         cls="t-data", fill=INK_MUTED, anchor="end"))
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
        f'<text x="{c.x + 4:.2f}" y="{c.y + 5.5:.2f}" font-size="{fonte_titulo}" class="t-ui" font-weight="600">'
        f'{_e(c.titulo)}</text>'
        f'<text x="{c.x + 4:.2f}" y="{c.y + 9.5:.2f}" font-size="{fonte_sub}" class="t-data" '
        f'fill="{INK_SOFT}">{_e(sub)}</text>'
    )


def _contar_formas(caixa: Caixa, por_pai: dict) -> dict[str, int]:
    saida: dict[str, int] = {}
    for f in por_pai.get(caixa.chave, []):
        if f.tipo != "no":
            continue
        if f.forma:
            saida[f.forma] = saida.get(f.forma, 0) + 1
        for k, v in _contar_formas(f, por_pai).items():
            saida[k] = saida.get(k, 0) + v
    return saida


def _no_recursivo(caixa: Caixa, por_pai: dict, spof_map: dict,
                  grupos_por_chave: dict[str, Vm],
                  largura_cena: float, pai_tipo: str | None = None) -> tuple[str, str]:
    """Devolve `(forma, texto)` — a caixa inteira dividida nas duas camadas.
    Recursivo: cada filho contribui a propria forma e o proprio texto."""
    filhos = por_pai.get(caixa.chave, [])
    subs_no = [f for f in filhos if f.tipo in ("no", "vm")]
    itens = [f for f in filhos if f.tipo == "item"]
    spof = spof_map.get(caixa.chave, False)
    cor = _cor_de(caixa.chave)

    interior_forma = "".join(_item_forma(i) for i in itens)
    interior_texto = "".join(_item_texto(i) for i in itens)
    for s in subs_no:
        f_forma, f_texto = _no_recursivo(s, por_pai, spof_map, grupos_por_chave,
                                         largura_cena, caixa.tipo)
        interior_forma += f_forma
        interior_texto += f_texto

    extra_forma = ""
    extra_texto = ""
    dica = ""
    if caixa.tipo == "vm":
        vm = grupos_por_chave.get(caixa.chave)
        eh_banco = vm is not None and vm.tipo in ("postgres", "banco-proprio")
        retangulo = _cilindro(caixa) if eh_banco else _rect_vm(caixa)
        if vm is not None and vm.roda and not filhos:
            extra_forma = _forma_roda(caixa, vm)
            extra_texto = _rotulo_roda(caixa, vm)
        fixo = _face_vm(caixa, largura_cena, bool(subs_no))
        some = ("", "")
        if caixa.subtitulo:
            dica = f"<title>{_e(caixa.titulo)} — {_e(caixa.subtitulo)}</title>"
    else:
        retangulo = _rect_no(caixa, spof, cor[0])
        eh_produto = pai_tipo in (None, "vm")
        if eh_produto:
            fixo, some = _face_produto(caixa, spof, cor, subs_no, _contar_formas(caixa, por_pai))
        else:
            fixo, some = _face_componente(caixa, spof, cor, bool(subs_no))
        if caixa.subtitulo and caixa.subtitulo != caixa.papel:
            dica = f"<title>{_e(caixa.titulo)} — {_e(caixa.subtitulo)}</title>"

    # `data-dono` anda junto do limiar: sem ele o LOD e' so escala, e caixas
    # irmas de tamanho parecido abrem o interior JUNTAS. Ver a trava de
    # linhagem em arq_zoom.js.
    kmin_attr = (
        f' data-k-min="{caixa.k_min:.3f}" data-dono="{_e(caixa.chave)}"'
        if caixa.k_min > 0 else ""
    )
    face_attr = (
        f' data-face-ate="{caixa.k_face:.3f}" data-dono="{_e(caixa.chave)}"'
        if caixa.k_face > 0 else ""
    )

    # `data-x/y/w/h`: a geometria ORIGINAL da caixa, pra o JS nao precisar de
    # getBBox. Arrastar soma um deslocamento a estes numeros.
    geo = (f' data-x="{caixa.x:.2f}" data-y="{caixa.y:.2f}"'
           f' data-w="{caixa.w:.2f}" data-h="{caixa.h:.2f}"')
    chave_esc = _e(caixa.chave)
    forma = (
        f'<g id="{chave_esc}" data-titulo="{_e(caixa.titulo)}" data-navegavel{geo}>'
        + retangulo + dica + extra_forma + fixo[0]
        + f"<g{face_attr}>{some[0]}</g>"
        + f"<g{kmin_attr}>{interior_forma}</g>"
        + "</g>"
    )
    # `data-texto-de` casa esta camada com a forma de mesma chave. O <g> do
    # texto nao pode levar `id`: `svg.getElementById` acertaria o alvo errado.
    texto = (
        f'<g data-texto-de="{chave_esc}">' + fixo[1] + extra_texto
        + f"<g{face_attr}>{some[1]}</g>"
        + f"<g{kmin_attr}>{interior_texto}</g>"
        + "</g>"
    )
    return forma, texto


def _resolver_produto(chave_produto: str, caixas_por_chave: dict[str, Caixa]) -> Caixa | None:
    """Acha a Caixa de um produto pra fim de aresta. Um produto dentro de
    uma VM tem a chave da Caixa prefixada (`app2037.portal-gestao`), entao
    a chave crua da Aresta (`portal-gestao`) nunca bate direto — casa pelo
    sufixo. Produto em mais de uma VM escolhe a primeira em ordem
    alfabetica, sempre a mesma."""
    if chave_produto in caixas_por_chave:
        return caixas_por_chave[chave_produto]
    candidatos = sorted(
        k for k in caixas_por_chave if k.endswith("." + chave_produto))
    return caixas_por_chave[candidatos[0]] if candidatos else None


# --------------------------------------------------------------------------
# Arestas: ortogonais, desviando de caixa (arq_rotas), com pilula de rotulo.
# --------------------------------------------------------------------------

_LADO_OPOSTO = arq_rotas._LADO_OPOSTO


def _lado_saida(de: Caixa, para: Caixa) -> str:
    return arq_rotas.lado_saida(_ret(de), _ret(para))


def _ponto_borda(c: Caixa, lado: str, deslocamento: float) -> tuple[float, float]:
    return arq_rotas.ponto_borda(_ret(c), lado, deslocamento)


def _pontos_ortogonais(p1, lado1, p2):
    return arq_rotas._pontos_ortogonais(p1, lado1, p2)


def _ret(c: Caixa) -> arq_rotas.Ret:
    return arq_rotas.Ret(c.x, c.y, c.w, c.h)


def _offsets_de_saida(resolvidas: list) -> dict[int, float]:
    """Quando duas arestas saem da MESMA borda da MESMA caixa, desloca o
    ponto de saida pra elas nao se sobreporem — espalhadas em torno do
    centro da borda, na ordem em que aparecem (`resolvidas` ja vem
    deterministico: `arq_modelo.carregar` ordena as arestas)."""
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


def _ancestral(a: str, b: str) -> bool:
    """`a` e' ancestral de `b` (caminho pontuado)?"""
    return b.startswith(a + ".")


def _obstaculos(de: Caixa, para: Caixa, por_pai: dict) -> list[arq_rotas.Ret]:
    """Irmaos das duas pontas, fora as proprias pontas e os ancestrais delas
    (sair de dentro de uma moldura obriga a cruzar a moldura). Ficha
    (`item`) nunca e' obstaculo: mora dentro de uma caixa que ja e'."""
    vistos: set[str] = set()
    saida: list[arq_rotas.Ret] = []
    for pai in (de.pai, para.pai):
        for c in por_pai.get(pai, []):
            if c.tipo == "item" or c.chave in vistos:
                continue
            if c.chave in (de.chave, para.chave):
                continue
            if _ancestral(c.chave, de.chave) or _ancestral(c.chave, para.chave):
                continue
            vistos.add(c.chave)
            saida.append(_ret(c))
    saida.sort(key=lambda r: (r.x, r.y, r.w, r.h))
    return saida


def _dono_lod(de: Caixa, para: Caixa, caixas_por_chave: dict) -> Caixa | None:
    """A caixa cujo INTERIOR contem as duas pontas: o ancestral comum mais
    fundo que e' `no` com limiar. A seta entre dois componentes do Chatbot
    so faz sentido com o Chatbot aberto — no nivel 1 ela cortava a face do
    produto (na Schema, onde toda seta e' visivel, virava um emaranhado por
    cima das pilulas). Aresta entre produtos (ancestral comum e' VM ou
    nenhum) nao tem dono: e' a camada de sempre."""
    a = de.chave.split(".")
    b = para.chave.split(".")
    comum = []
    for x, y in zip(a, b):
        if x != y:
            break
        comum.append(x)
    while comum:
        c = caixas_por_chave.get(".".join(comum))
        if c is not None and c.tipo == "no" and c.k_min > 0:
            return c
        comum.pop()
    return None


def _pontos_da_aresta(de: Caixa, para: Caixa, deslocamento: float,
                      obstaculos: list | None = None) -> list[tuple[float, float]]:
    return arq_rotas.rotear(_ret(de), _ret(para), obstaculos or [],
                            folga=MARGEM * 0.6, deslocamento=deslocamento)


def _sem_rede(a: Aresta) -> bool:
    """A aresta fica dentro do mesmo produto? Isso decide a COR do risco:
    `retry=False` so e' risco quando a chamada atravessa fronteira de
    processo. Dentro do mesmo produto e' funcao chamando funcao."""
    return a.de.split(".")[0] == a.para.split(".")[0]


def _cor_aresta(a: Aresta, de: Caixa) -> str:
    if not a.retry and not _sem_rede(a):
        return DANGER
    if _sem_rede(a):
        return INK_SOFT
    return _cor_de(de.chave)[0]


def _marcas_da_aresta(a: Aresta, de: Caixa, para: Caixa, idx: int,
                      sempre_visivel: bool = False) -> str:
    """Atributos que `arq_zoom.js` le pra decidir a opacidade de cada seta.

    `data-de`/`data-para` sao os ids ABSOLUTOS (com prefixo de VM).
    `data-interna` marca aresta que nao cruza fronteira de produto — sao
    elas que nascem apagadas e so acendem sob o mouse. Vao na forma, na
    pilula E no rotulo, pra os tres acenderem juntos. `data-aresta` NAO:
    o valor carrega um `>` literal, e e' o que os testes contam.
    """
    interna = ' data-interna=""' if _sem_rede(a) and not sempre_visivel else ""
    return (f' data-i="{idx}" data-de="{_e(de.chave)}"'
            f' data-para="{_e(para.chave)}"{interna}')


def _aresta_forma(a: Aresta, de: Caixa, para: Caixa, deslocamento: float, idx: int,
                  sempre_visivel: bool = False, obstaculos: list | None = None) -> str:
    pontos = _pontos_da_aresta(de, para, deslocamento, obstaculos)
    marca = f"{_e(a.de)}->{_e(a.para)}"
    cor = _cor_aresta(a, de)
    fs = _escala_aresta(de, para)
    tracejado = f' stroke-dasharray="{fs * 0.9:.1f} {fs * 0.6:.1f}"' if not a.sincrono else ""
    # A cor so' sai escrita quando difere do grupo (INK_SOFT): e' o que
    # deixa `test_5` contar o vermelho por aresta sem retry — a ponta, que
    # e' `fill`, usa a mesma cor, e o teste conta as duas.
    cor_attr = f' stroke="{cor}"' if cor != INK_SOFT else ""
    grossura = 2.2 if not _sem_rede(a) else 1.5
    txt_pontos = " ".join(f"{x:.2f},{y:.2f}" for x, y in pontos)
    marcas = _marcas_da_aresta(a, de, para, idx, sempre_visivel)
    linha = (
        f'<polyline data-aresta="{marca}" points="{txt_pontos}"'
        f'{marcas}{tracejado}{cor_attr} stroke-width="{grossura}"/>'
    )
    ponta = _ponta(pontos, fs, cor if cor != INK_SOFT else INK_SOFT, marcas)
    return linha + ponta + _aresta_pilula(a, de, para, pontos, idx, sempre_visivel, fs)


def _meio_do_maior_segmento(pontos: list) -> tuple[float, float]:
    melhor, mx, my = -1.0, pontos[0][0], pontos[0][1]
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
        comp = abs(x2 - x1) + abs(y2 - y1)
        if comp > melhor:
            melhor, mx, my = comp, (x1 + x2) / 2, (y1 + y2) / 2
    return mx, my


def _escala_aresta(de: Caixa, para: Caixa) -> float:
    """Fonte do rotulo (e tamanho da ponta) proporcional a MENOR das duas
    pontas: entre produtos (caixa de ~1000) o rotulo tem que se ler no nivel
    1; entre componentes (caixa de ~240) ele tem que caber no nivel 3."""
    return max(6.0, min(60.0, round(min(de.w, para.w) * 0.05, 1)))


def _tamanho_pilula(a: Aresta, fs: float) -> tuple[float, float]:
    return _largura_texto(a.protocolo, fs, True) + fs * 1.2, fs * 1.6


def _ponta(pontos: list, fs: float, cor: str, marcas: str) -> str:
    """A ponta da seta, como triangulo proprio (nao `<marker>`): o marcador
    escala com a stroke-width, que e' non-scaling, entao saia com 3px no
    nivel 1 e sumia. Aqui o tamanho acompanha a escala da aresta."""
    (x1, y1), (x2, y2) = pontos[-2], pontos[-1]
    dx, dy = x2 - x1, y2 - y1
    comp = math.hypot(dx, dy) or 1.0
    ux, uy = dx / comp, dy / comp
    tam = fs * 1.1
    bx, by = x2 - ux * tam, y2 - uy * tam
    px, py = -uy * tam * 0.45, ux * tam * 0.45
    return (f'<path data-ponta="" data-tam="{tam:.2f}" d="M{x2:.2f},{y2:.2f} L{bx + px:.2f},{by + py:.2f} '
            f'L{bx - px:.2f},{by - py:.2f} Z" fill="{cor}" stroke="none"{marcas}/>')


def _aresta_pilula(a: Aresta, de: Caixa, para: Caixa, pontos: list, idx: int,
                   sempre_visivel: bool, fs: float) -> str:
    """O fundo do rotulo, na camada de forma. "chamada" e' o protocolo mudo
    (funcao chamando funcao) e nao leva rotulo — ver `_aresta_texto`."""
    if a.protocolo == "chamada":
        return ""
    mx, my = _meio_do_maior_segmento(pontos)
    w, h = _tamanho_pilula(a, fs)
    return (f'<rect data-rw="{w:.2f}" data-rh="{h:.2f}" x="{mx - w / 2:.2f}" y="{my - h / 2:.2f}" '
            f'width="{w:.2f}" height="{h:.2f}" rx="{h / 2:.2f}" fill="{SURFACE}" '
            f'stroke="{LINE_STRONG}" stroke-width="1" vector-effect="non-scaling-stroke"'
            f'{_marcas_da_aresta(a, de, para, idx, sempre_visivel)}/>')


def _aresta_texto(a: Aresta, de: Caixa, para: Caixa, deslocamento: float, idx: int,
                  sempre_visivel: bool = False, obstaculos: list | None = None) -> str:
    # Rotulo e' SO o protocolo — sincrono/assincrono ja esta no tracejado da
    # forma, e "sem retry" ja esta na cor vermelha; repetir em texto era
    # ruido (e a palavra "retry" nunca aparece em texto nenhum).
    if a.protocolo == "chamada":
        return ""
    pontos = _pontos_da_aresta(de, para, deslocamento, obstaculos)
    mx, my = _meio_do_maior_segmento(pontos)
    fs = _escala_aresta(de, para)
    cor = DANGER if _cor_aresta(a, de) == DANGER else INK_SOFT
    # `class="protocolo"` so pra marcar QUAL <text> e' rotulo de aresta.
    return (f'<text{_marcas_da_aresta(a, de, para, idx, sempre_visivel)} x="{mx:.2f}" '
            f'y="{my + fs * 0.36:.2f}" font-size="{fs:.1f}" fill="{cor}" '
            f'class="protocolo" text-anchor="middle">'
            f'{_e(a.protocolo)}</text>')


# --------------------------------------------------------------------------
# Paineis: design, fluxos, defs, legenda, cromo.
# --------------------------------------------------------------------------

def _amostra(tok) -> str:
    """A amostra tem que MOSTRAR o token, nao descrever."""
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
    """A vista Design: os tokens de `shared/brand/revy-tokens.css`."""
    if not grupos:
        return ""
    secoes = []
    for g in grupos:
        chips = []
        for tok in g.tokens:
            heranca = (f'<em class="dher">{_e(tok.bruto)}</em>'
                       if tok.bruto != tok.valor else "")
            chips.append(
                f'<div class="dchip">{_amostra(tok)}'
                f'<code>{_e(tok.nome)}</code>'
                f'<em>{_e(tok.valor)}</em>{heranca}</div>'
            )
        secoes.append(f'<section><h3>{_e(g.titulo)}</h3>'
                      f'<div class="dchips">{"".join(chips)}</div></section>')
    # A paleta dos produtos tambem e' design — e vive so' nesta pagina.
    chips_prod = "".join(
        f'<div class="dchip"><span class="dsw" style="background:{traco}"></span>'
        f'<code>{_e(chave)}</code><em>{traco}</em>'
        f'<span class="dsw" style="background:{tinta}"></span><em>{tinta}</em></div>'
        for chave, (traco, tinta) in PALETA_PRODUTO.items())
    secoes.append('<section><h3>Paleta do diagrama (só aqui, não é token)</h3>'
                  f'<div class="dchips">{chips_prod}</div></section>')
    hidden_attr = " hidden" if oculto else ""
    return (f'<div id="painel-design"{hidden_attr}>'
            f'<p class="dfonte-arq">lido de <code>shared/brand/revy-tokens.css</code>'
            f' na geracao — nao copiado. Editar la muda esta pagina.</p>'
            f'{"".join(secoes)}</div>')


def _fluxos_html(modelo: Modelo, chave: str, oculto: bool) -> str:
    """Seletor de fluxo da vista `chave`: um botao por `Fluxo`, que acende so
    as caixas dos seus passos (`Zoom.acender`) e lista os passos EM ORDEM."""
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
    return (f'<details id="fluxos-{chave}" class="fluxos"{hidden_attr}>'
            f'<summary>Fluxos</summary><div class="fluxos-corpo">'
            f'{"".join(botoes)}<button data-fluxo="" class="limpar">limpar</button>'
            f'<ol id="passos-{chave}" hidden></ol><p id="inv-{chave}" hidden></p></div></details>'
            f'<script>var FLUXOS_{chave} = {json_fluxos};</script>')


def _fluxos_script(chave: str) -> str:
    return f"""
  var elFluxos_{chave} = document.getElementById("fluxos-{chave}");
  if (elFluxos_{chave}) {{
    elFluxos_{chave}.addEventListener("click", function (ev) {{
      var k = ev.target.getAttribute("data-fluxo");
      if (k === null) return;
      var ol = document.getElementById("passos-{chave}"), inv = document.getElementById("inv-{chave}");
      var botoes = elFluxos_{chave}.querySelectorAll("[data-fluxo]");
      for (var i = 0; i < botoes.length; i++) botoes[i].classList.toggle("ativo", botoes[i] === ev.target && !!k);
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


def _marcador(id_: str, cor: str) -> str:
    return (f'<marker id="{id_}" markerWidth="8" markerHeight="8" refX="6.6" refY="4" '
            f'orient="auto" markerUnits="strokeWidth">'
            f'<path d="M0.5,0.8 L7,4 L0.5,7.2 Z" fill="{cor}" stroke="none"/>'
            "</marker>")


def _defs_compartilhadas() -> str:
    """Um `<defs>` por DOCUMENTO: marcadores de seta, um por cor. Fica num
    `<svg>` proprio, 0x0, so pra hospedar `<defs>`."""
    marcadores = [_marcador("seta", INK_SOFT), _marcador("seta-sem", DANGER)]
    for traco, _ in PALETA_PRODUTO.values():
        marcadores.append(_marcador(f"seta-{_slug(traco)}", traco))
    return (
        '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
        "<defs>" + "".join(marcadores) + "</defs></svg>"
    )


# As formas tecnicas que a legenda desenha. `_marca_tecnica` levanta em
# forma desconhecida e `test_toda_forma_tecnica_usada_esta_na_legenda` liga as
# duas pontas.
FORMAS_TECNICAS: frozenset[str] = frozenset({"fila", "worker", "cache", "browser"})


def _legenda_html() -> str:
    """O vocabulario, como RODAPE fixo (nao painel por cima da cena). Cada
    item e' um mini-svg com a forma e o nome ao lado."""
    def item(svg: str, nome: str) -> str:
        return (f'<span class="lg-item"><svg viewBox="0 0 34 22" width="34" height="22">{svg}</svg>'
                f'<span>{nome}</span></span>')

    verde = PALETA_PRODUTO["chatbot-api"][0]
    itens = [
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{verde}" stroke-width="1.4"/>'
             f'<rect x="2" y="3" width="30" height="6" rx="3" fill="{PALETA_PRODUTO["chatbot-api"][1]}"/>',
             "produto Revy"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="6" fill="rgba(31,77,58,.05)" stroke="{BRAND_LINE}" stroke-width="1.3" stroke-dasharray="4 3"/>',
             "máquina Fly"),
        item(f'<ellipse cx="17" cy="11" rx="14" ry="8" fill="{COR_TERCEIRO[1]}" stroke="{COR_TERCEIRO[0]}" stroke-width="1.3"/>',
             "software de terceiro"),
        item(f'<path d="M3,6 a14,3 0 0 1 28,0 v10 a14,3 0 0 1 -28,0 z" fill="{COR_BANCO[1]}" stroke="{COR_BANCO[0]}" stroke-width="1.3"/>',
             "banco"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{INK_SOFT}" stroke-width="1.3"/>'
             f'<line x1="9.5" y1="16" x2="9.5" y2="19" stroke="{INK_SOFT}"/><line x1="17" y1="16" x2="17" y2="19" stroke="{INK_SOFT}"/><line x1="24.5" y1="16" x2="24.5" y2="19" stroke="{INK_SOFT}"/>',
             "fila (outbox)"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{INK_SOFT}" stroke-width="1.3"/>'
             f'<line x1="6" y1="3" x2="6" y2="19" stroke="{INK_SOFT}"/><line x1="28" y1="3" x2="28" y2="19" stroke="{INK_SOFT}"/>',
             "worker"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{INK_SOFT}" stroke-width="1.3"/>'
             f'<path d="M2,6 a15,3 0 0 1 30,0" fill="none" stroke="{INK_SOFT}" stroke-dasharray="3 2"/>',
             "cache"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{INK_SOFT}" stroke-width="1.3"/>'
             f'<line x1="2" y1="8" x2="32" y2="8" stroke="{INK_SOFT}"/><circle cx="5.5" cy="5.5" r="1" fill="{INK_SOFT}"/><circle cx="9" cy="5.5" r="1" fill="{INK_SOFT}"/><circle cx="12.5" cy="5.5" r="1" fill="{INK_SOFT}"/>',
             "browser (RPA)"),
        item(f'<line x1="2" y1="11" x2="28" y2="11" stroke="{INK_SOFT}" stroke-width="1.6" marker-end="url(#seta)"/>',
             "síncrono"),
        item(f'<line x1="2" y1="11" x2="28" y2="11" stroke="{INK_SOFT}" stroke-width="1.6" stroke-dasharray="5 3" marker-end="url(#seta)"/>',
             "assíncrono (fila)"),
        item(f'<line x1="2" y1="11" x2="28" y2="11" stroke="{DANGER}" stroke-width="1.6" marker-end="url(#seta-sem)"/>',
             "sem retentativa"),
        item(f'<rect x="2" y="3" width="30" height="16" rx="3" fill="{SURFACE}" stroke="{DANGER}" stroke-width="2.4"/>',
             "SPOF"),
    ]
    return f'<footer id="legenda"><b>Vocabulário</b>{"".join(itens)}</footer>'


DICA = ("clique numa caixa para cair dentro · Esc volta · roda dá zoom · arraste o fundo para navegar · "
        "passe o mouse numa caixa para ver o que ela chama · arraste uma caixa para reposicionar")


def render(vistas: tuple[Vista, ...], js: str,
           tokens: tuple[Grupo, ...] = ()) -> str:
    """Monta a pagina inteira a partir de N `Vista`. A primeira da tupla abre
    visivel; as demais saem com `hidden`. Cada vista ganha o proprio
    `<svg id="mapa-{chave}">`, o proprio botao no alternador (`data-vista`) e
    a propria instancia de `Zoom.criar`."""
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
        sempre = vista.arestas_sempre_visiveis
        obst = [_obstaculos(de, para, por_pai) for (_, de, para) in resolvidas]
        # Aresta com dono (as duas pontas dentro do mesmo produto) sai num
        # `<g data-k-min data-dono>` proprio, que `aplicarLod` acende junto
        # com o interior daquele produto. As sem dono ficam soltas. A ordem
        # de `data-i` continua sendo a de `resolvidas` — o JS ordena por ela,
        # nunca pela ordem do DOM.
        soltas_f, soltas_t = [], []
        por_dono_f: dict[str, list[str]] = {}
        por_dono_t: dict[str, list[str]] = {}
        donos: dict[str, Caixa] = {}
        for idx, (a, de, para) in enumerate(resolvidas):
            f = _aresta_forma(a, de, para, offsets[idx], idx, sempre, obst[idx])
            t = _aresta_texto(a, de, para, offsets[idx], idx, sempre, obst[idx])
            dono = _dono_lod(de, para, caixas_por_chave)
            if dono is None:
                soltas_f.append(f)
                soltas_t.append(t)
            else:
                donos[dono.chave] = dono
                por_dono_f.setdefault(dono.chave, []).append(f)
                por_dono_t.setdefault(dono.chave, []).append(t)
        arestas_forma = "".join(soltas_f)
        arestas_texto = "".join(soltas_t)
        for chave_dono in sorted(donos):
            d = donos[chave_dono]
            attr = f' data-k-min="{d.k_min:.3f}" data-dono="{_e(d.chave)}"'
            arestas_forma += f"<g{attr}>{''.join(por_dono_f[chave_dono])}</g>"
            arestas_texto += f"<g{attr}>{''.join(por_dono_t[chave_dono])}</g>"

        largura = max(vista.cena.largura, 1.0)
        altura = max(vista.cena.altura, 1.0)
        # Respiro em volta da cena: sem ele a moldura de baixo encostava no
        # rodape e a de cima no cromo.
        m = max(largura, altura) * 0.02
        hidden_attr = "" if ativa else " hidden"
        svgs.append(
            f'<svg id="mapa-{vista.chave}" viewBox="{-m:.2f} {-m:.2f} {largura + 2 * m:.2f} {altura + 2 * m:.2f}"{hidden_attr}>\n'
            f'<g class="formas">{corpo_forma}'
            f'<g class="arestas" stroke="{INK_SOFT}" stroke-width="1.8" fill="none"'
            f' vector-effect="non-scaling-stroke">{arestas_forma}</g></g>\n'
            f'<g class="textos">{corpo_texto}{arestas_texto}</g>\n'
            f'</svg>'
        )

        classe = ' class="ativo"' if ativa else ""
        botoes.append(f'<button data-vista="{_e(vista.chave)}"{classe}>{_e(vista.rotulo)}</button>')
        rotulos[vista.chave] = vista.rotulo

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
  :root{{--cromo:48px;--rodape:42px}}
  html,body{{margin:0;height:100%;background:{PAPER};
    font-family:{FONTE_UI};color:{INK};overflow:hidden}}
  text{{font-family:{FONTE_UI};fill:{INK};pointer-events:none}}
  text.t-data,text.protocolo{{font-family:{MONO}}}
  svg[id^="mapa-"]{{position:fixed;top:var(--cromo);left:0;width:100vw;
    height:calc(100vh - var(--cromo) - var(--rodape));display:block;cursor:grab;touch-action:none;
    background:{PAPER}}}
  /* Task 10: com duas cenas na pagina, hidden esconde a vista que nao esta
     ativa — sem esta regra, o svg{{display:block}} acima pisa a regra padrao
     do navegador pra [hidden] e as duas cenas ficam sobrepostas. */
  svg[hidden]{{display:none}}
  #cromo{{position:fixed;top:0;left:0;right:0;height:var(--cromo);z-index:3;
    display:flex;align-items:center;gap:14px;padding:0 16px;
    background:{SURFACE};border-bottom:1px solid {LINE};box-sizing:border-box}}
  .marca{{font-family:{BRAND_FONT};font-size:17px;letter-spacing:-.01em;white-space:nowrap}}
  .marca b{{color:{BRAND};font-weight:600}}
  #alternador{{display:inline-flex;border:1px solid {LINE_STRONG};border-radius:8px;
    overflow:hidden;font-size:12px}}
  #alternador button{{border:none;background:{SURFACE};color:{INK_SOFT};cursor:pointer;
    padding:6px 14px;font-family:{FONTE_UI};font-size:12px;font-weight:600}}
  #alternador button.ativo{{background:{BRAND};color:{SURFACE}}}
  #trilha{{font-size:12px;color:{INK_MUTED};font-family:{MONO};margin-left:4px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}}
  .ferramentas{{display:flex;align-items:center;gap:8px;margin-left:auto;font-size:11px;
    color:{INK_MUTED};white-space:nowrap}}
  .ferramentas button,.fluxos button{{font-size:11px;font-family:{FONTE_UI};cursor:pointer;
    padding:4px 9px;border:1px solid {LINE_STRONG};border-radius:6px;background:{SURFACE};color:{INK}}}
  .ferramentas button:hover,.fluxos button:hover{{background:{SURFACE_SOFT}}}
  .ajuda{{display:inline-flex;width:20px;height:20px;border-radius:50%;border:1px solid {LINE_STRONG};
    align-items:center;justify-content:center;font-size:11px;color:{INK_MUTED};cursor:help;
    font-family:{MONO}}}
  .fluxos{{position:relative;font-size:12px}}
  .fluxos summary{{cursor:pointer;font-weight:600;font-size:11px;list-style:none;
    padding:4px 10px;border:1px solid {LINE_STRONG};border-radius:6px;background:{SURFACE};color:{INK}}}
  .fluxos summary::-webkit-details-marker{{display:none}}
  .fluxos summary::after{{content:" ▾"}}
  .fluxos[open] summary::after{{content:" ▴"}}
  .fluxos-corpo{{position:absolute;right:0;top:32px;width:320px;background:{SURFACE};
    border:1px solid {LINE};border-radius:10px;padding:10px 12px;z-index:5;
    box-shadow:0 8px 24px rgba(27,20,20,.10);white-space:normal;text-align:left}}
  .fluxos-corpo button{{margin:2px 2px 2px 0;background:{SURFACE_SOFT};border-color:{LINE}}}
  .fluxos-corpo button.ativo{{background:{BRAND};color:{SURFACE};border-color:{BRAND}}}
  .fluxos-corpo button.limpar{{background:{SURFACE}}}
  [id^="passos-"]{{margin:8px 0 0;padding-left:18px;font-size:11.5px;line-height:1.45}}
  [id^="inv-"]{{margin:8px 0 0;font-size:11px;color:{INK_MUTED};line-height:1.4}}
  #legenda{{position:fixed;left:0;right:0;bottom:0;height:var(--rodape);z-index:3;
    display:flex;align-items:center;gap:16px;padding:0 16px;overflow-x:auto;
    background:{SURFACE};border-top:1px solid {LINE};box-sizing:border-box;
    font-size:11px;color:{INK_SOFT};white-space:nowrap}}
  #legenda b{{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:{INK_MUTED};margin-right:4px}}
  #legenda .lg-item{{display:inline-flex;align-items:center;gap:6px}}
  #legenda svg{{display:block;flex:none}}
  #painel-design{{position:fixed;top:var(--cromo);left:0;right:0;bottom:0;overflow:auto;
    background:{PAPER};padding:22px 26px 60px;z-index:1}}
  #painel-design section{{margin:0 0 26px}}
  #painel-design h3{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;
    color:{BRAND};margin:0 0 10px;font-weight:600}}
  #painel-design .dchips{{display:flex;flex-wrap:wrap;gap:10px}}
  #painel-design .dchip{{display:flex;align-items:center;gap:8px;background:{SURFACE};
    border:1px solid {LINE};border-radius:8px;padding:7px 11px;font-size:11px}}
  #painel-design code{{color:{INK};font-size:11px;font-family:{MONO}}}
  #painel-design em{{font-style:normal;color:{INK_MUTED};font-size:10.5px;font-family:{MONO}}}
  #painel-design .dher{{color:{BRAND};opacity:.75}}
  #painel-design .dsw{{width:26px;height:18px;border-radius:4px;
    border:1px solid {LINE_STRONG};display:inline-block;flex:none}}
  #painel-design .dbox{{background:{SURFACE_SOFT}}}
  #painel-design .dfonte{{font-size:15px;color:{INK}}}
  #painel-design .dfonte-arq{{margin:0 0 22px;font-size:11px;color:{INK_MUTED};font-family:{MONO}}}
  #saida-posicoes{{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);
    z-index:9;background:{SURFACE};border:1px solid {LINE_STRONG};border-radius:12px;
    padding:14px;width:min(620px,90vw);box-shadow:0 8px 30px rgba(0,0,0,.18)}}
  #saida-posicoes p{{margin:0 0 8px;font-size:12px;color:{INK_MUTED};line-height:1.5}}
  #saida-posicoes textarea{{width:100%;font-family:{MONO};font-size:11px;
    border:1px solid {LINE};border-radius:6px;padding:8px;background:{SURFACE_SOFT};
    color:{INK};resize:vertical;box-sizing:border-box}}
  #saida-posicoes button{{margin-top:8px;font-size:11px;font-family:{FONTE_UI};cursor:pointer;
    padding:4px 10px;border:1px solid {LINE_STRONG};border-radius:6px;
    background:{SURFACE_SOFT};color:{INK}}}
  [data-k-min],[data-face-ate]{{transition:opacity .1s linear}}
  [data-navegavel],[data-aresta],[data-de]{{transition:opacity .15s linear}}
  /* Aresta dentro do mesmo produto nasce APAGADA. `arq_zoom.js` acende as
     do componente sob o mouse escrevendo opacity inline, que ganha desta
     regra; `Zoom.apagar()` limpa o inline e elas voltam a sumir sozinhas. */
  [data-interna]{{opacity:0}}
  g.arestas polyline{{stroke-linejoin:round;stroke-linecap:round}}
</style>
{_defs_compartilhadas()}
<header id="cromo">
  <span class="marca">Revy · <b>arquitetura</b></span>
  <nav id="alternador">{corpo_botoes}{botao_design}</nav>
  <span id="trilha">Revy</span>
  <div class="ferramentas">
    {corpo_fluxos}
    <span id="posicoes"><button id="btn-auto" title="descarta o que você moveu e volta ao layout calculado">automático</button>
    <button id="btn-exportar" title="gera o bloco POSICOES para colar em arquitetura.py">exportar</button></span>
    <span class="ajuda" id="dica" title="{_e(DICA)}">?</span>
  </div>
</header>
<div id="saida-posicoes" hidden>
  <p>Cole este bloco no lugar do <code>POSICOES</code> em <code>arquitetura.py</code> e rode <code>gerar_arquitetura.py</code>. A partir daí a posição é dado versionado, não só deste navegador.</p>
  <textarea id="texto-posicoes" readonly rows="10" spellcheck="false"></textarea>
  <button id="btn-fechar-posicoes">fechar</button>
</div>
{_legenda_html()}
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
  // Design nao tem instancia de Zoom (nao e' cena).
  var VISTAS = {vistas_json};
  function mostrarVista(chave) {{
    var chaves = VISTAS;
    for (var i = 0; i < chaves.length; i++) {{
      var v = chaves[i];
      var svgEl = document.getElementById("mapa-" + v);
      // setAttribute, nao a propriedade `.hidden`: em SVGSVGElement (o
      // <svg> raiz) `.hidden = true` NAO reflete no atributo nem some da
      // tela neste Chrome — so aparece lendo `getAttribute`.
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
    // Na vista Design nao ha caixa pra clicar nem forma pra decifrar.
    var temCena = !!document.getElementById("mapa-" + chave);
    var dica = document.getElementById("dica");
    if (dica) dica.hidden = !temCena;
    var legenda = document.getElementById("legenda");
    if (legenda) legenda.hidden = !temCena;
    var posicoes = document.getElementById("posicoes");
    if (posicoes) posicoes.hidden = !temCena;
  }}

  // ---- barra de posicoes ----
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
