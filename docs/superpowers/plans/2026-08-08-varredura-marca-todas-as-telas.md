# Varredura de marca em todas as telas — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer a identidade decidida em 08/08 alcançar as 76 telas do Revy Loja e do Revy Control, saneando a base de CSS que ainda as desenha no sistema antigo.

**Architecture:** Primeiro a fundação: o `app.css` para de redeclarar os tokens canônicos, some com o vocabulário antigo (`--accent`, `--radius`, `--green`, `--amber`, `--red`, `--online`) e dissolve a camada de marca do fim do arquivo, ganhando uma seção por peça. Depois, uma tarefa por peça de interface — botão, campo, estado, painel, tabela, número, navegação, alerta, autenticação, superfícies específicas — cada uma varrendo os **dois** arquivos de uma vez. Cada tarefa aperta uma guarda automática em `shared/brand/tests/` que impede o valor antigo de voltar.

**Tech Stack:** CSS com custom properties · Jinja2 · Python 3 + pytest (sem libs novas)

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-08-varredura-marca-todas-as-telas-design.md`. A marca em si está em `2026-08-08-identidade-visual-revy-design.md` e em `docs/brand/revy-brand-kit.md` v2.0.
- **Isto é varredura, não redesenho.** Nenhuma informação sai do lugar, nenhum fluxo muda, nenhuma tela ganha ou perde conteúdo. As duas exceções autorizadas: o `<small>` de explicação sob KPI sai (Peça 6) e o chip de estado vira ponto (Peça 3).
- **Toda tarefa mexe nos dois `app.css`.** Nenhuma fecha com só um lado feito. Loja é `portal-gestao/app/static/css/app.css`; Control é `revy-trafego/app/static/css/app.css`.
- **Raio:** `--radius-ctl` 3px (botão, campo, chip, pastilha), `--radius-nav` 8px (item de menu), `--radius-srf` 12px (painel, card, foto). Não existe quarto valor. `50%` (círculo) é geometria, não raio, e é permitido.
- **Acento:** `--brand` marca navegação, foco e ênfase de estrutura. **Nunca é cor de status.**
- **Cor nunca vem sozinha:** todo estado tem forma e palavra escrita.
- **`#1f4d3a` sobre fundo escuro é bug** (contraste 1,6:1). No escuro o acento é `#7fbfa3`.
- **Não mexer nos 13 itens recusados** em `docs/2026-08-07-triagem-revisao-ux-loja-control.md`. Em especial ficam: o card "Google Ads — Indisponível" e o "Simulações — em construção" no rodapé.
- **Não mexer em espaçamento nem hierarquia.** O problema de "gaps" que o dono viu nas prévias está fora desta rodada, por decisão explícita.
- **Não tocar em Python de produto, n8n, Fly, migrations ou contrato HTTP.** As únicas edições fora de CSS são as de template listadas nominalmente nas tarefas.
- **Não mexer em `site/` nem `catalogo-publico/`** além da reverificação da Tarefa 14 — já foram convertidos no commit `a99d04f`.
- **Comandos de teste**, sempre a partir da raiz do repositório salvo onde indicado:
  - Guardas de marca: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
  - Suíte da Loja: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`
  - Suíte do Control: `cd revy-trafego; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`
  - `revy-trafego` **não tem `.venv`** — use o do `portal-gestao`.
- **Cache de CSS:** a partir da Tarefa 3, cada tarefa de peça incrementa `?v=v1`, `?v=v2`, … São **oito** arquivos, não dois: os dois `base.html` mais seis telas standalone com `<head>` próprio (`portal-gestao/app/templates/login.html`, `convite_aceitar.html`, `senha_esqueci.html`, `senha_redefinir.html`; `revy-trafego/app/templates/login.html`, `control/convite_aceitar.html`). Confirme com `rg -n "v=v" portal-gestao revy-trafego` que as oito subiram. Sem isso a conferência visual do dono mostra a folha antiga.

### Descoberta da Tarefa 3: existem quatro camadas, não duas

A revisão da Tarefa 3 revelou que o diagnóstico do spec estava incompleto. Além da regra base e
da camada `Camada Revy 2026` (agora dissolvida em seções), existe **um terceiro grupo de blocos
ad-hoc no fim de cada arquivo**, todos datados de 2026-08-08, que já implementam parte das
decisões de marca por sobrescrita:

| Bloco | Onde | O que já faz |
|---|---|---|
| `Estado em ponto (2026-08-08)` | Loja ~2926, Control ~2564 | Forma Ponto **já aplicada**; família `--st-*` **já mapeada**, com estados do enum real que o spec não listava; terminais já sem ponto |
| `Botao reto (3px)` | Loja ~2995, Control ~2686 | `--radius-ctl` **já aplicado** a botão, campo, select, textarea, busca; `--radius-nav` ao menu; `--radius-srf` a painel |
| `Login (2026-08-08)` | Loja ~3002 | Newsreader na frase **já aplicado**; painel da história já sempre preto |

Corrigem-se, portanto, duas afirmações do spec: **o botão já está reto** e **o estado já é
ponto** — não "nunca chegaram ao produto". O que continua verdade, e é o que justifica a
varredura, é que essas decisões vivem como sobrescrita no fim do arquivo enquanto a regra base
segue com o valor antigo (`.button` com 8px, `.status` com pílula de 6px). São duas verdades
disputando o mesmo seletor, que é exatamente o que este trabalho existe para acabar.

**Regra que passa a valer para as Tarefas 4 a 13:** cada tarefa de peça funde **três** fontes na
sua seção — a regra base, o que a Tarefa 3 moveu da camada, e a fatia correspondente desses
blocos do fim — e apaga as três origens. A tarefa só está pronta quando `rg` mostra a peça num
lugar só. As seções nasceram no meio do arquivo, então enquanto o bloco do fim não for absorvido
ele **vence** a seção no cascade: escrever na seção sem apagar o bloco do fim não muda nada na
tela.
- **Conferência visual** ao fim de cada peça, no app rodando (`cd portal-gestao; docker compose up --build -d`), **nos dois temas**. Telas-testemunha: Loja — login, Atendimento (fila e conversa), Vendas → Visão, Estoque → lista, Ajustes → Integrações. Control — Visão geral, Lojas → lista, Loja → detalhe, Aquisição/ROI.
- Encerrar cada tarefa com `git diff --check` e `git status --short` limpos, e um commit por tarefa.

---

## Estrutura de arquivos

**Criados:**

| Arquivo | Responsabilidade |
|---|---|
| `shared/brand/css_audit.py` | Lê um CSS de produto e responde perguntas objetivas sobre ele: que variáveis declara, quantas vezes usa `var(--x)`, que `border-radius` literais tem, se contém um trecho. Sem opinião de estilo — só medição. |
| `shared/brand/tests/test_app_css.py` | As guardas da varredura. Cada tarefa aperta uma. |

**Modificados:**

| Arquivo | O que muda |
|---|---|
| `portal-gestao/app/static/css/app.css` | `:root` enxuto, camada do fim dissolvida, todas as peças no sistema novo |
| `revy-trafego/app/static/css/app.css` | Idem |
| `shared/brand/revy-tokens.css` | Perde os cinco apelidos genéricos na Tarefa 14 |
| `portal-gestao/app/templates/base.html` | `?v=` do CSS |
| `revy-trafego/app/templates/base.html` | `?v=` do CSS |
| Templates nominais das Peças 6 e 9 | Listados nas tarefas |

---

## Task 1: Ferramenta de auditoria e o canônico volta a pintar

O `app.css` reabre `:root` e redeclara 20 dos 40 tokens canônicos, depois do `revy-tokens.css` no cascade. Enquanto isso for verdade, editar o arquivo canônico não muda os painéis. Esta tarefa corrige isso e cria a ferramenta que as demais usam.

**Files:**
- Create: `shared/brand/css_audit.py`
- Create: `shared/brand/tests/test_app_css.py`
- Modify: `portal-gestao/app/static/css/app.css` (bloco `:root` no topo; bloco `--brand-*` da camada em ~2065-2081)
- Modify: `revy-trafego/app/static/css/app.css` (mesmos blocos, ~2155-2171)

**Interfaces:**
- Consumes: `tokens.load_tokens(path) -> dict[str, dict[str, str]]`, `tokens.CANONICAL`, `tokens.RAIZ` (já existem em `shared/brand/tokens.py`).
- Produces:
  - `css_audit.PAINEIS: list[str]` — caminhos relativos dos dois `app.css`.
  - `css_audit.variaveis_do_root(path: Path) -> set[str]` — nomes declarados em qualquer bloco `:root` / `[data-theme=...]`.
  - `css_audit.usos_de_var(path: Path, nome: str) -> int` — quantas vezes `var(--nome)` aparece.
  - `css_audit.raios_literais(path: Path) -> list[tuple[int, str]]` — `(linha, valor)` de todo `border-radius` que não seja `var(--radius-*)`, `50%`, `inherit` ou `0`.
  - `css_audit.contem(path: Path, trecho: str) -> bool`.

- [ ] **Step 1: Escrever a ferramenta de auditoria**

`shared/brand/css_audit.py`:

```python
"""Medicoes objetivas sobre os CSS de produto.

Existe para que as guardas da varredura facam perguntas verificaveis em vez de
depender de leitura humana de um arquivo de 3.000 linhas. Nao opina sobre
estilo: so conta, lista e localiza.
"""
import re
from pathlib import Path

from tokens import RAIZ, load_tokens

