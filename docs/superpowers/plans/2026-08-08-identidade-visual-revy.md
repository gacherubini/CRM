# Identidade visual Revy — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer site, catálogo público, Revy Loja e Revy Control usarem a mesma marca, os mesmos tokens e a mesma tipografia, com o logo virando vetor de verdade.

**Architecture:** Um arquivo canônico de tokens em `shared/brand/` é copiado para os quatro front-ends por um script, e um teste falha se alguma cópia divergir. A marca é gerada em código (geometria para o símbolo, `fontTools` para o wordmark). Cada produto adota os tokens numa tarefa própria, e cada tarefa acrescenta ao teste compartilhado uma asserção que impede o valor antigo de voltar.

**Tech Stack:** CSS com custom properties · Jinja2 · Python 3 + pytest · fontTools 4.63 (já no venv do `portal-gestao`)

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-08-identidade-visual-revy-design.md`. Kit para pessoas de fora: `docs/brand/revy-brand-kit.md` v2.0.
- **Acento:** `#1f4d3a` no claro, `#7fbfa3` no escuro. `#1f4d3a` sobre fundo escuro é bug (contraste 1,6:1).
- **Preto da marca:** `#1b1b1b`. O `#0a0a0a` do catálogo e do logo é aposentado como tinta (segue sendo `--paper` do modo escuro).
- **Fontes:** Hanken Grotesk na interface; Newsreader 300 **só** na frase de marca (login, manchete do site, criativo). Preço do catálogo é Hanken com `tabular-nums`.
- **Raio:** 3px em controle, 8px em item de menu, 12px em painel e card. Não existe quarto valor.
- **Modo escuro é só dos painéis.** `site/` e `catalogo-publico/` declaram `color-scheme: light` e nunca recebem `data-theme`.
- **Cor nunca vem sozinha:** todo estado tem ponto *e* palavra escrita.
- **Não mexer nos 13 itens recusados** em `docs/2026-08-07-triagem-revisao-ux-loja-control.md`. Em especial: o card "Google Ads — Indisponível" (`L2`) e o "Simulações — em construção" no rodapé (`L6`) **ficam**.
- **Não redesenhar telas.** Trocar marca, cor, forma e tipo — não mover informação nem mudar fluxo. Única exceção: o card de veículo do catálogo.
- **Rodar os testes compartilhados a partir da raiz do repositório:**
  `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
- **`revy-trafego` não tem `.venv`** — use o do `portal-gestao` para rodar os testes dele.
- Encerrar cada tarefa com `git diff --check` e `git status --short` limpos.

---

## Estrutura de arquivos

**Criados:**

| Arquivo | Responsabilidade |
|---|---|
| `shared/brand/revy-tokens.css` | Fonte única dos tokens. Só `:root` e `[data-theme="dark"]`. Nenhuma regra de componente. |
| `shared/brand/tokens.py` | Lê o CSS e devolve `dict` de tokens; calcula contraste WCAG. |
| `shared/brand/sync_tokens.py` | Copia o canônico para os quatro produtos. |
| `shared/brand/build_marca.py` | Gera os SVG da marca (símbolo por geometria, wordmark por `fontTools`). |
| `shared/brand/tests/test_tokens.py` | Contraste AA, sincronia das cópias, valores proibidos. |
| `shared/brand/tests/test_marca.py` | Nenhum SVG de marca contém `<text>`. |
| `docs/brand/assets/*.svg` | Marca em contorno. |

**Modificados:**

| Arquivo | O que muda |
|---|---|
| `portal-gestao/app/static/css/app.css:2055-2080` | Camada de marca: azul → verde |
| `portal-gestao/app/static/css/app.css:836-880` | `.status` vira Ponto |
| `portal-gestao/app/templates/base.html` | `<link>` dos tokens, símbolo SVG, Newsreader |
| `portal-gestao/app/templates/login.html` | Frase em Newsreader, painel sempre preto |
| `portal-gestao/app/templates/loja/vendas_visao.html` | KPI perde `<small>` |
| `revy-trafego/app/static/css/app.css:2149-2175` | Mesma troca da camada |
| `revy-trafego/app/templates/base.html` | `<link>` dos tokens, símbolo SVG |
| `catalogo-publico/app/static/css/catalog.css:39` | Inter → Hanken; tokens; card Vitrine |
| `catalogo-publico/app/templates/base.html:11` | Google Fonts: Inter → Hanken |
| `site/index.html` | Tokens, Newsreader nas manchetes, botão reto, logos novos |

---

## Task 1: Tokens canônicos e verificador de contraste

**Files:**
- Create: `shared/brand/revy-tokens.css`
- Create: `shared/brand/tokens.py`
- Test: `shared/brand/tests/test_tokens.py`

**Interfaces:**
- Produces: `tokens.load_tokens(path) -> dict[str, dict[str, str]]` com chaves `"light"` e `"dark"`; `tokens.contrast(fg: str, bg: str) -> float` (razão WCAG, 1.0–21.0); `tokens.CANONICAL` (`pathlib.Path` do `revy-tokens.css`).

- [ ] **Step 1: Escrever o teste que falha**

`shared/brand/tests/test_tokens.py`:

```python
"""Guarda dos tokens de marca.

Contraste nao e opiniao: se um par cair abaixo de 4.5:1 o texto fica ilegivel
para parte dos usuarios. Este teste existe para que uma futura troca de cor
quebre aqui, e nao na tela do lojista.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import CANONICAL, contrast, load_tokens

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
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'tokens'`

- [ ] **Step 3: Escrever `shared/brand/tokens.py`**

```python
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

    return {"light": light, "dark": {**light, **dark_overrides}}


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
```

- [ ] **Step 4: Escrever `shared/brand/revy-tokens.css`**

```css
/* ===========================================================================
   Revy — tokens de marca. FONTE UNICA.
   Edite este arquivo; nunca as copias em */static/css/revy-tokens.css.
   Depois de editar: python shared/brand/sync_tokens.py
   Spec: docs/superpowers/specs/2026-08-08-identidade-visual-revy-design.md
   =========================================================================== */
