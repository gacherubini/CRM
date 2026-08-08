"""Leitura dos tokens de marca e contraste WCAG.

Um parser proprio, e nao uma lib de CSS, porque o arquivo canonico e
deliberadamente simples: dois blocos, uma declaracao por linha.
"""
import re
from pathlib import Path

CANONICAL = Path(__file__).resolve().parent / "revy-tokens.css"

# Os quatro produtos que recebem copia. Caminhos relativos a raiz do repositorio.
DESTINOS = [
    "portal-gestao/app/static/css/revy-tokens.css",
    "revy-trafego/app/static/css/revy-tokens.css",
    "catalogo-publico/app/static/css/revy-tokens.css",
    "site/assets/revy-tokens.css",
]

RAIZ = Path(__file__).resolve().parents[2]

_BLOCO = re.compile(r"(?P<sel>[^{}]+)\{(?P<corpo>[^}]*)\}", re.S)
_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def load_tokens(path: Path) -> dict[str, dict[str, str]]:
    """Devolve {"light": {...}, "dark": {...}}.

    O bloco claro e o que casa `:root`; o escuro, o que casa `[data-theme="dark"]`.
    O escuro herda o claro e sobrescreve o que declara — igual ao cascade.
    """
    css = path.read_text(encoding="utf-8")
    light: dict[str, str] = {}
    dark_overrides: dict[str, str] = {}

    for bloco in _BLOCO.finditer(css):
        sel = bloco.group("sel")
        decls = {k: v.strip() for k, v in _DECL.findall(bloco.group("corpo"))}
        if 'data-theme="dark"' in sel:
            dark_overrides.update(decls)
        elif ":root" in sel:
            light.update(decls)

    dark = {**light, **dark_overrides}
    light = {k: _resolver(v, light) for k, v in light.items()}
    dark = {k: _resolver(v, dark) for k, v in dark.items()}
    return {"light": light, "dark": dark}


_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*\)")


def _resolver(valor: str, escopo: dict[str, str], profundidade: int = 0) -> str:
    """Troca var(--x) pelo valor de --x no mesmo tema.

    O canonico usa var() so para apontar --brand para um passo da escala do
    verde; uma passada rasa resolve, mas o limite de profundidade evita laco
    infinito se alguem criar uma referencia circular.
    """
    if profundidade > 5:
        return valor
    m = _VAR.search(valor)
    if not m:
        return valor
    alvo = escopo.get(m.group(1), "")
    return _resolver(valor.replace(m.group(0), alvo), escopo, profundidade + 1)


def _canal(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminancia(hexa: str) -> float:
    h = hexa.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal(r) + 0.7152 * _canal(g) + 0.0722 * _canal(b)


def contrast(fg: str, bg: str) -> float:
    """Razao de contraste WCAG 2.1. Aceita so hex opaco."""
    a, b = _luminancia(fg), _luminancia(bg)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)