# Os dois paineis. Site e catalogo nao tem app.css reabrindo :root.
PAINEIS = [
    "portal-gestao/app/static/css/app.css",
    "revy-trafego/app/static/css/app.css",
]

# border-radius que NAO conta como raio de caixa:
# 50% e circulo (ponto de estado, avatar), inherit copia o pai, 0 e ausencia.
_RAIO_LIVRE = ("50%", "inherit", "0")

_RADIUS = re.compile(r"border-radius:\s*([^;]+);")


def variaveis_do_root(path: Path) -> set[str]:
    """Nomes declarados nos blocos :root / [data-theme] do arquivo.

    Reaproveita o parser do canonico: ele ja ignora declaracoes que estao
    dentro de regra de componente (como o --sc dos resultados), que sao
    locais de propósito e nao fazem parte do vocabulario global.
    """
    t = load_tokens(path)
    return set(t["light"]) | set(t["dark"])


def usos_de_var(path: Path, nome: str) -> int:
    padrao = re.compile(r"var\(\s*" + re.escape(nome) + r"\s*[,)]")
    return len(padrao.findall(path.read_text(encoding="utf-8")))


def raios_literais(path: Path) -> list[tuple[int, str]]:
    achados = []
    for n, linha in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        for valor in _RADIUS.findall(linha):
            v = valor.strip()
            if v.startswith("var(--radius-") or v in _RAIO_LIVRE:
                continue
            achados.append((n, v))
    return achados


def contem(path: Path, trecho: str) -> bool:
    return trecho in path.read_text(encoding="utf-8")


def caminho(rel: str) -> Path:
    return RAIZ / rel
