"""Gera a marca Revy em contorno vetorial.

A marca e a do kit de 20/08/2026: duas barras inclinadas mais a palavra em
Chivo 900. As barras sao geometria escrita a mao; a palavra sai da fonte via
fontTools — baixa o TTF do Google Fonts, extrai os glifos e inverte o eixo Y
(SVG cresce para baixo, fonte cresce para cima).

Por que contorno e nao <text>: o arquivo vai para impresso, Canva e favicon,
onde a fonte pode nao existir. Ver shared/brand/tests/test_marca.py.

Tres armadilhas ja pagas:
  - o woff2 exige a extensao Brotli, que nao esta instalada; por isso pedimos
    TTF com user-agent antigo (Mozilla/4.0);
  - a pasta de saida ja morou em docs/brand/assets e ficou orfa quando docs/
    foi reorganizada — o teste passou semanas vermelho. Mora aqui agora;
  - o eixo do contorno vem em unidades da fonte, nao em px: toda a composicao
    e feita em unidades e so o viewBox final traduz.
"""
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from tokens import RAIZ

ASSETS = Path(__file__).resolve().parent / "assets"
CACHE = Path(__file__).resolve().parent / ".cache"

TINTA = "#1b1b1b"
BRANCO = "#ffffff"
REVERSO = "#f5f5f5"
HERDA = "currentColor"

CSS_URL = "https://fonts.googleapis.com/css2?family=Chivo:wght@900&display=swap"
UA_ANTIGO = "Mozilla/4.0"

# --- geometria, medida pixel a pixel nos PNGs do kit -------------------------
# logo-revy-tinta.png e icone-barras-r-tinta.png. Tudo em multiplos da altura
# de caixa alta (a altura de tinta do "R"), que e a unica medida estavel entre
# o PNG e a fonte.
BARRA_ALTURA = 1.1756       # altura das barras
BARRA_ABAIXO_DA_BASE = 0.0789   # o quanto elas descem abaixo da linha de base
RESPIRO_ASSINATURA = 0.3513     # das barras ate o R, no logo
RESPIRO_ICONE = 0.1649          # das barras ate o R, no icone
ENTRELETRAS = -0.03         # em em: o kit exporta a palavra ~3% mais fechada

# Barras normalizadas num retangulo 78 x 100 (inclinacao 15,0 graus).
BARRAS = (
    ((26.5, 0), (46.3, 0), (19.8, 100), (0, 100)),
    ((58.2, 0), (78.0, 0), (51.5, 100), (31.7, 100)),
)
BARRAS_LARGURA = 78.0
BARRAS_ALTURA = 100.0

# --- o icone quadrado (favicon, icone de app), medido nos PNGs de 512 --------
LADO = 512
FAVICON_CAP = 222.0     # altura do R
FAVICON_CENTRO = (266.0, 257.5)
APP_CAP = 209.0
APP_CENTRO = (265.0, 257.0)
APP_RAIO = 114          # canto arredondado do icone de app do kit


def _baixar_ttf() -> Path:
    CACHE.mkdir(exist_ok=True)
    alvo = CACHE / "chivo-900.ttf"
    if alvo.exists():
        return alvo
    req = urllib.request.Request(CSS_URL, headers={"User-Agent": UA_ANTIGO})
    css = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    urls = re.findall(r"https://[^)]*\.ttf", css)
    if not urls:
        raise RuntimeError("o CSS do Google Fonts nao trouxe nenhum TTF")
    alvo.write_bytes(urllib.request.urlopen(urls[-1], timeout=30).read())
    return alvo


class _Fonte:
    """Chivo 900, com o que precisamos dela: glifos, avanco e caixa alta."""

    def __init__(self) -> None:
        self.tt = TTFont(_baixar_ttf())
        self.upem = self.tt["head"].unitsPerEm
        self.glifos = self.tt.getGlyphSet()
        self.cmap = self.tt.getBestCmap()
        self.cap = self._altura_de_tinta("R")

    def _glifo(self, ch: str):
        return self.glifos[self.cmap[ord(ch)]]

    def _altura_de_tinta(self, ch: str) -> float:
        pen = BoundsPen(self.glifos)
        self._glifo(ch).draw(pen)
        return pen.bounds[3]

    def borda_esquerda(self, ch: str) -> float:
        """x da primeira tinta do glifo — nao a origem dele.

        O kit mede tinta a tinta: o respiro medido no PNG vai da borda da barra
        ate o tronco do R. Alinhar pela origem do glifo somaria o espaco lateral
        da fonte por cima e abriria o respiro em ~4%.
        """
        pen = BoundsPen(self.glifos)
        self._glifo(ch).draw(pen)
        return pen.bounds[0]

    def desenhar(self, texto: str, x0: float, base_y: float) -> tuple[list[str], tuple]:
        """Contornos de `texto` ja posicionados, e a caixa de tinta deles.

        base_y e a linha de base num sistema que cresce para baixo; por isso o
        -1 no eixo Y da transformacao.
        """
        tracking = ENTRELETRAS * self.upem
        ds, caixa, x = [], _Caixa(), x0
        for ch in texto:
            glifo = self._glifo(ch)
            transformacao = Transform(1, 0, 0, -1, x, base_y)
            caneta = SVGPathPen(self.glifos)
            glifo.draw(TransformPen(caneta, transformacao))
            d = caneta.getCommands()
            if d:
                ds.append(d)
            limites = BoundsPen(self.glifos)
            glifo.draw(TransformPen(limites, transformacao))
            if limites.bounds:
                caixa.somar(limites.bounds)
            x += glifo.width + tracking
        return ds, caixa.valor()