:root {
  /* --- neutros --- */
  --paper: #f9f9f9;
  --surface: #ffffff;
  --surface-raised: #f4f2f1;
  --surface-soft: #efeceb;
  --ink: #1b1b1b;
  --ink-soft: #57514f;
  --ink-muted: #6b625f;
  --line: #ded8d9;
  --line-strong: #cdc6c4;
  --shadow: 0 1px 2px rgba(27, 20, 20, .05);

  /* --- acento: escala do verde racing --- */
  --green-900: #0f2b20;
  --green-700: #1f4d3a;
  --green-500: #2f7355;
  --green-300: #7fbfa3;
  --green-100: #dfeee7;

  --brand: var(--green-700);
  --brand-strong: #1a4231;
  --brand-ink: #ffffff;
  --brand-tint: rgba(31, 77, 58, .09);
  --brand-line: rgba(31, 77, 58, .32);

  /* --- estado --- */
  --st-wait: #8a6d1d;
  --st-live: #57514f;
  --st-prop: #1f4d3a;
  --st-won: #0d7a4f;
  --st-lost: #6b625f;

  --ok: #0d7a4f;
  --amber: #8a6d1d;
  --warn: #8a6d1d;
  --danger: #b42318;
  --red: #b42318;
  --green: #0d7a4f;
  --whatsapp: #25d366;
  --online: #25d366;

  /* --- forma --- */
  --radius-ctl: 3px;
  --radius-nav: 8px;
  --radius-srf: 12px;
  --radius: 12px;

  /* --- tipografia --- */
  --font-ui: "Hanken Grotesk", "Segoe UI", ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-brand: "Newsreader", Georgia, "Times New Roman", serif;
  --font-data: ui-monospace, "Consolas", "SF Mono", monospace;
}

/* O modo escuro e dos paineis. site/ e catalogo-publico/ nunca recebem
   data-theme e declaram color-scheme: light. */
[data-theme="dark"] {
  --paper: #0a0a0a;
  --surface: #111111;
  --surface-raised: #161616;
  --surface-soft: #1a1a1a;
  --ink: #f5f5f5;
  --ink-soft: #a3a3a3;
  --ink-muted: #949494;
  --line: #2a2a2a;
  --line-strong: #3a3a3a;
  --shadow: none;

  /* O acento sobe para o 300: o 700 da 1,6:1 sobre #0a0a0a. */
  --brand: var(--green-300);
  --brand-strong: #9ed0ba;
  --brand-ink: #0a0a0a;
  --brand-tint: rgba(127, 191, 163, .14);
  --brand-line: rgba(127, 191, 163, .34);

  --st-wait: #d9b04a;
  --st-live: #a3a3a3;
  --st-prop: #7fbfa3;
  --st-won: #3ecf8e;
  --st-lost: #949494;

  --ok: #3ecf8e;
  --amber: #d9b04a;
  --warn: #d9b04a;
  --danger: #f97066;
  --red: #f97066;
  --green: #3ecf8e;
}
```

> `--brand` usa `var(--green-700)`, mas o parser de `tokens.py` devolve a string literal
> `var(--green-700)`, que `contrast()` não sabe ler. Resolva na Step 5.

- [ ] **Step 5: Resolver `var()` no parser**

Acrescente a `shared/brand/tokens.py`, antes de `_canal`:

```python
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
```

E, no fim de `load_tokens`, antes do `return`:

```python
    dark = {**light, **dark_overrides}
    light = {k: _resolver(v, light) for k, v in light.items()}
    dark = {k: _resolver(v, dark) for k, v in dark.items()}
    return {"light": light, "dark": dark}
```

Remova o `return {"light": light, "dark": {**light, **dark_overrides}}` antigo.

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS — 23 testes (20 pares de contraste + 3 asserções de valor)

- [ ] **Step 7: Commit**

```bash
git add shared/brand/revy-tokens.css shared/brand/tokens.py shared/brand/tests/test_tokens.py
git commit -m "feat(marca): tokens canonicos com guarda de contraste AA"
```

---

## Task 2: Sincronizar as cópias nos quatro produtos

**Files:**
- Create: `shared/brand/sync_tokens.py`
- Modify: `shared/brand/tests/test_tokens.py` (acrescenta teste de sincronia)
- Create (gerados): as quatro cópias em `DESTINOS`

**Interfaces:**
- Consumes: `tokens.CANONICAL`, `tokens.DESTINOS`, `tokens.RAIZ` (Task 1)
- Produces: `sync_tokens.sincronizar() -> list[Path]` (as cópias escritas); `sync_tokens.divergentes() -> list[Path]` (as que não batem)

- [ ] **Step 1: Escrever o teste que falha**

Acrescente ao fim de `shared/brand/tests/test_tokens.py`:

```python
from sync_tokens import divergentes


