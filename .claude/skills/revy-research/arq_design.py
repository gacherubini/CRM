"""A vista Design: os tokens da marca, lidos de `shared/brand/revy-tokens.css`.

Lidos, nao copiados. `revy-tokens.css` se declara FONTE UNICA no proprio
cabecalho, e uma pagina de design system que repete os valores a mao vira
mentira no primeiro `sync_tokens.py` — que e' exatamente o defeito que esta
pagina inteira existe pra nao ter.

So o bloco `:root` (tema claro). O `[data-theme="dark"]` e' dos paineis
(Loja e Control); o site e o catalogo declaram `color-scheme: light` e nunca
recebem `data-theme`. Desenhar os dois lado a lado sugeriria uma escolha que
nao existe.

Stdlib apenas: um parser de `--nome: valor;` resolve o arquivo inteiro. Nao
vale trazer dependencia de CSS pra ler 40 linhas de declaracao.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# `/* --- neutros --- */` e afins. E' o unico agrupamento que existe no
# arquivo, e ele e' bom: quem edita os tokens ja pensa nesses grupos.
_SECAO = re.compile(r"/\*\s*-{2,}\s*(.+?)\s*-{2,}\s*\*/")
_TOKEN = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(.+?);\s*$", re.MULTILINE)
_VAR = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*\)")


@dataclass(frozen=True)
class Token:
    nome: str          # `--brand`
    valor: str         # ja resolvido: `#1f4d3a`, nunca `var(--green-700)`
    bruto: str         # como esta escrito no arquivo, pra mostrar a heranca
    tipo: str          # "cor" | "forma" | "fonte" | "sombra" | "outro"


@dataclass(frozen=True)
class Grupo:
    titulo: str
    tokens: tuple[Token, ...]


def _tipo_de(valor: str) -> str:
    v = valor.strip().lower()
    if v.startswith("#") or v.startswith("rgba(") or v.startswith("rgb("):
        return "cor"
    if v.endswith("px") or v.endswith("rem") or v.endswith("em"):
        return "forma"
    if "serif" in v or "monospace" in v or "system-ui" in v:
        return "fonte"
    if v == "none" or "rgba" in v or v.count(" ") >= 2:
        return "sombra"
    return "outro"


def ler_tokens(caminho: Path) -> tuple[Grupo, ...]:
    """Le o `:root` de `revy-tokens.css` e devolve os tokens agrupados na
    ordem em que aparecem no arquivo — a ordem e' informacao (a escala do
    verde vai do 900 ao 100), entao nao se ordena nada aqui."""
    texto = caminho.read_text(encoding="utf-8")
    inicio = texto.index(":root")
    fim = texto.index("}", inicio)
    corpo = texto[inicio:fim]

    # Primeiro passe: todo valor cru, pra poder resolver `var(--x)` depois.
    crus = {m.group(1): m.group(2).strip() for m in _TOKEN.finditer(corpo)}

    def resolver(valor: str, profundidade: int = 0) -> str:
        # Profundidade: `var(--a)` apontando pra `var(--b)` e legitimo, um
        # ciclo nao — e um ciclo aqui travaria a geracao inteira.
        if profundidade > 8:
            return valor
        m = _VAR.search(valor)
        if not m:
            return valor
        alvo = crus.get(m.group(1), valor)
        return resolver(valor[:m.start()] + alvo + valor[m.end():], profundidade + 1)

    grupos: list[Grupo] = []
    atual_titulo = "tokens"
    atual: list[Token] = []
    posicao = 0
    for marca in _SECAO.finditer(corpo):
        trecho = corpo[posicao:marca.start()]
        for m in _TOKEN.finditer(trecho):
            bruto = m.group(2).strip()
            atual.append(Token(m.group(1), resolver(bruto), bruto, _tipo_de(resolver(bruto))))
        if atual:
            grupos.append(Grupo(atual_titulo, tuple(atual)))
        atual = []
        atual_titulo = marca.group(1)
        posicao = marca.end()

    for m in _TOKEN.finditer(corpo[posicao:]):
        bruto = m.group(2).strip()
        atual.append(Token(m.group(1), resolver(bruto), bruto, _tipo_de(resolver(bruto))))
    if atual:
        grupos.append(Grupo(atual_titulo, tuple(atual)))

    return tuple(grupos)