class _Caixa:
    """Uniao de caixas delimitadoras (x0, y0, x1, y1)."""

    def __init__(self) -> None:
        self.b = None

    def somar(self, outra) -> None:
        if self.b is None:
            self.b = list(outra)
            return
        self.b[0] = min(self.b[0], outra[0])
        self.b[1] = min(self.b[1], outra[1])
        self.b[2] = max(self.b[2], outra[2])
        self.b[3] = max(self.b[3], outra[3])

    def valor(self) -> tuple:
        return tuple(self.b)


def _barras(altura: float) -> tuple[list[str], tuple]:
    """As duas barras, com o topo em y=0 e a esquerda em x=0."""
    escala = altura / BARRAS_ALTURA
    ds = []
    for pontos in BARRAS:
        p = [(x * escala, y * escala) for x, y in pontos]
        ds.append(
            "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in p) + " Z"
        )
    return ds, (0.0, 0.0, BARRAS_LARGURA * escala, altura)


def _lockup(fonte: _Fonte, texto: str, respiro: float) -> tuple[list[str], tuple]:
    """Barras + `texto`, alinhados como no kit."""
    altura_barras = BARRA_ALTURA * fonte.cap
    base_y = altura_barras - BARRA_ABAIXO_DA_BASE * fonte.cap

    ds_barras, caixa_barras = _barras(altura_barras)
    x0 = caixa_barras[2] + respiro * fonte.cap - fonte.borda_esquerda(texto[0])
    ds_texto, caixa_texto = fonte.desenhar(texto, x0, base_y)

    caixa = _Caixa()
    caixa.somar(caixa_barras)
    caixa.somar(caixa_texto)
    return ds_barras + ds_texto, caixa.valor()


def _svg(ds: list[str], caixa: tuple, cor: str, rotulo: str) -> str:
    """Envelopa contornos ja posicionados, com a tinta encostada na borda."""
    x0, y0, x1, y1 = caixa
    largura, altura = x1 - x0, y1 - y0
    corpo = "\n".join(f'    <path d="{d}"/>' for d in ds)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {largura:.0f} {altura:.0f}" role="img" aria-label="{rotulo}">\n'
        f'  <g fill="{cor}" transform="translate({-x0:.1f} {-y0:.1f})">\n'
        f"{corpo}\n  </g>\n</svg>\n"
    )


def _svg_quadrado(fonte: _Fonte, cap: float, centro: tuple, raio: int | None) -> str:
    """R branco centrado num quadrado de tinta. Favicon e icone de app.

    O R sai em contorno e e escalado para a altura de tinta medida no PNG do
    kit; centralizar pela caixa de tinta, e nao pelo avanco do glifo, e o que
    faz o R parecer no meio.
    """
    escala = cap / fonte.cap
    ds, caixa = fonte.desenhar("R", 0.0, 0.0)
    x0, y0, x1, y1 = [v * escala for v in caixa]
    dx = centro[0] - (x0 + x1) / 2
    dy = centro[1] - (y0 + y1) / 2
    canto = f' rx="{raio}"' if raio else ""
    corpo = "\n".join(f'    <path d="{d}"/>' for d in ds)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LADO} {LADO}" '
        f'role="img" aria-label="Revy">\n'
        f'  <rect width="{LADO}" height="{LADO}"{canto} fill="{TINTA}"/>\n'
        f'  <g fill="{BRANCO}" transform="translate({dx:.1f} {dy:.1f}) scale({escala:.5f})">\n'
        f"{corpo}\n  </g>\n</svg>\n"
    )


def gerar() -> list[Path]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fonte = _Fonte()

    ds_barras, caixa_barras = _barras(BARRA_ALTURA * fonte.cap)
    ds_palavra, caixa_palavra = fonte.desenhar("Revy", 0.0, 0.0)
    assinatura = _lockup(fonte, "Revy", RESPIRO_ASSINATURA)
    icone = _lockup(fonte, "R", RESPIRO_ICONE)

    saidas = {
        # herdam a cor: entram inline no HTML dos paineis
        "revy-bars.svg": _svg(ds_barras, caixa_barras, HERDA, "Revy"),
        "revy-icon.svg": _svg(*icone, HERDA, "Revy"),
        "revy-wordmark.svg": _svg(ds_palavra, caixa_palavra, HERDA, "Revy"),
        "revy-signature.svg": _svg(*assinatura, HERDA, "Revy"),
        # cor cravada: vao para <img> e favicon, onde currentColor nao existe
        "revy-icon-tinta.svg": _svg(*icone, TINTA, "Revy"),
        "revy-icon-branco.svg": _svg(*icone, REVERSO, "Revy"),
        "revy-signature-tinta.svg": _svg(*assinatura, TINTA, "Revy"),
        "revy-signature-branca.svg": _svg(*assinatura, REVERSO, "Revy"),
        "favicon.svg": _svg_quadrado(fonte, FAVICON_CAP, FAVICON_CENTRO, None),
        "icone-app.svg": _svg_quadrado(fonte, APP_CAP, APP_CENTRO, APP_RAIO),
    }

    escritos = []
    for nome, conteudo in saidas.items():
        destino = ASSETS / nome
        destino.write_text(conteudo, encoding="utf-8", newline="\n")
        escritos.append(destino)
    return escritos


if __name__ == "__main__":
    for p in gerar():
        print("gerado:", p.relative_to(RAIZ))