def test_copias_em_dia():
    """Se este teste falhar, alguem editou uma copia em vez do canonico.
    Rode: python shared/brand/sync_tokens.py
    """
    fora = divergentes()
    assert not fora, "copias divergentes do canonico: " + ", ".join(str(p) for p in fora)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync_tokens'`

- [ ] **Step 3: Escrever `shared/brand/sync_tokens.py`**

```python
"""Copia os tokens canonicos para os quatro front-ends.

Por que copia e nao import HTTP: cada produto e um deploy independente. Uma
folha de estilo buscada de outro servico criaria um modo de falha novo — o
Control fora do ar despintaria o catalogo — para resolver o que uma copia
com teste de sincronia ja resolve.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tokens import CANONICAL, DESTINOS, RAIZ

CABECALHO = (
    "/* GERADO por shared/brand/sync_tokens.py — NAO EDITE.\n"
    "   Edite shared/brand/revy-tokens.css e rode o script. */\n"
)


def _conteudo() -> str:
    return CABECALHO + CANONICAL.read_text(encoding="utf-8")


def sincronizar() -> list[Path]:
    escritas = []
    alvo = _conteudo()
    for rel in DESTINOS:
        destino = RAIZ / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(alvo, encoding="utf-8", newline="\n")
        escritas.append(destino)
    return escritas


def divergentes() -> list[Path]:
    alvo = _conteudo()
    fora = []
    for rel in DESTINOS:
        destino = RAIZ / rel
        if not destino.exists() or destino.read_text(encoding="utf-8") != alvo:
            fora.append(destino)
    return fora


if __name__ == "__main__":
    for p in sincronizar():
        print("escrito:", p.relative_to(RAIZ))
```

- [ ] **Step 4: Rodar o script**

Run: `portal-gestao/.venv/Scripts/python.exe shared/brand/sync_tokens.py`
Expected: quatro linhas `escrito: ...`

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add shared/brand/sync_tokens.py shared/brand/tests/test_tokens.py \
        portal-gestao/app/static/css/revy-tokens.css \
        revy-trafego/app/static/css/revy-tokens.css \
        catalogo-publico/app/static/css/revy-tokens.css \
        site/assets/revy-tokens.css
git commit -m "feat(marca): distribui tokens por copia verificada nos quatro front-ends"
```

---

## Task 3: A marca em vetor

**Files:**
- Create: `shared/brand/build_marca.py`
- Create: `shared/brand/tests/test_marca.py`
- Create (gerados): `docs/brand/assets/revy-mark.svg`, `revy-mark-reverse.svg`, `revy-wordmark.svg`, `revy-signature.svg`, `revy-signature-reverse.svg`, `favicon.svg`

**Interfaces:**
- Produces: `build_marca.SIMBOLO_PATHS` (tupla de `d=` do R), `build_marca.gerar() -> list[Path]`

- [ ] **Step 1: Escrever o teste que falha**

`shared/brand/tests/test_marca.py`:

```python
"""O logo anterior era <text font-family="Inter">: letra viva, sem contorno.
Mudava de forma conforme a maquina e nao dava para levar a impresso nem ao
Canva. Este teste impede que volte.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from tokens import RAIZ

ASSETS = RAIZ / "docs" / "brand" / "assets"

ESPERADOS = [
    "revy-mark.svg",
    "revy-mark-reverse.svg",
    "revy-wordmark.svg",
    "revy-signature.svg",
    "revy-signature-reverse.svg",
    "favicon.svg",
]


@pytest.mark.parametrize("nome", ESPERADOS)
def test_arquivo_existe(nome):
    assert (ASSETS / nome).is_file()


@pytest.mark.parametrize("nome", ESPERADOS)
def test_sem_texto_vivo(nome):
    svg = (ASSETS / nome).read_text(encoding="utf-8")
    assert "<text" not in svg, f"{nome} tem <text>: nao e contorno"
    assert "font-family" not in svg, f"{nome} depende de fonte instalada"


def test_simbolo_e_preto():
    svg = (ASSETS / "revy-mark.svg").read_text(encoding="utf-8")
    assert "#1b1b1b" in svg
    assert "#1f4d3a" not in svg, "o simbolo nao e verde"


def test_reversa_tem_fio_de_contraste():
    """Quadrado preto sobre sidebar #161616 sumiria sem o fio."""
    svg = (ASSETS / "revy-mark-reverse.svg").read_text(encoding="utf-8")
    assert "#000000" in svg
    assert "rgba(255,255,255,.16)" in svg
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_marca.py -q`
Expected: FAIL — todos os arquivos ausentes

- [ ] **Step 3: Escrever `shared/brand/build_marca.py`**

```python
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
    corpo_nome = "\n".join(f'    <path d="{d}"/>' for d in ds_nome)
    corpo_desc = "\n".join(f'    <path d="{d}"/>' for d in ds_desc)
    altura = upem * 1.35

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larg_nome:.0f} {altura:.0f}" '
        'role="img" aria-label="Revy — Gestao de revenda">\n'
        f'  <g fill="{tinta}" transform="translate(0 {upem * 0.74:.0f})">\n{corpo_nome}\n  </g>\n'
        f'  <g fill="{tinta_descritor}" transform="translate(0 {altura * 0.97:.0f}) '
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
```

- [ ] **Step 4: Rodar o gerador**

Run: `portal-gestao/.venv/Scripts/python.exe shared/brand/build_marca.py`
Expected: seis linhas `gerado: docs/brand/assets/...`

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

- [ ] **Step 6: Conferir a olho**

Abra `docs/brand/assets/revy-signature.svg` no navegador. O descritor deve ler
"GESTAO DE REVENDA" alinhado à esquerda sob "Revy", sem sobreposição.
Se a linha de base estiver errada, ajuste os fatores `0.74` e `0.97` em `_svg_assinatura`.
**Não siga para a Task 4 sem essa conferência** — os SVG entram em produção na Task 5.

> **Os PNG do spec (§6) ficam de fora desta tarefa.** `favicon-32.png` e
> `apple-touch-icon-180.png` exigem um rasterizador (`cairosvg` ou `Pillow` + `cairo`),
> que nenhum venv tem. `favicon.svg` cobre todo navegador atual; os PNG só importam para
> iOS antigo e para o atalho na tela inicial. Fica registrado como pendência no kit
> (Task 10) em vez de arrastar uma dependência nova de imagem para dentro do repositório.

- [ ] **Step 7: Substituir os arquivos antigos do site**

```bash
cp docs/brand/assets/revy-mark.svg site/assets/revy-mark.svg
cp docs/brand/assets/revy-wordmark.svg site/assets/revy-wordmark.svg
cp docs/brand/assets/revy-signature.svg site/assets/revy-signature.svg
cp docs/brand/assets/revy-signature-reverse.svg site/assets/revy-signature-reverse.svg
git rm site/assets/revy-logo-full-dark.svg site/assets/revy-logo-full-light.svg \
       site/assets/revy-wordmark-light.svg
