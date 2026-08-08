"""Guarda dos tokens de marca.

Contraste nao e opiniao: se um par cair abaixo de 4.5:1 o texto fica ilegivel
para parte dos usuarios. Este teste existe para que uma futura troca de cor
quebre aqui, e nao na tela do lojista.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import CANONICAL, DESTINOS, RAIZ, contrast, load_tokens

# (token do texto, token do fundo) que precisam passar AA em cada tema.
PARES_AA = [
    ("--ink-muted", "--paper"),
    ("--ink-muted", "--surface"),
    ("--ink-soft", "--surface"),
    ("--brand", "--paper"),
    ("--brand", "--surface-raised"),
    ("--st-wait", "--surface"),
    ("--st-live", "--surface"),
    ("--st-prop", "--surface"),
    ("--st-won", "--surface"),
    ("--st-lost", "--surface"),
]


@pytest.fixture(scope="module")
def tokens():
    return load_tokens(CANONICAL)


@pytest.mark.parametrize("tema", ["light", "dark"])
@pytest.mark.parametrize("fg,bg", PARES_AA)
def test_par_passa_aa(tokens, tema, fg, bg):
    razao = contrast(tokens[tema][fg], tokens[tema][bg])
    assert razao >= 4.5, f"{fg} sobre {bg} no tema {tema}: {razao:.2f}:1"


def test_acento_escuro_nao_usa_o_verde_do_claro(tokens):
    """#1f4d3a sobre fundo escuro da 1,6:1. Se alguem colar o valor do claro
    no bloco escuro, este teste pega."""
    assert tokens["dark"]["--brand"] != tokens["light"]["--brand"]
    assert tokens["dark"]["--brand"] == "#7fbfa3"


def test_preto_da_marca(tokens):
    assert tokens["light"]["--ink"] == "#1b1b1b"


def test_raios(tokens):
    assert tokens["light"]["--radius-ctl"] == "3px"
    assert tokens["light"]["--radius-nav"] == "8px"
    assert tokens["light"]["--radius-srf"] == "12px"


from sync_tokens import divergentes


def test_copias_em_dia():
    """Se este teste falhar, alguem editou uma copia em vez do canonico.
    Rode: python shared/brand/sync_tokens.py
    """
    fora = divergentes()
    assert not fora, "copias divergentes do canonico: " + ", ".join(str(p) for p in fora)


AZUL_ANTIGO = ("#1f6feb", "#5a95ff", "#1a5fd0", "#82afff")

CSS_DE_PRODUTO = [
    "portal-gestao/app/static/css/app.css",
    "revy-trafego/app/static/css/app.css",
]


@pytest.mark.parametrize("rel", CSS_DE_PRODUTO)
def test_azul_de_saas_nao_voltou(rel):
    css = (RAIZ / rel).read_text(encoding="utf-8").lower()
    achados = [c for c in AZUL_ANTIGO if c in css]
    assert not achados, f"{rel} ainda tem {achados}"


# ---------------------------------------------------------------------------
# Regressao: um "*/" literal dentro do corpo de um comentario fecha o
# comentario cedo NO NAVEGADOR, mesmo que o parser proprio deste modulo
# (tokens.py, via _BLOCO/_DECL) nao se importe com comentarios. O parser
# proprio so procura "algo { ... }" e casa ":root" por substring — ele NUNCA
# vai pegar esse bug. Os testes abaixo reproduzem a leitura do navegador:
# de cada "/*" ate o PRIMEIRO "*/" seguinte, e um seletor so conta se, depois
# de removidos os comentarios, sobrar EXATAMENTE ":root" (ou
# '[data-theme="dark"]') — nao "contem :root em algum lugar do lixo".
# ---------------------------------------------------------------------------


def _remover_comentarios_como_navegador(css: str) -> str:
    """Remove comentarios CSS a moda do navegador.

    Cada comentario vai do "/*" ate o PRIMEIRO "*/" que aparecer depois dele.
    Se esse "*/" estiver no MEIO do texto que deveria ser comentario (o bug
    que este teste existe para pegar), o comentario fecha cedo e o resto do
    texto — inclusive chaves, dois-pontos e o proprio ":root" que vem depois —
    volta a ser CSS "de verdade" aos olhos do navegador.
    """
    pedacos = []
    i = 0
    while True:
        inicio = css.find("/*", i)
        if inicio == -1:
            pedacos.append(css[i:])
            break
        pedacos.append(css[i:inicio])
        fim = css.find("*/", inicio + 2)
        if fim == -1:
            # comentario nunca fecha: o resto do arquivo some com ele.
            break
        i = fim + 2
    return "".join(pedacos)


_BLOCO_ESTRITO = re.compile(r"(?P<sel>[^{}]*)\{(?P<corpo>[^{}]*)\}", re.S)
_DECL_ESTRITA = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def _tokens_root_apos_parser_de_navegador(css_bruto: str) -> dict[str, str]:
    """So aceita um bloco como ':root' se o SELETOR INTEIRO, depois de tirar
    comentario a moda do navegador, for exatamente ":root" — nao um seletor
    invalido qualquer que contenha a palavra ":root" no meio do lixo. Um
    seletor invalido faz o navegador descartar a regra inteira.
    """
    css = _remover_comentarios_como_navegador(css_bruto)
    tokens: dict[str, str] = {}
    for bloco in _BLOCO_ESTRITO.finditer(css):
        if bloco.group("sel").strip() != ":root":
            continue
        tokens.update(
            {k: v.strip() for k, v in _DECL_ESTRITA.findall(bloco.group("corpo"))}
        )
    return tokens


_ARQUIVOS_COM_TEMA_CLARO = [("canonico (shared/brand)", CANONICAL)] + [
    (rel, RAIZ / rel) for rel in DESTINOS
]


@pytest.mark.parametrize(
    "nome,path",
    _ARQUIVOS_COM_TEMA_CLARO,
    ids=[nome for nome, _ in _ARQUIVOS_COM_TEMA_CLARO],
)
def test_root_do_tema_claro_sobrevive_ao_parser_do_navegador(nome, path):
    """Se um comentario de cabecalho tiver um "*/" literal no corpo, o
    navegador fecha o comentario cedo, o resto vira parte de um seletor
    invalido e o bloco ":root" inteiro e descartado — o tema claro (o
    default do produto) fica sem token nenhum. Este teste le o arquivo CRU
    e aplica a mesma regra de fechamento de comentario que um navegador usa;
    ele nao deve confiar no parser tolerante de tokens.py.
    """
    css_bruto = path.read_text(encoding="utf-8")
    tokens = _tokens_root_apos_parser_de_navegador(css_bruto)

    obrigatorios = ("--paper", "--brand", "--ok")
    faltando = [t for t in obrigatorios if not tokens.get(t)]
    assert not faltando, (
        f"{nome}: bloco :root do tema claro nao sobreviveu ao parser do "
        f"navegador (provavel '*/' literal dentro de um comentario de "
        f"cabecalho fechando-o cedo). Tokens ausentes: {faltando}"
    )
    assert tokens["--paper"] == "#f9f9f9", (
        f"{nome}: --paper deveria ser #f9f9f9, veio {tokens.get('--paper')!r}"
    )
