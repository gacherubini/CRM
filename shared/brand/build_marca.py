"""Gera a marca Revy em contorno vetorial.

O simbolo e geometria escrita a mao. O wordmark sai da Hanken Grotesk 700 via
fontTools: baixa o TTF estatico do Google Fonts, extrai os glifos de "Revy" e
inverte o eixo Y (SVG cresce para baixo, fonte cresce para cima).

Duas armadilhas ja pagas:
  - o woff2 exige a extensao Brotli, que nao esta instalada; por isso pedimos
    TTF com user-agent antigo (Mozilla/4.0);
  - no CSS de wght@400;700 o arquivo de peso 700 e o SEGUNDO da lista.
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

ASSETS = RAIZ / "docs" / "brand" / "assets"
CACHE = Path(__file__).resolve().parent / ".cache"

PRETO = "#1b1b1b"
PRETO_REVERSO = "#000000"
BRANCO = "#ffffff"
FIO = "rgba(255,255,255,.16)"
VERDE_300 = "#7fbfa3"

# Simbolo Bloco: quadrado rx=9 num viewBox 0 0 40 40, com o R vazado.
SIMBOLO_PATHS = (
    "M15.5 30V13h6.8a4.3 4.3 0 0 1 0 8.6h-6.8",
    "M21 21.6 27 30",
)

CSS_URL = "https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;700&display=swap"
UA_ANTIGO = "Mozilla/4.0"


def _baixar_ttf_700() -> Path:
    CACHE.mkdir(exist_ok=True)
    alvo = CACHE / "hanken-700.ttf"
    if alvo.exists():
        return alvo
    req = urllib.request.Request(CSS_URL, headers={"User-Agent": UA_ANTIGO})
    css = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    urls = re.findall(r"https://[^)]*\.ttf", css)
    if len(urls) < 2:
        raise RuntimeError(f"esperava 2 TTF (400 e 700), vieram {len(urls)}")
    alvo.write_bytes(urllib.request.urlopen(urls[1], timeout=30).read())
    return alvo


def _wordmark_paths(texto: str = "Revy") -> tuple[list[str], float, float]:
    """Devolve (lista de d=, largura em unidades, unitsPerEm)."""
    fonte = TTFont(_baixar_ttf_700())
    upem = fonte["head"].unitsPerEm
    glifos = fonte.getGlyphSet()
    cmap = fonte.getBestCmap()

    ds, x = [], 0.0
    for ch in texto:
        nome = cmap[ord(ch)]
        pen = SVGPathPen(glifos)
        glifos[nome].draw(TransformPen(pen, Transform(1, 0, 0, -1, x, 0)))
        d = pen.getCommands()
        if d:
            ds.append(d)
        x += glifos[nome].width
    return ds, x, upem


def _borda_esquerda(texto: str) -> float:
    """x da primeira tinta do texto — nao a origem do glifo.

    O descritor e reduzido a ~20%, e com ele encolhe o espaco lateral do "G".
    Alinhar as duas origens em x=0 deixaria o descritor uns 59/1000 de em a
    esquerda do tronco do "R": o olho le como desalinhamento, nao como
    compensacao optica. Alinhamos a tinta, entao.
    """
    fonte = TTFont(_baixar_ttf_700())
    glifos = fonte.getGlyphSet()
    pen = BoundsPen(glifos)
    glifos[fonte.getBestCmap()[ord(texto[0])]].draw(pen)
    return pen.bounds[0] if pen.bounds else 0.0


def _svg_simbolo(fundo: str, tinta: str, fio: str | None) -> str:
    borda = (
        f'\n  <rect x="1" y="1" width="38" height="38" rx="8" fill="none" '
        f'stroke="{fio}" stroke-width="2"/>' if fio else ""
    )
    traços = "\n".join(
        f'  <path d="{d}" fill="none" stroke="{tinta}" stroke-width="3" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        for d in SIMBOLO_PATHS
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" '
        'role="img" aria-label="Revy">\n'
        f'  <rect width="40" height="40" rx="9" fill="{fundo}"/>{borda}\n'
        f"{traços}\n</svg>\n"
    )


def _svg_wordmark(tinta: str) -> str:
    ds, largura, upem = _wordmark_paths()
    altura = upem
    corpo = "\n".join(f'    <path d="{d}"/>' for d in ds)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura:.0f} {altura:.0f}" '
        'role="img" aria-label="Revy">\n'
        f'  <g fill="{tinta}" transform="translate(0 {altura * 0.78:.0f})">\n'
        f"{corpo}\n  </g>\n</svg>\n"
    )


def _svg_assinatura(tinta: str, tinta_descritor: str) -> str:
    """Wordmark + descritor. O descritor tambem sai em contorno, no mesmo TTF."""
    ds_nome, larg_nome, upem = _wordmark_paths("Revy")
    ds_desc, larg_desc, _ = _wordmark_paths("GESTAO DE REVENDA")

    escala_desc = (larg_nome * 0.92) / larg_desc
    desloc_desc = _borda_esquerda("Revy") - _borda_esquerda("GESTAO DE REVENDA") * escala_desc
    corpo_nome = "\n".join(f'    <path d="{d}"/>' for d in ds_nome)
    corpo_desc = "\n".join(f'    <path d="{d}"/>' for d in ds_desc)
    altura = upem * 1.35

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larg_nome:.0f} {altura:.0f}" '
        'role="img" aria-label="Revy — Gestao de revenda">\n'
        f'  <g fill="{tinta}" transform="translate(0 {upem * 0.74:.0f})">\n{corpo_nome}\n  </g>\n'
        f'  <g fill="{tinta_descritor}" transform="translate({desloc_desc:.0f} {altura * 0.97:.0f}) '
        f'scale({escala_desc:.4f})">\n{corpo_desc}\n  </g>\n</svg>\n'
    )


def gerar() -> list[Path]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    saidas = {
        "revy-mark.svg": _svg_simbolo(PRETO, BRANCO, None),
        "revy-mark-reverse.svg": _svg_simbolo(PRETO_REVERSO, "#f5f5f5", FIO),
        "favicon.svg": _svg_simbolo(PRETO, BRANCO, None),
        "revy-wordmark.svg": _svg_wordmark(PRETO),
        "revy-signature.svg": _svg_assinatura(PRETO, "#6b625f"),
        "revy-signature-reverse.svg": _svg_assinatura("#f5f5f5", VERDE_300),
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