```

- [ ] **Step 8: Commit**

```bash
git add shared/brand/build_marca.py shared/brand/tests/test_marca.py \
        docs/brand/assets site/assets
git commit -m "feat(marca): logo em contorno vetorial, gerado por fontTools"
```

---

## Task 4: Revy Loja — acento verde e símbolo

**Files:**
- Modify: `portal-gestao/app/static/css/app.css:2055-2080` (bloco "Camada Revy 2026")
- Modify: `portal-gestao/app/templates/base.html:11` (link dos tokens), `:32` (`.brand-mark`)
- Modify: `shared/brand/tests/test_tokens.py` (guarda contra o azul)

**Interfaces:**
- Consumes: `revy-tokens.css` (Task 2), `docs/brand/assets/revy-mark.svg` (Task 3)

- [ ] **Step 1: Escrever o teste que falha**

Acrescente ao fim de `shared/brand/tests/test_tokens.py`:

```python
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
```

E acrescente `RAIZ` ao import do topo do arquivo:

```python
from tokens import CANONICAL, RAIZ, contrast, load_tokens
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q -k azul`
Expected: FAIL nos dois CSS (`#1f6feb`, `#5a95ff`, ...)

- [ ] **Step 3: Trocar a camada de marca do Portal**

Em `portal-gestao/app/static/css/app.css`, substitua os dois blocos de token da
"Camada Revy 2026" (a partir da linha ~2059) por:

```css
:root,
[data-theme="light"] {
  --brand: #1f4d3a;
  --brand-strong: #1a4231;
  --brand-ink: #ffffff;
  --brand-tint: rgba(31, 77, 58, .09);
  --brand-line: rgba(31, 77, 58, .32);
}
[data-theme="dark"] {
  /* Passo 300 da escala. O 700 (#1f4d3a) da 1,6:1 sobre #0a0a0a. */
  --brand: #7fbfa3;
  --brand-strong: #9ed0ba;
  --brand-ink: #0a0a0a;
  --brand-tint: rgba(127, 191, 163, .14);
  --brand-line: rgba(127, 191, 163, .34);
}
```

E substitua as três linhas de `.brand-mark` logo abaixo por:

```css
/* A marca e preta nos dois temas — nunca verde. O simbolo agora vem do SVG
   em docs/brand/assets; .brand-mark so posiciona. */
.brand-mark {
  background: transparent;
  color: inherit;
  padding: 0;
}
.brand-mark svg { width: 32px; height: 32px; display: block; }
```

- [ ] **Step 4: Trocar o `<span>` da marca pelo SVG**

Em `portal-gestao/app/templates/base.html`, linha 32, troque:

```html
<span class="brand-mark" aria-hidden="true">R</span>
```

por:

```html
<span class="brand-mark" aria-hidden="true">
  <svg viewBox="0 0 40 40" role="img" aria-label="Revy">
    <rect width="40" height="40" rx="9" fill="#1b1b1b"/>
    <rect class="brand-mark-edge" x="1" y="1" width="38" height="38" rx="8" fill="none" stroke="transparent" stroke-width="2"/>
    <path d="M15.5 30V13h6.8a4.3 4.3 0 0 1 0 8.6h-6.8" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M21 21.6 27 30" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/>
  </svg>
</span>
```

E acrescente à camada de marca do CSS, logo depois de `.brand-mark svg`:

```css
/* No escuro o quadrado preto sobre a sidebar #161616 sumiria sem o fio. */
[data-theme="dark"] .brand-mark rect:first-of-type { fill: #000000; }
[data-theme="dark"] .brand-mark .brand-mark-edge { stroke: rgba(255,255,255,.16); }
[data-theme="dark"] .brand-mark path { stroke: #f5f5f5; }
```

- [ ] **Step 5: Ligar o arquivo de tokens**

Em `portal-gestao/app/templates/base.html`, **antes** da linha 11 (`app.css`):

```html
<link rel="stylesheet" href="/static/css/revy-tokens.css?v=marca2">
```

E troque `?v=suave` por `?v=marca2` no `<link>` do `app.css`, para furar o cache.

Faça a mesma troca de `<link>` em `portal-gestao/app/templates/login.html` (linha 11).