```

- [ ] **Step 2: Escrever a guarda que falha**

`shared/brand/tests/test_app_css.py`:

```python
"""Guardas da varredura de marca.

O app.css de cada painel e carregado DEPOIS do revy-tokens.css. Se ele reabrir
:root e redeclarar um token canonico, o canonico deixa de pintar e a fonte
unica vira decoracao. Foi assim que o ambar do modo escuro divergiu sem que
ninguem visse. Estes testes existem para que isso quebre aqui.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from css_audit import PAINEIS, caminho, contem, raios_literais, usos_de_var, variaveis_do_root
from tokens import CANONICAL, RAIZ, load_tokens


@pytest.mark.parametrize("rel", PAINEIS)
def test_app_css_nao_redeclara_token_canonico(rel):
    """Quem redeclara vence no cascade e anula a fonte unica."""
    canonicos = set(load_tokens(CANONICAL)["light"])
    locais = variaveis_do_root(caminho(rel))
    invasores = sorted(canonicos & locais)
    assert not invasores, (
        f"{rel} redeclara {len(invasores)} token(s) canonico(s), entao "
        f"shared/brand/revy-tokens.css nao pinta: {' '.join(invasores)}"
    )
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL nos dois parâmetros, listando os 20 invasores: `--amber --brand --brand-ink --brand-line --brand-strong --brand-tint --green --ink --ink-muted --ink-soft --line --line-strong --online --paper --radius --red --shadow --surface --surface-raised --surface-soft`

- [ ] **Step 4: Apagar as redeclarações dos dois arquivos**

Em **cada** `app.css`, apagar apenas as linhas de declaração desses 20 nomes, nos três lugares onde eles aparecem:

1. o bloco `:root, [data-theme="light"]` do topo (paleta clara);
2. o bloco `[data-theme="dark"]` logo abaixo;
3. os blocos `:root, [data-theme="light"]` e `[data-theme="dark"]` **dentro da camada de marca** (`/* Camada Revy 2026 ... */`), que declaram só os cinco `--brand-*`.

O bloco `:root` de layout do topo (`--space-*`, `--text-*`, `--gutter`, `--page-inline`) **fica intacto** — não é marca. As variáveis `--accent` e `--accent-soft` também ficam por ora; saem na Tarefa 2.

Depois da edição, o topo do arquivo deve ficar assim (Loja e Control idênticos):

```css
:root {
  --space-1: 4px;
  /* ...toda a escala de espacamento e de texto, sem mudanca... */
  --gutter: var(--space-8);
  --page-inline: var(--gutter);
}

/* A paleta vem de shared/brand/revy-tokens.css, carregado antes deste arquivo.
   Nao redeclare token canonico aqui: como este arquivo vem depois no cascade,
   a redeclaracao vence e a fonte unica deixa de valer. */
:root,
[data-theme="light"] {
  --accent: #1b1b1b;
  --accent-soft: #3a3534;
}

[data-theme="dark"] {
  --accent: #f5f5f5;
  --accent-soft: #e5e5e5;
}
```

E a camada de marca perde inteiros os dois blocos de `--brand-*`, ficando com o comentário de cabeçalho e as regras de componente (`.brand-mark` em diante).

Nada muda visualmente: os valores apagados eram idênticos aos do canônico — **exceto um**, tratado no passo seguinte.

- [ ] **Step 5: Conferir a única divergência real e corrigi-la**

O `--amber` do modo escuro estava `#e3b341` no `app.css` e `#d9b04a` no canônico. Apagar a redeclaração já faz o painel adotar `#d9b04a`. Confirme que é isso que sobrou:

Run:
```bash
portal-gestao/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'shared/brand'); from tokens import load_tokens, CANONICAL; print(load_tokens(CANONICAL)['dark']['--amber'])"
```
Expected: `#d9b04a`

Run: `rg -n "e3b341" portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css`
Expected: nenhum resultado.

- [ ] **Step 6: Rodar as guardas e as suítes**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS (inclusive os testes de contraste e de sincronia que já existiam)

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS

Run: `cd revy-trafego; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS, com a mesma falha pré-existente do outbox de provisionamento — ela não é regressão desta tarefa.

- [ ] **Step 7: Conferência visual**

Suba a Loja (`cd portal-gestao; docker compose up --build -d`) e confira nos dois temas: login, Vendas → Visão, Ajustes → Integrações. Nenhuma diferença perceptível é o resultado esperado — a única mudança de valor é o âmbar do escuro, um pouco menos saturado.

- [ ] **Step 8: Commit**

```bash
git add shared/brand/css_audit.py shared/brand/tests/test_app_css.py portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css
git commit -m "fix(marca): o app.css para de anular os tokens canonicos"
```

---

## Task 2: Vocabulário do `:root` travado

Sobram `--accent` e `--accent-soft`: o "preto como acento" do sistema anterior ao verde. Esta tarefa os elimina e tranca o `:root` num vocabulário fechado, garantindo de quebra que Loja e Control não divirjam na escala de layout.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: `portal-gestao/app/static/css/app.css` (3 usos de `var(--accent)`; declarações)
- Modify: `revy-trafego/app/static/css/app.css` (0 usos; só as declarações)

**Interfaces:**
- Consumes: `css_audit.PAINEIS`, `css_audit.caminho`, `css_audit.variaveis_do_root`, `css_audit.usos_de_var`.
- Produces: `test_app_css.LAYOUT_PERMITIDO: set[str]` — o vocabulário local fechado, usado como referência pelas tarefas seguintes.

- [ ] **Step 1: Escrever a guarda que falha**

Acrescentar a `shared/brand/tests/test_app_css.py`:

```python
# Unico vocabulario que o app.css pode declarar por conta propria: escala de
# layout. Ritmo e densidade de painel nao sao marca, entao nao vao para o
# canonico; mas os dois paineis compartilham o mesmo shell e nao podem divergir.
LAYOUT_PERMITIDO = {
    "--space-1", "--space-2", "--space-3", "--space-4", "--space-5",
    "--space-6", "--space-7", "--space-8", "--space-9",
    "--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl",
    "--text-display-sm", "--text-display", "--text-metric",
    "--gutter", "--page-inline",
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_root_so_declara_escala_de_layout(rel):
    sobrando = sorted(variaveis_do_root(caminho(rel)) - LAYOUT_PERMITIDO)
    assert not sobrando, f"{rel} declara fora do vocabulario de layout: {sobrando}"


def test_escala_de_layout_identica_entre_os_dois_paineis():
    """Loja e Control tem o mesmo shell. Se o ritmo divergir, as duas telas
    equivalentes deixam de parecer o mesmo produto."""
    a = load_tokens(caminho(PAINEIS[0]))["light"]
    b = load_tokens(caminho(PAINEIS[1]))["light"]
    diferentes = sorted(k for k in set(a) & set(b) if a[k].strip() != b[k].strip())
    assert set(a) == set(b), f"conjuntos diferentes: {set(a) ^ set(b)}"
    assert not diferentes, f"mesmo nome, valor diferente: {diferentes}"


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("morto", ["--accent", "--accent-soft"])
def test_acento_preto_do_sistema_antigo_nao_volta(rel, morto):
    """O preto deixou de ser acento quando o verde entrou, em 08/08."""
    assert usos_de_var(caminho(rel), morto) == 0, f"{rel} ainda usa var({morto})"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL em `test_root_so_declara_escala_de_layout` (os dois painéis declaram `--accent` e `--accent-soft`) e em `test_acento_preto_do_sistema_antigo_nao_volta` para a Loja.

- [ ] **Step 3: Reescrever os três usos de `var(--accent)` na Loja**

Run: `rg -n "var\(--accent" portal-gestao/app/static/css/app.css`

Para cada um, escolha pelo papel — não mecanicamente:

- acento que hoje significa **tinta forte** (título, número, texto de ênfase) → `var(--ink)`;
- acento que hoje significa **cor da marca** (foco, seleção, elemento ativo) → `var(--brand)`.

O caso conhecido é o anel de foco `box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent)`, que é foco e portanto vira `var(--brand)`. Confira os outros dois no contexto antes de trocar.

- [ ] **Step 4: Apagar as declarações nos dois arquivos**

Remover `--accent` e `--accent-soft` dos blocos claro e escuro dos **dois** `app.css`. O bloco `:root, [data-theme="light"]` que a Tarefa 1 deixou só com essas duas variáveis desaparece por inteiro, junto com o `[data-theme="dark"]` equivalente. O comentário explicando por que não se declara token canônico aqui **fica**, movido para junto do `:root` de layout.

- [ ] **Step 5: Rodar as guardas e as suítes**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q` e `cd revy-trafego; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (com a falha pré-existente conhecida no Control)

- [ ] **Step 6: Conferência visual**

Nos dois temas, confira o **anel de foco**: dê Tab por um formulário da Loja (Ajustes → Números de WhatsApp). O anel passa a ser verde no claro e verde-claro no escuro, em vez de preto/branco.

- [ ] **Step 7: Commit**

```bash
git add shared/brand/tests/test_app_css.py portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css
git commit -m "refactor(marca): aposenta o preto-como-acento e tranca o :root na escala de layout"
```

---

## Task 3: A camada do fim é dissolvida

A camada `/* Camada Revy 2026 */` foi escrita para vencer no cascade sem mexer no que existia. Cumprido o papel, ela agora atrapalha: `.button` tem regra na linha 519 e outra na 2101, e quem lê o arquivo não sabe qual vale. Esta tarefa devolve cada regra à peça dela e cria a estrutura de seções que as tarefas seguintes vão usar.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: `portal-gestao/app/static/css/app.css`
- Modify: `revy-trafego/app/static/css/app.css`
- Modify: `portal-gestao/app/templates/base.html:11-12`
- Modify: `revy-trafego/app/templates/base.html:11-12`

**Interfaces:**
- Consumes: `css_audit.contem`, `css_audit.PAINEIS`, `css_audit.caminho`.
- Produces: `test_app_css.SECOES: list[str]` — os títulos das nove seções de peça, na ordem em que aparecem no arquivo. As tarefas 4 a 13 escrevem cada uma dentro da sua.

- [ ] **Step 1: Escrever a guarda que falha**

Acrescentar a `shared/brand/tests/test_app_css.py`:

```python
from css_audit import contem

# Uma secao por peca de interface, na ordem do arquivo. Cada tarefa de peca
# escreve dentro da sua: e isso que impede a regra de uma peca de nascer a
# 1.500 linhas da outra regra da mesma peca.
SECOES = [
    "Botao",
    "Campo e formulario",
    "Estado",
    "Painel e card",
    "Tabela e lista",
    "Numero e grafico",
    "Navegacao e shell",
    "Alerta, faixa e vazio",
    "Autenticacao",
]


@pytest.mark.parametrize("rel", PAINEIS)
def test_camada_do_fim_foi_dissolvida(rel):
    """Enquanto ela existir, cada peca tem duas regras disputando o seletor."""
    assert not contem(caminho(rel), "Camada Revy 2026"), (
        f"{rel} ainda tem a camada de sobrescritas no fim do arquivo"
    )


@pytest.mark.parametrize("rel", PAINEIS)
def test_arquivo_tem_uma_secao_por_peca(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    faltando = [s for s in SECOES if f"=== {s} ===" not in css]
    assert not faltando, f"{rel} sem secao para: {faltando}"


@pytest.mark.parametrize("rel", PAINEIS)
def test_secoes_estao_na_ordem_declarada(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    posicoes = [css.index(f"=== {s} ===") for s in SECOES]
    assert posicoes == sorted(posicoes), f"{rel} tem secoes fora de ordem"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL nos três testes novos, nos dois painéis.

- [ ] **Step 3: Criar as nove seções vazias**

Em cada `app.css`, ao fim do arquivo (onde a camada estava), abrir as nove seções na ordem de `SECOES`, cada uma com este cabeçalho:

```css
/* ===========================================================================
   Botao
   =========================================================================== */
```

Elas nascem vazias. As tarefas 4 a 13 as preenchem movendo regras para dentro.

- [ ] **Step 4: Mover cada regra da camada para a seção dela**

Percorra a camada de cima para baixo e realoque, **sem alterar nenhuma declaração**:

| Regra da camada | Seção de destino |
|---|---|
| `.brand-mark`, `.brand-mark svg`, os dois `[data-theme="dark"] .brand-mark …` | Navegacao e shell |
| `:focus-visible { outline-color: … }` | Campo e formulario |
| `.button.primary` e seu `:hover` | Botao |
| `.nav-link.active`, `.nav-link.active::before`, `[data-theme="dark"] .nav-link.active`, todas as `.nav-link svg` | Navegacao e shell |
| `.status, .status-pill` e os `::before` | Estado |
| `.control-tab.is-active` | Navegacao e shell |
| `.alert` e `.alert::before` (e o ajuste de multi-linha) | Alerta, faixa e vazio |
| `.empty` com ícone de marca | Alerta, faixa e vazio |
| Cartão-resumo em destaque | Painel e card |
| Sparkline / mini-gráfico | Numero e grafico |
| Painel de status das integrações | Painel e card |

Apagar o cabeçalho `/* === Camada Revy 2026 === */` e o comentário que manda editar os `--brand-*` ali — eles não existem mais desde a Tarefa 1.

**A regra antiga de cada peça continua onde está**, mais acima no arquivo. Isso é intencional: as tarefas 4 a 13 é que fundem as duas. Nesta tarefa a ordem no cascade tem de permanecer a mesma, ou seja, a regra movida continua *depois* da antiga.

- [ ] **Step 5: Subir o cache-buster**

Em `portal-gestao/app/templates/base.html` e `revy-trafego/app/templates/base.html`, trocar `?v=marca3` por `?v=v1` nas duas linhas de cada arquivo (`revy-tokens.css` e `app.css`).

- [ ] **Step 6: Rodar as guardas e as suítes**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

Run: as duas suítes de produto.
Expected: PASS (com a falha pré-existente conhecida no Control)

- [ ] **Step 7: Conferência visual completa**

Esta é a tarefa com maior risco de mover algo sem querer, porque muda ordem de regra. Percorra **todas** as telas-testemunha dos dois produtos, nos dois temas, e compare com o estado anterior. **Nada pode ter mudado de aparência.**

- [ ] **Step 8: Commit**

```bash
git add portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css portal-gestao/app/templates/base.html revy-trafego/app/templates/base.html shared/brand/tests/test_app_css.py
git commit -m "refactor(marca): dissolve a camada do fim em uma secao por peca"
```

---

## Task 4: Peça 1 — Botão

O botão reto de 3px **já está na tela**, mas por sobrescrita: o bloco `Botao reto (3px)` no fim do arquivo força `border-radius: var(--radius-ctl)` num seletor agrupado, enquanto a regra base do `.button` segue declarando `border-radius: 8px`. Duas verdades, 2.400 linhas de distância. Esta tarefa funde as três fontes (base, o que veio da camada, e a linha do bloco do fim) numa peça só, e instala o **teto de raios literais**, o mecanismo que as peças seguintes vão apertar.

O bloco do fim cobre num único seletor peças de quatro tarefas diferentes:

```css
.button, .link-button, input, select, textarea, .search, .filter-bar select {
  border-radius: var(--radius-ctl);
}
.nav-link { border-radius: var(--radius-nav); }
.panel, .metric-grid > .panel { border-radius: var(--radius-srf); }
```

**Retire desse bloco apenas `.button` e `.link-button`**, que são seus. `input`, `select`,
`textarea`, `.search` e `.filter-bar select` ficam para a Tarefa 5; `.nav-link` para a Tarefa 10;
`.panel` para a Tarefa 7. O bloco só desaparece quando a última dessas tarefas levar a sua parte —
quem levar a última linha apaga o comentário `/* --- Botao reto (3px) --- */` junto.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: `portal-gestao/app/static/css/app.css` (`.button` em ~519-560, `.link-button`, `.action-links`, `.action-stack`, mais o que a Tarefa 3 pôs na seção Botao)
- Modify: `revy-trafego/app/static/css/app.css` (mesmas peças)
- Modify: `portal-gestao/app/templates/base.html`, `revy-trafego/app/templates/base.html` (`?v=v2`)

**Interfaces:**
- Consumes: `css_audit.raios_literais`.
- Produces: `test_app_css.TETO_RAIOS: dict[str, int]` — quantos `border-radius` literais cada arquivo ainda pode ter. **Só desce.** Cada tarefa de peça baixa o número; a Tarefa 14 o zera.

- [ ] **Step 1: Medir o ponto de partida**

Run:
```bash
portal-gestao/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'shared/brand'); from css_audit import PAINEIS, caminho, raios_literais; [print(r, len(raios_literais(caminho(r)))) for r in PAINEIS]"
```
Medido em 08/08 com esta mesma função: **53 na Loja e 49 no Control**. (São 66 e 63
declarações de `border-radius` no total; a função já desconta as 3 tokenizadas, os `50%`,
os `inherit` e os `0` de cada arquivo.) Se a ferramenta imprimir outra coisa, use o que ela
imprimir — alguém mexeu no arquivo depois.

Note que `var(--radius)` **não** entra nesta conta: é variável, não literal. Os 11 usos da
Loja e os 10 do Control são cobertos pela guarda de apelidos da Tarefa 6, não por esta.

- [ ] **Step 2: Escrever a guarda que falha**

Acrescentar a `shared/brand/tests/test_app_css.py`, com os números medidos **menos** os que esta tarefa vai eliminar:

```python
from css_audit import raios_literais

# Teto de border-radius literais por arquivo. So desce: cada tarefa de peca
# tokeniza os raios da peca dela e baixa o numero aqui. A Tarefa 14 zera.
# O sistema tem tres raios (3/8/12); qualquer quarto valor e um sistema
# paralelo nascendo.
TETO_RAIOS = {
    "portal-gestao/app/static/css/app.css": 47,
    "revy-trafego/app/static/css/app.css": 43,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_teto_de_raios_literais(rel):
    achados = raios_literais(caminho(rel))
    assert len(achados) <= TETO_RAIOS[rel], (
        f"{rel}: {len(achados)} raios literais, teto {TETO_RAIOS[rel]}. "
        f"Primeiros: {achados[:8]}"
    )
```

Ajuste os dois valores para `medido - 6` (as seis regras de botão listadas no passo 4). Se a contagem real der outro número de regras de botão, use o que ela der — o teto tem de refletir o trabalho feito, nunca uma estimativa.

- [ ] **Step 3: Rodar e ver falhar**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py::test_teto_de_raios_literais -q`
Expected: FAIL nos dois painéis, com a contagem atual acima do teto.

- [ ] **Step 4: Reescrever a peça Botão nos dois arquivos**

Funda a regra base com o que a Tarefa 3 moveu para a seção Botao, e deixe a peça inteira só na seção. A base de hoje é:

```css
.button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s ease, border-color .15s ease, opacity .15s ease;
}
```

Passa a ser, na seção Botao:

```css
/* Botao reto: raio 3px, borda de 1px, caixa-baixa. Decisao de 08/08 — o botao
   e a mesma peca no site, na vitrine e no painel. */
.button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-ctl);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s ease, border-color .15s ease, opacity .15s ease;
}
.button:hover { opacity: .92; }

/* Sem variante o botao caia no estilo nativo do navegador. O padrao e o neutro. */
.button:not(.primary):not(.secondary):not(.ghost):not(.danger) {
  border-color: var(--line-strong);
  background: var(--surface);
  color: var(--ink);
}
.button:not(.primary):not(.secondary):not(.ghost):not(.danger):hover {
  background: var(--surface-soft);
}

.button.primary { background: var(--brand); color: var(--brand-ink); border-color: var(--brand); }
.button.primary:hover { background: var(--brand-strong); border-color: var(--brand-strong); opacity: 1; }

/* Vermelho tintado, nunca preenchimento solido: --danger no escuro e #f97066,
   e texto branco sobre ele da 2,76:1. O tintado tambem e o padrao dos outros
   cinco lugares que sinalizam erro (.alert.error, .sim-step.fail, .integ-pill.err). */
.button.danger {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--line));
  background: color-mix(in srgb, var(--danger) 8%, var(--paper));
  color: var(--danger);
}
```

Duas mudanças além do raio, ambas dentro da decisão de marca:

- a borda do botão neutro sobe de `--line` para `--line-strong` — com raio 3px e sem sombra, `--line` some no papel;
- `.button.danger` passa a usar `--danger` no lugar de `--red`. **É só troca de nome**: os dois
  tokens têm valor idêntico nos dois temas (`#b42318` / `#f97066`), então a fórmula `color-mix`
  fica exatamente como está. Trocar o tintado por preenchimento sólido seria redesenho de peça e
  reprova no contraste — decisão do dono em 08/08.

Mantenha `.secondary` e `.ghost` como estão, só migrando raio e eventuais `--red`/`--green`.
Aplique o mesmo a `.link-button`, e tokenize os raios de `.action-links` e `.action-stack` se houver.

Repita, regra por regra, no `app.css` do Control. Se lá a `.button` divergir da Loja em alguma declaração que não seja raio, borda ou cor, **preserve a divergência** — unificar componente está fora do escopo.

- [ ] **Step 5: Subir o cache-buster para `?v=v2`** nos dois `base.html`.

- [ ] **Step 6: Rodar as guardas e as suítes**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

Run: as duas suítes de produto.
Expected: PASS (com a falha pré-existente conhecida no Control)

- [ ] **Step 7: Conferência visual**

Nos dois temas: Loja → Ajustes (botões neutros e primários lado a lado), Estoque → lista (botão em linha de tabela), qualquer modal de confirmação (botão `danger`). Control → Lojas → detalhe. O botão fica visivelmente mais duro; é o esperado.

- [ ] **Step 8: Commit**

```bash
git add shared/brand/tests/test_app_css.py portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css portal-gestao/app/templates/base.html revy-trafego/app/templates/base.html
git commit -m "feat(marca): botao reto de 3px em toda tela"
```

---

## Task 5: Peça 2 — Campo e formulário

**Files:**
- Modify: `shared/brand/tests/test_app_css.py` (baixa `TETO_RAIOS`)
- Modify: os dois `app.css` (regra `input:not([type="checkbox"]):not([type="radio"]), select, textarea` em ~1149; `fieldset`; `.form-layout`, `.form-grid`, `.stack-form`, `.option-group`, `.filter-bar`, `.slug-field`)
- Modify: os dois `base.html` (`?v=v3`)

**Interfaces:**
- Consumes: `TETO_RAIOS` da Tarefa 4.
- Produces: nada novo.

- [ ] **Step 1: Contar os raios da peça**

Run:
```bash
rg -n "border-radius" portal-gestao/app/static/css/app.css | rg -i "input|select|textarea|field|form|filter|option|slug"
```
Some quantos são; esse é o quanto o teto desce.

- [ ] **Step 2: Baixar `TETO_RAIOS` no teste e vê-lo falhar**

Edite os dois números em `TETO_RAIOS` e rode:

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py::test_teto_de_raios_literais -q`
Expected: FAIL nos dois painéis.

- [ ] **Step 3: Reescrever a peça nos dois arquivos**

Mover a regra de campo para a seção `Campo e formulario` e aplicar:

```css
/* Campo reto, mesma familia do botao. A borda e --line-strong porque com raio
   de 3px e sem sombra a borda e o unico limite visivel do campo. */
input:not([type="checkbox"]):not([type="radio"]),
select,
textarea {
  width: 100%;
  min-height: 40px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-ctl);
  background: var(--surface);
  color: var(--ink);
}
```

O comentário existente sobre `checkbox`/`radio` (por que o `width: 100%` não pode valer para eles) **é conhecimento de armadilha e tem de sobreviver** à movimentação.

Junte na mesma seção o `:focus-visible { outline-color: var(--brand); }` que a Tarefa 3 moveu para cá, e acrescente o estado de foco do campo:

```css
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 1px;
  border-color: var(--brand);
}
```

Tokenize os raios de `.filter-bar`, `.option-group`, `.slug-field` e `fieldset` para `var(--radius-ctl)` quando forem controle, ou `var(--radius-srf)` quando forem caixa que agrupa (o `fieldset` de "Módulos da Loja" é caixa).

- [ ] **Step 4: Subir o cache-buster para `?v=v3`.**

- [ ] **Step 5: Rodar as guardas e as suítes.** Expected: PASS.

- [ ] **Step 6: Conferência visual**

Nos dois temas: Loja → Ajustes → Grupo do estoque (campos de texto, select, checkbox), Estoque → filtro, Simulação manual (formulário longo). Control → Lojas → nova loja (o `slug-field`). Confira em especial que a caixinha de checkbox **não** esticou — é a armadilha que o comentário registra.

- [ ] **Step 7: Commit**

```bash
git add shared/brand/tests/test_app_css.py portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css portal-gestao/app/templates/base.html revy-trafego/app/templates/base.html
git commit -m "feat(marca): campo reto e foco na cor da marca em toda tela"
```

---

## Task 6: Peça 3 — Estado

A maior e mais arriscada: 71 regras de `.status` na Loja, 64 no Control. Hoje o estado pinta por `--green`/`--amber`/`--red`, os genéricos, e a camada do fim transformou o chip numa pílula com bolinha — parente do "chip sólido" que foi **testado e rejeitado** em 08/08. Esta tarefa entrega a forma decidida (Ponto) e troca o vocabulário pela família `--st-*`.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: os dois `app.css` (`.status` e variantes em ~841-885 da Loja; `.status-pill`, `.status-chip`, `.canal-badge`, `.integ-pill`; o que a Tarefa 3 moveu para a seção Estado)
- Modify: os dois `base.html` (`?v=v4`)

**Interfaces:**
- Consumes: `css_audit.usos_de_var`, `TETO_RAIOS`.
- Produces: `test_app_css.TETO_APELIDOS: dict[str, int]` — quantos usos dos apelidos genéricos (`--green`, `--amber`, `--red`, `--online`) cada arquivo ainda pode ter. **Só desce.** A Tarefa 14 zera e remove os apelidos do canônico.

### Mapa de estado → token

**O mapa já existe no produto.** O bloco `Estado em ponto (2026-08-08)` no fim do arquivo já
aplica a forma Ponto e já distribui os estados pela família `--st-*` — inclusive estados vindos
do enum real (`confirmada`, `concluida`, `registrada`, `recebida`, `parcial`,
`aguardando_intervencao`, `pausada`, `processando`, `cancelada`, `falhou`) que o spec não listava.

Esse mapa é a **linha de base**, não um rascunho a substituir: ele foi conferido contra o enum e
está no ar. Esta tarefa faz três coisas com ele — traz para a seção `Estado`, aplica **uma** troca
de significado, e renomeia dois grupos para o vocabulário semântico.

**A tabela final:**

| Classes | Token | Ponto? |
|---|---|---|
| `novo`, `qualificado`, `convertido`, `confirmada`, `concluida` | `--st-won` | sim |
| `ativa`, `ativo`, `pronta`, `conectado` | `--ok` | sim |
| `reservado`, `aguardando_simulacao`, `aguardando_cliente`, `em_configuracao`, `rascunho`, `pendente`, `registrada`, `recebida`, `parcial`, `aguardando_intervencao`, `pausada` | `--st-wait` | sim |
| `desconectado`, `warn` | `--warn` | sim |
| `em_atendimento`, `processando` | `--st-live` | sim |
| `negociacao` | `--st-prop` | sim |
| `disponivel` | `--ink-muted` (neutro) | **não** |
| `vendido`, `perdido`, `indisponivel`, `suspensa`, `encerrada`, `inativo`, `cancelada`, `falhou` | `--ink-muted`, `--st-lost` no `--sc` | **não** — terminal |

**A única troca de significado** — aprovada pelo dono em 08/08: `disponivel` sai de `--st-won` e
vira neutro sem ponto. Hoje ele sai da mesma variável que `convertido`, ou seja, `Disponível` e
`Convertido` são a mesma cor na tela. É o estado de repouso da maioria dos veículos e não exige
ação; o destaque vai para quem espera.

**As duas renomeações são de graça e não mudam pixel:** `ativa`/`ativo`/`pronta`/`conectado`
saem de `--st-won` para `--ok`, e `desconectado`/`warn` saem de `--st-wait` para `--warn`. Os
valores são idênticos nos dois temas (`--st-won` e `--ok` são ambos `#0d7a4f`/`#3ecf8e`;
`--st-wait` e `--warn` são ambos `#8a6d1d`/`#d9b04a`). O ganho é de leitura: passa a ser possível
saber, olhando o CSS, se aquele verde significa "registro ganho" ou "operação deu certo" — que é
a regra §3.3 do spec. Confirme os valores em `shared/brand/revy-tokens.css` antes de trocar; se
divergirem, **pare e reporte** em vez de mudar a cor de um estado.

**Nada mais no mapa muda.** Em particular `qualificado` continua `--st-won` e `reservado`
continua `--st-wait`, mesmo que pareçam candidatos a `--st-live`: mexer neles seria redesenho, e
o mapa vigente veio do enum real. `--st-lost` também passa a ter uso, no `--sc` dos terminais,
saindo de zero usos.

- [ ] **Step 1: Escrever as guardas que falham**

Acrescentar a `shared/brand/tests/test_app_css.py`:

```python
# Apelidos genericos herdados do sistema anterior. Cada tarefa migra os seus
# para o nome semantico e baixa o teto; a Tarefa 14 zera e os remove do
# canonico. Enquanto .status pintar por --green, "Proposta" e "Ganho" saem da
# mesma variavel e a regra "o acento nunca e status" nao tem como valer.
APELIDOS = ("--green", "--amber", "--red", "--online")

TETO_APELIDOS = {
    "portal-gestao/app/static/css/app.css": 45,
    "revy-trafego/app/static/css/app.css": 50,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_teto_de_apelidos_genericos(rel):
    total = sum(usos_de_var(caminho(rel), a) for a in APELIDOS)
    assert total <= TETO_APELIDOS[rel], (
        f"{rel}: {total} usos de apelido generico, teto {TETO_APELIDOS[rel]}"
    )


TERMINAIS = ("convertido", "vendido", "perdido", "indisponivel", "encerrada", "inativo")


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("terminal", TERMINAIS)
def test_estado_terminal_nao_recebe_ponto(rel, terminal):
    """Ganho e marca de conferido; Perdido e texto apagado. O orcamento de
    destaque vai para quem exige acao — um cliente esperando ha tres horas
    importa mais que uma venda fechada semana passada."""
    css = caminho(rel).read_text(encoding="utf-8")
    assert f".status.{terminal}::before" in css, (
        f"{rel}: o estado terminal '{terminal}' nao suprime o ponto"
    )
```

Se um dos seis estados terminais não existir no CSS de um dos produtos (o Control não
tem `vendido`, por exemplo), remova-o de `TERMINAIS` para aquele arquivo em vez de
inventar a classe — a guarda existe para proteger o que existe.

Meça o total atual antes de escolher os números do teto:

```bash
portal-gestao/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'shared/brand'); from css_audit import PAINEIS, caminho, usos_de_var; [print(r, sum(usos_de_var(caminho(r), a) for a in ('--green','--amber','--red','--online'))) for r in PAINEIS]"
```

Medido em 08/08: **62 na Loja** (22 `--green` + 21 `--amber` + 16 `--red` + 3 `--online`) e
**78 no Control** (29 + 23 + 26 + 0). Desses, a peça Estado responde por aproximadamente 17
na Loja e 28 no Control — daí os tetos 45 e 50 acima. São estimativas de partida: depois de
reescrever a peça, rode a medição de novo e **baixe o teto até o valor real**. Um teto folgado
não protege nada.

- [ ] **Step 2: Rodar e ver falhar**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL em `test_teto_de_apelidos_genericos` e em `test_estado_terminal_nao_recebe_ponto`.

- [ ] **Step 3: Reescrever a peça Estado nos dois arquivos**

Toda a peça vai para a seção `Estado`. A base passa a ser Ponto — sem fundo, sem pílula:

```css
/* Estado = ponto na cor do estado + palavra. Cor nunca comunica sozinha, e o
   chip solido foi testado e rejeitado em 08/08: numa fila de 40 linhas vira
   mosaico. O --sc e a cor deste estado, definida pela variante logo abaixo. */
.status {
  --sc: var(--ink-soft);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: max-content;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 500;
}
.status::before {
  content: "";
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--sc);
}

/* Terminal nao disputa atencao: Ganho e marca de conferido, Perdido e texto
   apagado. Nenhum dos dois ganha ponto colorido. */
.status.is-terminal::before { display: none; }
.status.convertido,
.status.vendido { color: var(--st-won); font-weight: 600; }
.status.perdido,
.status.indisponivel,
.status.encerrada,
.status.inativo,
.status.suspensa { color: var(--st-lost); }

/* Os grupos de estado saem da tabela acima, nao deste exemplo. A forma e
   sempre esta: */
.status.<classe>, .status.<classe> { --sc: var(<token da tabela>); }

/* Repouso: a maioria dos veiculos esta disponivel. Sem destaque. */
.status.disponivel { --sc: var(--ink-muted); }
```

**A tabela acima é a autoridade dos grupos, não este bloco de exemplo.** Ele mostra só a
*forma* da regra. Se as duas divergirem, a tabela vence — e reporte a divergência, porque
significa que este documento voltou a ter duas verdades.

As classes terminais precisam de `is-terminal` no template. Em vez de editar cada `<span>`, acrescente as terminais também como seletor do `::before`:

```css
.status.convertido::before,
.status.vendido::before,
.status.perdido::before,
.status.indisponivel::before,
.status.encerrada::before,
.status.inativo::before,
.status.suspensa::before,
.status.disponivel::before { display: none; }
```

e mantenha `.status.is-terminal::before { display: none; }` para quem vier depois. Assim **nenhum template muda**.

Aplique o mesmo tratamento a `.status-pill`, `.status-chip`, `.canal-badge` e `.integ-pill`: quem indica **estado** vira Ponto; quem é **rótulo** (nome do canal, por exemplo) vira pastilha reta de `var(--radius-ctl)` com `--surface-soft` de fundo, sem cor de estado.

No Control, a peça é maior (`.status-pill` tem 17 regras) e a seção `revy-results` já usa `--sc` apontando para `--st-*` — esse trecho já está certo e serve de referência. Só troque os `var(--red)` que aparecerem lá por `var(--danger)`.

- [ ] **Step 4: Subir o cache-buster para `?v=v4`.**

- [ ] **Step 5: Rodar as guardas e as suítes.** Expected: PASS.

- [ ] **Step 6: Conferência visual — a mais importante do plano**

Nos dois temas, com atenção a cada estado que existir na base:

- Loja → Atendimento (fila com leads em vários estados), Vendas → Visão (vendas confirmadas e perdidas), Estoque → lista (disponível, reservado, vendido), Ajustes → Números de WhatsApp (conectado/desconectado).
- Control → Lojas → lista (rascunho, em configuração, pronta, ativa, suspensa, encerrada), Loja → detalhe, Aquisição/ROI.

Confira os três invariantes: **(a)** todo estado tem ponto *ou* é terminal, e sempre tem palavra; **(b)** `Proposta` (verde acento) e `Ganho` (verde de sucesso) são distinguíveis; **(c)** nenhuma fila virou mosaico colorido.

- [ ] **Step 7: Commit**

```bash
git add shared/brand/tests/test_app_css.py portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css portal-gestao/app/templates/base.html revy-trafego/app/templates/base.html
git commit -m "feat(marca): estado vira ponto e adota a familia --st-* em toda tela"
```

---

## Task 7: Peça 4 — Painel e card

**Files:**
- Modify: `shared/brand/tests/test_app_css.py` (baixa `TETO_RAIOS` e `TETO_APELIDOS`)
- Modify: os dois `app.css` (`.panel` ~574, `.panel-heading`, `.panel-body`, `.panel-vitrine`, `.operations-card`, `.integration-card`, `.action-panel`, `.funil-summary-card`, `.empty`, mais o cartão-resumo e o painel de integrações que a Tarefa 3 moveu para cá)
- Modify: os dois `base.html` (`?v=v5`)

- [ ] **Step 1: Baixar os dois tetos e vê-los falhar**

Conte os raios e apelidos dessas classes com `rg -n` antes de escolher os números.

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL nos tetos.

- [ ] **Step 2: Reescrever a peça nos dois arquivos**

`.panel` já usa tokens; só o raio migra:

```css
/* Superficie sempre contrasta com o papel: e o que da profundidade,
   principalmente no escuro. Achatar tudo no mesmo tom mata a peca. */
.panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-srf);
  background: var(--surface);
  box-shadow: var(--shadow);
}
```

Aplique `var(--radius-srf)` a todo card e painel da lista, e confirme que cada um tem `background: var(--surface)` explícito — nenhum pode herdar `--paper`, ou perde a profundidade no escuro.

`.empty` fica na seção `Alerta, faixa e vazio` (Tarefa 12), não aqui; se a Tarefa 3 a tiver colocado em Painel e card, mova agora.

- [ ] **Step 3: Subir o cache-buster para `?v=v5`.**
- [ ] **Step 4: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 5: Conferência visual** — nos dois temas: Loja → Vendas → Visão (grade de painéis), Ajustes → Integrações (cards de integração). Control → Visão geral. No escuro, cada card tem de se destacar do fundo.
- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(marca): painel e card no raio 12px com superficie propria"
```

---

## Task 8: Peça 5 — Tabela e lista

Além do raio e da cor, esta peça estreia `--font-data` (mono) em placa, telefone e ID — hoje com **zero usos**.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: os dois `app.css` (`.vehicle-row` ~782, `.vehicle-cell`, `.thread`, `.integ-row`, `.integ-subitem`, `.overview-list`, `.rowlink`, `.readiness-item`, `table`/`th`/`td` se houver)
- Modify: os dois `base.html` (`?v=v6`)

- [ ] **Step 1: Escrever a guarda que falha**

```python
@pytest.mark.parametrize("rel", PAINEIS)
def test_dado_tecnico_usa_a_fonte_mono(rel):
    """Placa, telefone e ID sao para conferir caractere a caractere; em fonte
    proporcional o 0/O e o 1/l se confundem."""
    assert usos_de_var(caminho(rel), "--font-data") > 0, (
        f"{rel} nao usa --font-data em lugar nenhum"
    )
```

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py::test_dado_tecnico_usa_a_fonte_mono -q`
Expected: FAIL nos dois painéis.

- [ ] **Step 2: Baixar `TETO_RAIOS` e `TETO_APELIDOS`** pelo que a peça consome.

- [ ] **Step 3: Reescrever a peça nos dois arquivos**

Densidade média (~34px de linha), separador `--line`, hover `--surface-soft`:

```css
.vehicle-row {
  min-width: 0;
  display: grid;
  grid-template-columns: 54px minmax(180px, 1fr) auto 150px;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
  transition: background .15s ease;
}
.vehicle-row:hover { background: var(--surface-soft); }
.vehicle-row:last-child { border-bottom: 0; }

/* Placa, telefone e ID: mono e tabular, para conferir caractere a caractere. */
.dado-tecnico,
.vehicle-cell .placa {
  font-family: var(--font-data);
  font-variant-numeric: tabular-nums;
  letter-spacing: .01em;
}
```

O `padding` sai de `14px 16px` para a escala (`--space-2` = 8px vertical), que é o que entrega a linha de ~34px com `min-height` implícito do conteúdo. **Este é o único ajuste de espaçamento autorizado nesta rodada**, porque a densidade de tabela é decisão de marca registrada no spec de 08/08 ("Densidade de tabela: Média — linha de ~34px").

Localize onde placa e telefone são renderizados (`rg -n "placa" portal-gestao/app/templates`) e aplique a classe existente, ou acrescente `.dado-tecnico` ao `<span>` correspondente. Isto e a Peça 6 são as duas únicas tarefas que editam template.

- [ ] **Step 4: Subir o cache-buster para `?v=v6`.**
- [ ] **Step 5: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 6: Conferência visual** — Loja → Estoque → lista (linha mais compacta, placa em mono), Atendimento → fila. Control → Lojas → lista. Confira que a linha não ficou apertada demais para clicar no toque.
- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(marca): tabela na densidade media e dado tecnico em mono"
```

---

## Task 9: Peça 6 — Número e gráfico

Aqui sai o `<small>` de explicação sob o KPI — a segunda exceção autorizada ao "não redesenhar". A regra é "um rótulo por número": era a linha de apoio que fazia três camadas de texto entregarem um número só.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: os dois `app.css` (`.metric` ~615, `.metric-grid`, `.revy-results*` (36 regras em cada), `.funil-*`, `.split-legend`, `.dashboard-*`, `.day-col`, `.roas-bar`, mais a sparkline que a Tarefa 3 moveu)
- Modify: `portal-gestao/app/templates/loja/vendas_visao.html` e os demais que a busca do passo 3 apontar
- Modify: os dois `base.html` (`?v=v7`)

- [ ] **Step 1: Medir quantos `tabular-nums` já existem**

Run: `rg -c "tabular-nums" portal-gestao/app/static/css/app.css revy-trafego/app/static/css/app.css`

Anote os dois números; chame-os de `atual`. Se um arquivo não tiver nenhum, `rg -c` omite a linha e `atual` é 0.

- [ ] **Step 2: Escrever a guarda que falha**

Com `MINIMO_TABULAR` = `atual + 2` para cada arquivo, garantindo que falhe agora e passe depois:

```python
# Numero que muda a cada refresh nao pode dancar de largura: sem tabular-nums,
# a coluna de valores treme quando o digito 1 entra ou sai.
MINIMO_TABULAR = {
    "portal-gestao/app/static/css/app.css": 3,
    "revy-trafego/app/static/css/app.css": 3,
}


@pytest.mark.parametrize("rel", PAINEIS)
def test_numero_e_tabular(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    assert css.count("tabular-nums") >= MINIMO_TABULAR[rel], (
        f"{rel}: {css.count('tabular-nums')} usos, minimo {MINIMO_TABULAR[rel]}"
    )
```

Troque os dois `3` pelo `atual + 2` que você mediu.

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py::test_numero_e_tabular -q`
Expected: FAIL nos dois painéis.

- [ ] **Step 3: Isentar as duas barras finas do teto de raios**

Antes de baixar o teto, resolva um conflito real: `.roas-bar` (7px de altura) e
`.revy-onboarding__progress i` (4px) usam `border-radius: 99px` para arredondar a ponta.
Isso é geometria de barra, não raio de caixa — `50%` numa barra fina vira elipse, e
`--radius-ctl` (3px) numa barra de 4px não arredonda nada. As duas são exceção nominal,
para que o teto possa chegar a zero na Tarefa 13.

Acrescente ao teste:

```python
# Barra fina: a ponta arredondada e geometria da barra, nao raio de caixa.
# Duas excecoes nominais e documentadas — nao e categoria aberta.
EXCECOES_DE_RAIO = ("roas-bar", "revy-onboarding__progress")


def _raios_relevantes(rel):
    """Raios literais, menos os das barras finas isentas."""
    linhas = caminho(rel).read_text(encoding="utf-8").split("\n")
    return [
        (n, v) for n, v in raios_literais(caminho(rel))
        if not any(e in "\n".join(linhas[max(0, n - 4):n]) for e in EXCECOES_DE_RAIO)
    ]
```

e troque, em `test_teto_de_raios_literais`, `raios_literais(caminho(rel))` por `_raios_relevantes(rel)`.

- [ ] **Step 4: Baixar `TETO_RAIOS` e `TETO_APELIDOS`.**

- [ ] **Step 5: Achar e remover a linha de apoio do KPI**

Run: `rg -n "metric" portal-gestao/app/templates revy-trafego/app/templates -l`
Run: `rg -n "<small" portal-gestao/app/templates/loja revy-trafego/app/templates`

Para cada KPI, o padrão é rótulo (`<span>`) + valor (`<strong>`) + explicação (`<small>`). **Só o `<small>` sai**, e só quando ele explica o número — se for unidade, período ou variação, fica. Na dúvida, mantenha e anote no commit.

- [ ] **Step 6: Reescrever a peça nos dois arquivos**

```css
/* Um rotulo por numero: rotulo curto + valor. A linha de explicacao saiu —
   era ela que fazia tres camadas de texto entregarem um numero so. */
.metric strong,
.funil-stage-value,
.revy-results__value {
  font-variant-numeric: tabular-nums;
  letter-spacing: -.02em;
}
```

Série de gráfico e barra passam a usar `var(--green-500)` — o passo da escala reservado a
gráfico — e o pico continua em `var(--brand)`. As duas barras finas isentadas no Step 3
mantêm `border-radius: 99px` como estão.

- [ ] **Step 7: Subir o cache-buster para `?v=v7`.**
- [ ] **Step 8: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 9: Conferência visual** — Loja → Vendas → Visão (o KPI perde a terceira linha), funil. Control → Visão geral, Aquisição/ROI. Confira que nenhum número ficou sem rótulo depois da remoção do `<small>`.
- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "feat(marca): um rotulo por numero, valor tabular e serie no verde 500"
```

---

## Task 10: Peça 7 — Navegação e shell

Boa parte já está certa desde 08/08 — esta tarefa absorve o que a Tarefa 3 moveu para cá e tokeniza o que sobrou. **A aparência não deve mudar.**

**Files:**
- Modify: `shared/brand/tests/test_app_css.py` (baixa `TETO_RAIOS`)
- Modify: os dois `app.css` (`.nav-link` ~198, `.brand-mark`, `.sidebar`, `.topbar`, `.control-tab`, `.page-heading`, `.section-title`, `.eyebrow`, `.environment`, `.avatar`)
- Modify: os dois `base.html` (`?v=v8`)

- [ ] **Step 1: Escrever a guarda que falha**

```python
@pytest.mark.parametrize("rel", PAINEIS)
def test_item_de_menu_usa_o_raio_de_navegacao(rel):
    css = caminho(rel).read_text(encoding="utf-8")
    assert "border-radius: var(--radius-nav)" in css, (
        f"{rel} nao usa --radius-nav em item de menu"
    )
```

Run: o pytest do arquivo. Expected: FAIL nos dois painéis (hoje `.nav-link` é `border-radius: 8px` literal).

- [ ] **Step 2: Baixar `TETO_RAIOS`.**

- [ ] **Step 3: Reescrever a peça nos dois arquivos**

Fundir `.nav-link` (linha ~198) com `.nav-link.active` e as regras de ícone que a Tarefa 3 moveu, tudo na seção `Navegacao e shell`. Trocar `border-radius: 8px` por `var(--radius-nav)`. **Nenhuma outra declaração muda.**

`.brand-mark` e os dois `[data-theme="dark"] .brand-mark …` vêm junto, sem alteração: a marca é preta nos dois temas, com o fio de 1px no escuro para não sumir na sidebar.

`.avatar` mantém `border-radius: 50%` — é círculo, não raio.

- [ ] **Step 4: Subir o cache-buster para `?v=v8`.**
- [ ] **Step 5: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 6: Conferência visual** — nos dois temas, o menu lateral dos dois produtos e as abas do Control. **Nada pode ter mudado.** Se mudou, uma regra foi perdida na fusão.
- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor(marca): navegacao e shell numa secao so, com o raio de menu tokenizado"
```

---

## Task 11: Peça 8 — Alerta, faixa e vazio

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: os dois `app.css` (`.alert` ~930, `.revy-alert-strip`, `.sim-status-banner`, `.handoff-bar`, `.empty`, `.revy-onboarding`, mais o `.alert::before` e o `.empty` que a Tarefa 3 moveu)
- Modify: os dois `base.html` (`?v=v9`)

- [ ] **Step 1: Escrever a guarda que falha**

```python
@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("token", ["--ok", "--warn", "--danger", "--whatsapp"])
def test_resultado_de_operacao_usa_token_semantico(rel, token):
    """--ok/--warn/--danger dizem o que aconteceu; --green/--amber/--red so
    diziam a cor. Sem o nome semantico, ninguem sabe se o verde e 'conectou'
    ou 'e da marca'."""
    assert usos_de_var(caminho(rel), token) > 0, f"{rel} nao usa var({token})"
```

Run: o pytest do arquivo. Expected: FAIL nos oito parâmetros (os quatro tokens têm zero usos hoje).

- [ ] **Step 2: Baixar `TETO_APELIDOS` e `TETO_RAIOS`.**

- [ ] **Step 3: Reescrever a peça nos dois arquivos**

```css
/* O padding fica exatamente como estava (12px 14px, mais os 42px de recuo do
   icone): espacamento esta fora desta rodada. So raio e cor mudam. */
.alert {
  position: relative;
  margin-bottom: 16px;
  padding: 12px 14px 12px 42px;
  border: 1px solid;
  border-radius: var(--radius-srf);
  font-size: 13px;
}
.alert.warning {
  border-color: color-mix(in srgb, var(--warn) 30%, var(--line));
  background: color-mix(in srgb, var(--warn) 10%, var(--paper));
  color: var(--warn);
}
.alert.error {
  border-color: color-mix(in srgb, var(--danger) 30%, var(--line));
  background: color-mix(in srgb, var(--danger) 10%, var(--paper));
  color: var(--danger);
}
.alert.success {
  border-color: color-mix(in srgb, var(--ok) 30%, var(--line));
  background: color-mix(in srgb, var(--ok) 10%, var(--paper));
  color: var(--ok);
}
```

Preserve o `.alert::before` com a máscara de ícone que a Tarefa 3 moveu, **inclusive o comentário** sobre o posicionamento absoluto (ele registra por que o ícone não pode ser irmão flex de conteúdo multi-bloco).

Migre `var(--online)` para `var(--whatsapp)` onde aparecer (selo "Conectado", botão Enviar) — são 3 usos na Loja, nenhum no Control.

- [ ] **Step 4: Subir o cache-buster para `?v=v9`.**
- [ ] **Step 5: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 6: Conferência visual** — Loja → Ajustes → Integrações (alerta de aviso e de erro), Atendimento com bot pausado (`handoff-bar`), qualquer lista vazia. Control → onboarding de loja nova.
- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(marca): alerta e faixa nos tokens semanticos de operacao"
```

---

## Task 12: Peça 9 — Autenticação

Cinco telas fora do shell: login, aceitar convite, esqueci a senha, redefinir senha, e o `base.html`. São as únicas com cor crua em template — e ela é **legítima**: aplica o tema antes do CSS carregar, evitando o flash branco. O que muda é que os valores passam a ser os canônicos e a frase de marca ganha Newsreader.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py`
- Modify: os dois `app.css` (`.login-*`, `.login-story`, `.login-theme-bar`, `.login-card`, `.login-layout`)
- Modify: `portal-gestao/app/templates/login.html`, `convite_aceitar.html`, `senha_esqueci.html`, `senha_redefinir.html`, `base.html`
- Modify: os dois `base.html` (`?v=v10`)

- [ ] **Step 1: Escrever a guarda que falha**

```python
import re

# Cor em template so se justifica no anti-flash: o <script> que aplica o tema
# antes de o CSS carregar, para a tela nao piscar branco. Sao cinco arquivos, e
# os valores tem de bater com o canonico — se divergirem, a tela pisca de uma
# cor para a outra.
TEMPLATES_COM_ANTI_FLASH = {
    "base.html",
    "login.html",
    "convite_aceitar.html",
    "senha_esqueci.html",
    "senha_redefinir.html",
}

HEX_DO_ANTI_FLASH = {"#f9f9f9", "#0a0a0a", "#ffffff", "#1b1b1b", "#f5f5f5", "#111111"}

TEMPLATES = ["portal-gestao/app/templates", "revy-trafego/app/templates"]


def _templates():
    for raiz in TEMPLATES:
        for p in sorted((RAIZ / raiz).rglob("*.html")):
            yield p.relative_to(RAIZ).as_posix(), p


@pytest.mark.parametrize("rel,path", list(_templates()), ids=lambda x: x if isinstance(x, str) else "")
def test_template_nao_carrega_cor_propria(rel, path):
    achados = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", path.read_text(encoding="utf-8"))}
    if not achados:
        return
    permitido = HEX_DO_ANTI_FLASH if path.name in TEMPLATES_COM_ANTI_FLASH else set()
    fora = sorted(achados - permitido)
    assert not fora, (
        f"{rel} tem cor propria: {fora}. Cor vem de token no app.css; "
        f"so os cinco templates de anti-flash podem citar hex, e so os canonicos."
    )
```

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -k template -q`
Expected: FAIL em dois arquivos — `simulacoes/registros.html` (`#111`) e `trafego/roi.html` (`#3ecf8e`). Nenhum dos dois é anti-flash: são `<style>` inline no corpo da página, e é isso que o Step 3 resolve.

- [ ] **Step 2: Baixar `TETO_RAIOS` e `TETO_APELIDOS`.**

- [ ] **Step 3: Migrar os dois `<style>` inline**

`portal-gestao/app/templates/simulacoes/registros.html` e `portal-gestao/app/templates/trafego/roi.html` têm CSS embutido. Mova as regras para a seção apropriada do `app.css` (Painel e card, ou Número e gráfico) e apague o `<style>`. Se alguma regra for específica de uma tela só, mantenha-a no `app.css` sob um seletor de página — não deixe CSS em template.

- [ ] **Step 4: Trazer o bloco `Login (2026-08-08)` para a seção**

A Newsreader **já está aplicada** — no `.login-story h1`, pelo bloco `Login (2026-08-08)` no fim
do arquivo da Loja. O painel da história **já é** sempre preto. Esta tarefa não introduz nada
disso: ela move o bloco inteiro para a seção `Autenticacao`, funde com o que já houver lá e com
as regras `.login-*` mais acima no arquivo, e apaga as origens. Confirme com `rg -n "login-"` que
a peça fica num lugar só — no Portal ela existe hoje em **três** regiões distintas.

Preserve intactos, junto das regras que explicam, os dois comentários de armadilha desse bloco: o
que registra por que o preto é literal (derivar de `var(--ink)` deixaria o painel branco no modo
escuro) e o que registra por que a media query de 900px é repetida (senão o login fica com 48px
de margem lateral em tela de 375px).

Esse bloco tem cinco cores cruas. Só uma muda:

| Cor | Destino |
|---|---|
| `#1b1b1b`, `#000000`, `#f7f7f7`, `#9a9a9a` | **ficam literais.** O painel é uma superfície de escuro fixo, não uma superfície temática: token de tema aqui inverteria a cor no modo escuro, que é justamente a armadilha registrada no comentário |
| `#7fbfa3` (descritor "GESTÃO DE REVENDA") | vira `var(--green-300)` — é exatamente esse passo da escala, e a escala existe para isto |

Confirme que a Newsreader está no `<link>` do Google Fonts do `login.html` (e só dele; o
`base.html` do painel não carrega Newsreader).

- [ ] **Step 5: Subir o cache-buster para `?v=v10`.**
- [ ] **Step 6: Rodar as guardas e as suítes.** Expected: PASS.
- [ ] **Step 7: Conferência visual** — as cinco telas, nos dois temas, e com o cache do navegador limpo (é onde o anti-flash aparece). Recarregue com o tema escuro ativo e confirme que não há flash branco.
- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat(marca): autenticacao com frase em Newsreader e anti-flash canonico"
```

---

## Task 13: Peças 10 e 11 — superfícies específicas de cada produto

O que sobrou depois de as oito peças compartilhadas passarem: `vitrine-card`, `vehicle-photo`, `composer`, `sim-step`, `funil-time-grid`, `roi-insights` na Loja; `google-step`, `danger-zone`, `next-steps`, `integration-stats`, `readiness-item` no Control.

**Files:**
- Modify: `shared/brand/tests/test_app_css.py` (zera `TETO_RAIOS` e `TETO_APELIDOS`)
- Modify: os dois `app.css`
- Modify: os dois `base.html` (`?v=v11`)

- [ ] **Step 1: Zerar os dois tetos e ver falhar**

```python
TETO_RAIOS = {
    "portal-gestao/app/static/css/app.css": 0,
    "revy-trafego/app/static/css/app.css": 0,
}
TETO_APELIDOS = {
    "portal-gestao/app/static/css/app.css": 0,
    "revy-trafego/app/static/css/app.css": 0,
}
```

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests/test_app_css.py -q`
Expected: FAIL, listando exatamente o que restou. Essa lista **é** a lista de trabalho desta tarefa.

- [ ] **Step 2: Percorrer a lista até zerar**

Para cada raio literal: `--radius-ctl` se for controle ou pastilha, `--radius-nav` se for item de menu, `--radius-srf` se for caixa ou foto. Para cada apelido: `--ok` / `--warn` / `--danger` / `--whatsapp` se for resultado de operação; a família `--st-*` se for estado de registro; `--brand` se for ênfase de estrutura.

`.vitrine-card` e `.vehicle-photo` seguem o padrão Vitrine já implantado no catálogo público em `a99d04f` — abra `catalogo-publico/app/static/css/catalog.css` e reaproveite as decisões de lá em vez de inventar.

- [ ] **Step 3: Subir o cache-buster para `?v=v11`.**
- [ ] **Step 4: Rodar as guardas e as suítes.** Expected: PASS, com os dois tetos em zero.
- [ ] **Step 5: Conferência visual** — todas as telas-testemunha dos dois produtos, nos dois temas, mais Loja → Estoque → detalhe de veículo (a vitrine) e Control → Loja → detalhe (`danger-zone`).
- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(marca): superficies especificas de Loja e Control no sistema novo"
```

---

## Task 14: Fecho — os apelidos saem do canônico e as guardas viram absolutas

**Files:**
- Modify: `shared/brand/revy-tokens.css` (remove `--green`, `--amber`, `--red`, `--online`, `--radius`)
- Modify: as quatro cópias, via `shared/brand/sync_tokens.py`
- Modify: `shared/brand/tests/test_app_css.py` (tetos viram asserções absolutas)
- Modify: `docs/handoff-contexto.md`
- Modify: `portal-gestao/README.md` e `revy-trafego/README.md` (uma linha de armadilha em cada)

- [ ] **Step 1: Verificar que ninguém mais usa os apelidos**

Run:
```bash
rg -n "var\(--green\)|var\(--amber\)|var\(--red\)|var\(--online\)|var\(--radius\)" portal-gestao revy-trafego catalogo-publico site --glob '!*.min.css'
```
Expected: nenhum resultado. Se houver, corrija antes de seguir — o catálogo e o site também consomem o canônico.

- [ ] **Step 2: Escrever a guarda que falha**

```python
APELIDOS_APOSENTADOS = ("--green", "--amber", "--red", "--online", "--radius")


def test_canonico_nao_carrega_mais_apelido_generico():
    """Eles existiam so para o app.css antigo continuar funcionando. Enquanto
    estiverem la, uma regra nova pode nascer usando --green sem que ninguem
    saiba se aquilo e sucesso, estado de registro ou verde de marca."""
    declarados = set(load_tokens(CANONICAL)["light"])
    sobrando = sorted(set(APELIDOS_APOSENTADOS) & declarados)
    assert not sobrando, f"o canonico ainda declara: {sobrando}"
```

Run: o pytest do arquivo. Expected: FAIL listando os cinco.

- [ ] **Step 3: Remover os cinco do canônico e sincronizar**

Editar `shared/brand/revy-tokens.css` e depois:

Run: `portal-gestao/.venv/Scripts/python.exe shared/brand/sync_tokens.py`
Expected: as quatro cópias atualizadas.

- [ ] **Step 4: Transformar os tetos em asserções absolutas**

Substituir `TETO_RAIOS` e `TETO_APELIDOS` por asserções diretas, para que o próximo leitor não pense que zero é um marco temporário:

```python
@pytest.mark.parametrize("rel", PAINEIS)
def test_nenhum_raio_fora_do_sistema(rel):
    """O sistema tem tres raios: 3px controle, 8px menu, 12px superficie.
    Um quarto valor e um sistema paralelo nascendo."""
    achados = _raios_relevantes(rel)
    assert not achados, f"{rel} tem raio fora do sistema: {achados}"


@pytest.mark.parametrize("rel", PAINEIS)
@pytest.mark.parametrize("apelido", APELIDOS_APOSENTADOS)
def test_apelido_generico_nao_volta(rel, apelido):
    assert usos_de_var(caminho(rel), apelido) == 0, f"{rel} voltou a usar {apelido}"
```

- [ ] **Step 5: Rodar tudo**

Run: `portal-gestao/.venv/Scripts/python.exe -m pytest shared/brand/tests -q`
Expected: PASS

Run: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS

Run: `cd revy-trafego; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (com a falha pré-existente conhecida do outbox de provisionamento)

- [ ] **Step 6: Reverificar site e catálogo**

Eles consomem o canônico e acabaram de perder cinco variáveis.

Run: `rg -n "1f6feb|5a95ff" catalogo-publico site` — Expected: nada.
Run: `rg -n "Inter" catalogo-publico/` — Expected: nada.
Run: `rg -n "data-theme" catalogo-publico/ site/` — Expected: nada.

Abra a vitrine pública e a landing e confirme que nada despintou.

- [ ] **Step 7: Conferência visual final**

Todas as telas-testemunha dos dois produtos, nos dois temas, mais a vitrine e o site no claro. Este é o momento de comparar com os mockups de 08/08.

- [ ] **Step 8: Registrar o estado**

Em `docs/handoff-contexto.md`, atualizar "Checkpoint de código" e "Validação conhecida" com o que foi feito, e remover da lista de pendências o que esta varredura fechou. **Não** remover a pendência de espaçamento ("gaps") — ela continua em fila separada, por decisão.

Em `portal-gestao/README.md` e `revy-trafego/README.md`, acrescentar uma linha em "Armadilhas":

> O `app.css` **não** pode reabrir `:root` para declarar token de marca: ele carrega depois do `revy-tokens.css` e a redeclaração anula a fonte única. `shared/brand/tests/test_app_css.py` falha se acontecer.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(marca): aposenta os apelidos genericos e fecha as guardas da varredura"
```

---

## Verificação final do plano

Depois da Tarefa 14, tudo abaixo tem de valer:

- [ ] `rg -n "Camada Revy 2026"` — nada
- [ ] `rg -n "var\(--accent"` em `portal-gestao` e `revy-trafego` — nada
- [ ] `rg -n "1f6feb|5a95ff"` no repositório, fora de `docs/historico` — nada
- [ ] `rg -n "1f4d3a|7fbfa3" portal-gestao revy-trafego` — nada: o acento só pode chegar por token, ou um dos dois passos acaba sob o fundo errado. As cores literais do painel de login (`#1b1b1b`, `#000000`, `#f7f7f7`, `#9a9a9a`) são a exceção documentada — superfície de escuro fixo, não temática
- [ ] `rg -n "/\* --- Botao reto" portal-gestao revy-trafego` — nada: o bloco ad-hoc do fim foi absorvido pelas Tarefas 4, 5, 7 e 10
- [ ] `rg -n "Estado em ponto|Login \(2026-08-08\)" portal-gestao revy-trafego` — nada: absorvidos pelas Tarefas 6 e 12
- [ ] Nenhum template com cor própria fora dos cinco de anti-flash
- [ ] Nenhum `border-radius` fora de `var(--radius-*)`, `50%`, `inherit`, `0` e as duas barras finas nominais
- [ ] `--st-lost`, `--ok`, `--warn`, `--danger`, `--whatsapp` e `--font-data` todos com uso > 0 nos dois painéis
- [ ] `shared/brand/revy-tokens.css` é a única fonte de cor dos quatro front-ends, e editá-lo muda os quatro
- [ ] Contraste AA nos dois temas para todo par de `PARES_AA`
- [ ] Suítes de `portal-gestao`, `revy-trafego` e `shared/brand` passando
- [ ] `git diff --check` e `git status --short` limpos