- [ ] **Step 6: Rodar os testes**

```bash
portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q
cd portal-gestao && .venv/Scripts/python.exe -m pytest -q && cd ..
```
Expected: ambos PASS

- [ ] **Step 7: Conferir a olho**

Suba o Portal e abra `/app/loja/vendas` nos dois temas. Item de menu ativo deve estar
verde (tint + barra + ícone), e o quadradinho da marca preto nos dois — com um fio
visível no escuro.

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/static/css/app.css portal-gestao/app/templates/base.html \
        portal-gestao/app/templates/login.html shared/brand/tests/test_tokens.py
git commit -m "feat(loja): acento verde e marca preta vetorizada"
```

---

## Task 5: Revy Loja — botões retos, estado em ponto, KPI sem explicação

**Files:**
- Modify: `portal-gestao/app/static/css/app.css` (camada de marca, no fim)
- Modify: `portal-gestao/app/templates/loja/vendas_visao.html`

**Interfaces:**
- Consumes: `--radius-ctl`, `--st-*` de `revy-tokens.css` (Task 2)

> **Atenção de escopo:** `.status` é usado em todo o produto — veículo (`disponivel`,
> `reservado`, `vendido`), lead (`novo`, `qualificado`), canal (`conectado`,
> `desconectado`) e loja (`ativa`, `em_configuracao`). São três grupos de cor em
> `app.css:848-880`. A mudança para Ponto vale para **todos**, o que é o objetivo:
> uma forma só de mostrar estado no produto inteiro.

- [ ] **Step 1: Acrescentar o estilo Ponto na camada de marca**

No fim de `portal-gestao/app/static/css/app.css`:

```css
/* ===========================================================================
   Estado em ponto (2026-08-08)
   A pilula cheia virava mosaico numa fila longa. Agora a cor vive no ponto e
   o texto fica neutro: cor + forma + palavra, nunca cor sozinha.
   O grupo de cor de cada estado continua em app.css:848-880; aqui so trocamos
   a FORMA e movemos a cor de `color` para `--sc`.
   =========================================================================== */
.status,
.status-pill {
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  color: var(--ink-soft);
  font-weight: 500;
  gap: 6px;
}
.status::before,
.status-pill::before {
  width: 7px;
  height: 7px;
  background: var(--sc, var(--ink-muted));
}

/* Os tres grupos herdados passam a definir --sc em vez de background+color. */
.status.disponivel, .status.novo, .status.qualificado, .status.convertido,
.status.ativa, .status.ativo, .status.conectado, .status.pronta {
  background: transparent;
  color: var(--ink-soft);
  --sc: var(--st-won);
}
.status.reservado, .status.aguardando_simulacao, .status.aguardando_cliente,
.status.warn, .status.em_configuracao, .status.rascunho, .status.pendente,
.status.desconectado {
  background: transparent;
  color: var(--ink-soft);
  --sc: var(--st-wait);
}
/* Em atendimento sai do ambar: quem exige acao e quem espera, nao quem ja
   esta sendo atendido. Negociacao (Proposta) ganha o acento. */
.status.em_atendimento {
  background: transparent;
  color: var(--ink-soft);
  --sc: var(--st-live);
}
.status.negociacao {
  background: transparent;
  color: var(--ink-soft);
  --sc: var(--st-prop);
}
/* Terminais nao recebem ponto: nao disputam atencao com quem esta esperando. */
.status.vendido, .status.perdido, .status.indisponivel,
.status.suspensa, .status.encerrada, .status.inativo {
  background: transparent;
  color: var(--ink-muted);
  font-weight: 500;
}
.status.vendido::before, .status.perdido::before, .status.indisponivel::before,
.status.suspensa::before, .status.encerrada::before, .status.inativo::before {
  display: none;
}

/* --- Botao reto (3px) --- */
.button, .link-button, input, select, textarea, .search, .filter-bar select {
  border-radius: var(--radius-ctl);
}
.nav-link { border-radius: var(--radius-nav); }
.panel, .metric-grid > .panel { border-radius: var(--radius-srf); }
```

- [ ] **Step 2: Conferir os valores de estado contra o enum real**

Run: `rg -n "estados\s*=" portal-gestao/app/web/loja_*.py portal-gestao/app/main.py`

Compare as chaves do dicionário `estados` com as classes listadas na Step 1.
Se houver estado sem grupo (por exemplo `ganho`), acrescente-o ao grupo certo.
**Um estado sem grupo cai no `--sc` padrão (`--ink-muted`) e some — por isso a conferência.**

- [ ] **Step 3: Tirar a linha de explicação dos KPI**

Em `portal-gestao/app/templates/loja/vendas_visao.html`, remova os `<small>` de dentro
de `.metric` **quando forem só descrição do rótulo**. Exemplo, linhas 42-51:

```html
<div class="metric">
  <span>Vendas confirmadas</span>
  <strong>{{ overview.qtd_vendas }}</strong>
</div>
<div class="metric">
  <span>Receita</span>
  <strong>{{ formatar_brl(overview.receita) }}</strong>
</div>
```

**Mantenha** os `<small>` que carregam informação que o número não dá — o de
margem incompleta (linhas 60-63) e o de meta (`meta: X · Y%`). A regra é
"um rótulo por número", não "apagar contexto".

- [ ] **Step 4: Rodar os testes**

```bash
portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q
cd portal-gestao && .venv/Scripts/python.exe -m pytest -q && cd ..
```
Expected: PASS. Se algum teste procurar texto de `<small>` removido, ajuste o teste —
ele estava afirmando copy, não comportamento.

- [ ] **Step 5: Conferir a olho**

`/app/loja/atendimento` nos dois temas: cada linha com ponto colorido + palavra,
sem pílula. `/app/estoque`: os estados de veículo também em ponto.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/static/css/app.css portal-gestao/app/templates/loja/vendas_visao.html
git commit -m "feat(loja): estado em ponto, botao reto e KPI sem linha de explicacao"
```

---

## Task 6: Revy Loja — login com Newsreader e painel sempre preto

**Files:**
- Modify: `portal-gestao/app/templates/login.html`
- Modify: `portal-gestao/app/static/css/app.css` (camada de marca)

- [ ] **Step 1: Carregar a Newsreader**

Em `portal-gestao/app/templates/login.html`, linha 10, troque o `<link>` do Google Fonts por:

```html
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&family=Newsreader:wght@300;400&display=swap" rel="stylesheet">
```

**Só no login.** O `base.html` do painel continua carregando apenas Hanken — a serifa
não entra em tela de trabalho.

- [ ] **Step 2: Trocar a assinatura do login**

Em `login.html`, substitua o bloco `.login-story` (linhas 33-37) por:

```html
<section class="login-story">
  <span class="login-sig">
    <b>Revy</b>
    <span>Gestão de revenda</span>
  </span>
  <h1>A revenda no ritmo certo.</h1>
  <p>WhatsApp, simulação, estoque e vendas — a operação da loja em um só lugar.</p>
</section>
```

- [ ] **Step 3: Estilos do login na camada de marca**

No fim de `portal-gestao/app/static/css/app.css`:

```css
/* ===========================================================================
   Login (2026-08-08) — o unico momento de marca dentro do produto.
   O painel da frase e SEMPRE preto: derivar de var(--ink) o deixava branco no
   modo escuro, porque la --ink e quase branco.
   =========================================================================== */
.login-story {
  background: #1b1b1b;
  color: #f7f7f7;
  padding: 56px 48px;
}
[data-theme="dark"] .login-story { background: #000000; }

.login-story h1 {
  font-family: var(--font-brand);
  font-weight: 300;
  font-size: clamp(32px, 4vw, 45px);
  letter-spacing: -.018em;
  line-height: 1.08;
  max-width: 13ch;
  color: inherit;
  text-transform: none;
}
.login-story p { color: #9a9a9a; max-width: 36ch; }

.login-sig { display: flex; flex-direction: column; gap: 5px; margin-bottom: 6px; }
.login-sig b { font-size: 26px; font-weight: 700; letter-spacing: -.05em; line-height: 1; }
.login-sig > span {
  font-size: 9px; font-weight: 700; letter-spacing: .3em;
  text-transform: uppercase; color: #7fbfa3;
}
```

- [ ] **Step 4: Rodar os testes**

```bash
cd portal-gestao && .venv/Scripts/python.exe -m pytest -q && cd ..
```
Expected: PASS

- [ ] **Step 5: Conferir a olho**

`/login` nos dois temas. O painel da esquerda tem que ser **preto nos dois**, a frase em
serifa caixa-baixa, e o descritor verde. Se a frase sair em caixa-alta ou cinza, algum
`h1`/`h2` global está vazando — foi exatamente esse bug que apareceu nos mockups.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/templates/login.html portal-gestao/app/static/css/app.css
git commit -m "feat(loja): login com frase em Newsreader e painel sempre preto"
```

---

## Task 7: Revy Control — mesmas trocas

**Files:**
- Modify: `revy-trafego/app/static/css/app.css:2149-2175` e fim do arquivo
- Modify: `revy-trafego/app/templates/base.html`

- [ ] **Step 1: Repetir a troca de tokens**

Em `revy-trafego/app/static/css/app.css`, o bloco "Camada Revy 2026" (linha ~2149) é
**idêntico** ao do Portal. Aplique exatamente a mesma substituição da **Task 4, Step 3**
(os dois blocos `:root`/`[data-theme="dark"]` e as regras de `.brand-mark`).

- [ ] **Step 2: Repetir o estilo Ponto e os raios**

No fim de `revy-trafego/app/static/css/app.css`, cole o mesmo bloco da
**Task 5, Step 1** — inclusive os comentários.

Depois rode `rg -n "\.status\." revy-trafego/app/static/css/app.css` e confira se o
Control tem estados que o Portal não tem (por exemplo `pausada`, `sem_gasto`).
Acrescente-os ao grupo certo.

- [ ] **Step 3: Ligar tokens e trocar a marca no template**

Em `revy-trafego/app/templates/base.html`, acrescente antes do `<link>` do `app.css`:

```html
<link rel="stylesheet" href="/static/css/revy-tokens.css?v=marca2">
```

E troque o `<span class="brand-mark">` pelo mesmo SVG da **Task 4, Step 4**.

- [ ] **Step 4: Rodar os testes**

```bash
portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q
cd revy-trafego && ../portal-gestao/.venv/Scripts/python.exe -m pytest -q && cd ..
```
Expected: PASS. O teste `test_azul_de_saas_nao_voltou` agora passa nos dois CSS.

> Já existe **um teste do outbox de provisionamento quebrado** no `revy-trafego`, anterior
> a este trabalho. Se ele falhar, não é regressão sua — confirme que a falha é a mesma de
> antes com `git stash` e siga.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/static/css/app.css revy-trafego/app/templates/base.html
git commit -m "feat(control): acento verde, marca vetorizada e estado em ponto"
```

---

## Task 8: Catálogo público — Hanken, tokens e card Vitrine

**Files:**
- Modify: `catalogo-publico/app/templates/base.html:7,11`
- Modify: `catalogo-publico/app/static/css/catalog.css:3-40` e o bloco do card
- Modify: `shared/brand/tests/test_tokens.py` (guarda contra Inter e `data-theme`)

- [ ] **Step 1: Escrever o teste que falha**

Acrescente ao fim de `shared/brand/tests/test_tokens.py`:

```python
SUPERFICIES_PUBLICAS = ["catalogo-publico/app", "site"]


def test_catalogo_nao_usa_mais_inter():
    for rel in ["catalogo-publico/app/static/css/catalog.css",
                "catalogo-publico/app/templates/base.html"]:
        assert "Inter" not in (RAIZ / rel).read_text(encoding="utf-8"), rel


@pytest.mark.parametrize("rel", SUPERFICIES_PUBLICAS)
def test_superficie_publica_nao_tem_tema_escuro(rel):
    """Modo escuro e dos paineis. Vitrine e site sao sempre claros."""
    base = RAIZ / rel
    arquivos = list(base.rglob("*.html")) + list(base.rglob("*.css"))
    with_theme = [f for f in arquivos if "data-theme" in f.read_text(encoding="utf-8")]
    assert not with_theme, [str(f.relative_to(RAIZ)) for f in with_theme]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q -k inter`
Expected: FAIL nos dois arquivos do catálogo

- [ ] **Step 3: Trocar a fonte no template**

`catalogo-publico/app/templates/base.html`, linha 11:

```html
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Linha 7:

```html
<meta name="theme-color" content="#f9f9f9">
```

E, antes do `<link>` do `catalog.css`:

```html
<link rel="stylesheet" href="{{ url_prefix }}/static/css/revy-tokens.css">
```

- [ ] **Step 4: Trocar os tokens locais do catálogo**

Em `catalogo-publico/app/static/css/catalog.css`, no bloco `:root` (linhas 3-40),
**remova** as declarações que agora vêm de `revy-tokens.css` — `--ink`, `--ink-soft`,
`--ink-muted`, `--paper`, `--surface`, `--surface-raised`, `--surface-soft`, `--line`,
`--line-strong`, `--accent`, `--green` — e deixe apenas as que são só do catálogo
(`--space-*`, `--text-*`, `--page-max`, `--gutter`).

Troque a linha 39:

```css
  --font: var(--font-ui);
```

E logo abaixo de `color-scheme: light;`, deixe um comentário explicando que é decisão:

```css
  /* Decisao de 08/08: a vitrine e SEMPRE clara. Foto de veiculo sobre fundo
     escuro nunca foi testada, e a vitrine nao vai ser onde isso se descobre. */
```

- [ ] **Step 5: Redesenhar o card de veículo**

A estrutura de hoje (`storefront.html:28-41`) é
`.vehicle-card > a > .card-media > img` + `.card-body` com `.eyebrow`, `h2`, `.muted` e
`.facts`. Ela **se mantém** — o que muda é que o preço sai do `.facts` e vira herói, e
tipo/ano/km viram pastilhas.

Substitua o `<div class="card-body">` (linhas 34-39) por:

```html
      <div class="card-body">
        <h2>{{ v.marca }} {{ v.modelo }}</h2>
        {% if v.versao %}<p class="muted">{{ v.versao }}</p>{% endif %}
        <strong class="card-price">{{ v.preco | moeda }}</strong>
        <div class="card-chips">
          <span>{{ v.ano_modelo }}</span>
          <span>{{ "{:,.0f}".format(v.km).replace(',', '.') }} km</span>
          {% if v.tipo %}<span>{{ v.tipo }}</span>{% endif %}
        </div>
      </div>
```

E no `catalog.css`:

```css
.vehicle-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-srf);
  overflow: hidden;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
}
.vehicle-card .card-media img {
  aspect-ratio: 16 / 10;
  object-fit: cover;
  width: 100%;
  display: block;
}
.vehicle-card .card-body {
  padding: 13px 15px 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.vehicle-card .card-body h2 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  letter-spacing: -.01em;
}
.card-price {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -.04em;
  /* Preco e Hanken com tabular: serifa aqui atrapalha leitura rapida. */
  font-variant-numeric: tabular-nums;
  color: var(--brand-strong);
  margin-top: 5px;
}
.card-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.card-chips span {
  font-size: 10.5px;
  padding: 2px 8px;
  border-radius: var(--radius-ctl);
  background: var(--surface-soft);
  color: var(--ink-muted);
}
```

**Antes de apagar as regras de `.eyebrow` e `.facts`**, confira se `vehicle.html` ainda
as usa: `rg -n "eyebrow|facts" catalogo-publico/app/templates/`. Se usar, deixe-as.

- [ ] **Step 6: Rodar os testes**

```bash
portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q
cd catalogo-publico && .venv/Scripts/python.exe -m pytest -q && cd ..
```
Expected: PASS

- [ ] **Step 7: Conferir a olho e medir**

Abra a vitrine de uma loja. Confira que a fonte mudou (Hanken tem o "g" de andar único,
a Inter tem o de dois). Meça o LCP antes e depois no DevTools — as duas fontes vêm do
mesmo CDN, então a diferença deve ficar no ruído; se passar de 200ms, registre.

- [ ] **Step 8: Commit**

```bash
git add catalogo-publico shared/brand/tests/test_tokens.py
git commit -m "feat(catalogo): Hanken no lugar de Inter, tokens compartilhados e card Vitrine"
```

---

## Task 9: Site — tokens, Newsreader nas manchetes e botão reto

**Files:**
- Modify: `site/index.html` (linhas 9-18, 33-37, 217, 384)

- [ ] **Step 1: Ligar tokens e Newsreader**

Em `site/index.html`, linha 12, troque o `<link>` do Google Fonts por:

```html
<link href='https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;600;700;900&family=Newsreader:wght@300;400&family=Material+Symbols+Outlined:wght@400&display=swap' rel='stylesheet' />
```

E acrescente, antes do `<style>`:

```html
<link rel='stylesheet' href='assets/revy-tokens.css' />
```

- [ ] **Step 2: Enxugar o `:root` inline**

Substitua o bloco `:root` (linhas 14-18) por apenas o que é do site:

```css
    :root {
      /* Cores e tipografia vem de assets/revy-tokens.css. */
      color-scheme: light;   /* o site e sempre claro */
      --max: 1280px;
      --gutter: clamp(20px, 5vw, 64px);
      --card: var(--surface);
      --soft: var(--surface-soft);
      --black: var(--ink);
      --muted: var(--ink-muted);
    }
```

E na linha 21, troque `font-family: 'Hanken Grotesk', sans-serif;` por
`font-family: var(--font-ui);`.

- [ ] **Step 3: Manchetes em Newsreader**

Substitua a regra `.section-title` (linha 31):

```css
    .section-title {
      margin: 0 0 22px;
      font-family: var(--font-brand);
      font-weight: 300;
      font-size: clamp(36px, 5vw, 56px);
      line-height: 1.1;
      letter-spacing: -.02em;
    }
```

A serifa vai **só** em `.section-title` e no `h1` do hero. `.section-copy`, navegação,
rodapé e botões continuam em Hanken.

- [ ] **Step 4: Botão reto**

Substitua a regra `.button` (linha 33):

```css
    .button {
      display: inline-flex; min-height: 48px; align-items: center; justify-content: center;
      padding: 0 28px;
      border: 1px solid var(--ink);
      border-radius: var(--radius-ctl);
      font-size: 14px; font-weight: 600;
      letter-spacing: 0;
      text-transform: none;
      transition: transform .18s, opacity .18s, background .18s;
    }
```

Mantenha `.button-dark` e `.button-light` como estão.

- [ ] **Step 5: Apontar para os logos novos**

- Linha 9: `href='assets/revy-mark.svg'` — continua, o arquivo foi regerado na Task 3
- Linha 217 (navegação): troque `revy-wordmark.svg` por `revy-signature.svg` e ajuste
  `width='96' height='34'`
- Linha 384 (rodapé): idem

- [ ] **Step 6: Rodar o teste compartilhado**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS — inclusive `test_superficie_publica_nao_tem_tema_escuro`

- [ ] **Step 7: Conferir a olho**

Abra `site/index.html` no navegador. Manchetes em serifa, corpo em Hanken, botões retos,
assinatura com o descritor. Confira em 375px de largura que a assinatura não estoura a
barra de navegação.

- [ ] **Step 8: Commit**

```bash
git add site/index.html
git commit -m "feat(site): tokens compartilhados, manchete em Newsreader e botao reto"
```

---

## Task 10: Fechar o kit e o handoff

**Files:**
- Modify: `docs/brand/revy-brand-kit.md` (checklist da seção 8)
- Modify: `docs/handoff-contexto.md`

- [ ] **Step 1: Marcar o checklist do kit**

Em `docs/brand/revy-brand-kit.md`, seção 8, marque como feitos os itens que este plano
entregou: símbolo exportado, wordmark em contorno, favicon, `shared/brand/revy-tokens.css`
criado e sincronizado, tokens aplicados nos quatro front-ends.

Deixe em aberto o que continua pendente: `docs/brand/preview.html` e `index.html`
regerados, os PNG de favicon (`favicon-32.png`, `apple-touch-icon-180.png` — precisam de
rasterizador), domínio e @ registrados.

- [ ] **Step 2: Registrar no handoff**

Em `docs/handoff-contexto.md`, acrescente uma linha ao estado atual apontando para o
spec e este plano, e dizendo em que ponto a implementação parou.

- [ ] **Step 3: Verificação final**

```bash
rg -n "1f6feb|5a95ff" --glob '!docs/**' --glob '!*.md' .
rg -n "Inter" catalogo-publico/
rg -n "data-theme" catalogo-publico/ site/
rg -n "<text" docs/brand/assets/ site/assets/
portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q
git diff --check
git status --short
```

Expected: as quatro buscas sem resultado, testes PASS, diff e status limpos.

- [ ] **Step 4: Commit**

```bash
git add docs/brand/revy-brand-kit.md docs/handoff-contexto.md
git commit -m "docs(marca): fecha checklist do kit e registra no handoff"
```

---

## Ordem e o que dá para parar no meio

Cada tarefa é enviável sozinha. Se precisar parar:

- **Depois da Task 3** — a fundação e a marca existem, nada mudou na tela. Seguro.
- **Depois da Task 6** — a Revy Loja está inteira; Control, catálogo e site seguem no azul.
  Feio (dois acentos na suíte), mas funcional.
- **Depois da Task 7** — os dois painéis prontos. É o corte natural se o tempo acabar.

O que **não** dá para parar no meio: a Task 8 sem a Task 2, porque o catálogo passa a
depender de `revy-tokens.css` para ter qualquer cor.
