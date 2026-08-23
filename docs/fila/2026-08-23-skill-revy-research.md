# Skill `revy-research` — Plano de Implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans` para executar tarefa por tarefa. Os passos usam checkbox (`- [ ]`).

**Goal:** Uma skill de projeto que, ao ser invocada antes de codar, entrega ao agente `arquivo:linha` de toda rota, modelo, worker, migration, flag e template dos 6 produtos, mais as armadilhas conhecidas e as decisões do dono a não re-propor.

**Architecture:** Um gerador em AST estático da stdlib varre os 694 arquivos `.py` dos seis produtos (a árvore inteira tem 10.288, dos quais 9.564 — 93% — vivem nos cinco `.venv`) e escreve `mapa/<produto>.md`. Um modo `--verificar` reabre cada `arquivo:linha` escrita e prova que o símbolo prometido está lá — o mapa não pode mentir. `SKILL.md` é só protocolo; o volume mora em arquivos vizinhos carregados sob demanda.

**Tech Stack:** Python 3 stdlib apenas (`ast`, `pathlib`, `json`, `unittest`, `subprocess` para git). Sem dependência, sem `.venv`, sem importar o `app` de nenhum produto.

**Spec:** [`docs/referencia-viva/specs/2026-08-23-skill-revy-research-design.md`](../referencia-viva/specs/2026-08-23-skill-revy-research-design.md)

## Global Constraints

Valem para toda tarefa deste plano.

- **Stdlib apenas.** Zero `pip install`. Zero import de `app` de qualquer produto (invariante do `AGENTS.md` §5). O gerador lê arquivo como texto e parseia com `ast`; nunca executa código de produto.
- **Roda nos dois SOs.** Windows: `python`. macOS: `python3`. O comando `python3` **não existe** no Windows do dono e `python` puro **não existe** no Mac dele — todo comando neste plano aparece nas duas formas.
- **A árvore de trabalho tem 9 arquivos modificados que NÃO são deste plano** (`.gitignore`, `n8n/*`, `site/*`, `deploy/fly/3vm/prepare-workflow.ps1`). Todo commit lista caminhos explícitos. **Nunca `git add -A`, nunca `git add .`, nunca `git commit -a`.** (`AGENTS.md` §6: não commitar mudança alheia.) Se estas tarefas rodarem **em paralelo**, o `git add` explícito não basta: um `git commit` sem pathspec leva **todo o índice**, inclusive o que outro agente acabou de estagiar. Use a forma restrita nos dois lados: `git add <caminhos> && git commit -m "..." -- <os mesmos caminhos>`.
- **Diretórios sempre excluídos da varredura:** `.venv`, `__pycache__`, `node_modules`, `.git`, `.pytest_cache`, `.pytest-tmp`, `test-tmp-*`, `graphify-out`.
- **Os 6 produtos são exatamente:** `chatbot-api`, `portal-gestao`, `motor-simulacao`, `estoque-api`, `revy-trafego`, `catalogo-publico`. `site/`, `n8n/`, `shared/` e `deploy/` **não** entram no mapa.
- **`revy-trafego` não tem `.venv`** e usa o do `portal-gestao`. É a exceção que precisa aparecer no mapa.
- **Suspeita não vira commit, vira pergunta.** A seção de cruzamentos é rotulada como suspeita e nunca gera edição automática de código.
- **Sem segredo no git.** Nada de token, cookie ou `.env` real em nenhum arquivo gerado.
- Testes do gerador rodam com `unittest` da stdlib, nunca com `pytest` (que exigiria `.venv`).

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `.gitignore` (modificar) | Passar a versionar `.claude/skills/` mantendo o resto de `.claude/` ignorado |
| `AGENTS.md` (modificar) | Passo 0 no §1, para o disparo ser determinístico |
| `.claude/skills/revy-research/SKILL.md` | Só o protocolo. **Teto de ~70 linhas** — é o que carrega em todo disparo |
| `.claude/skills/revy-research/varredura.py` | Achar os arquivos do projeto e ignorar dependência |
| `.claude/skills/revy-research/extratores.py` | Os 7 extratores. Funções puras: texto → `list[Entrada]` |
| `.claude/skills/revy-research/gerar_mapa.py` | CLI, orquestração, render do markdown, `--verificar` |
| `.claude/skills/revy-research/cruzamentos.py` | Clientes HTTP × rotas declaradas; funções sem chamador |
| `.claude/skills/revy-research/test_gerar_mapa.py` | `unittest`, roda sem `.venv` |
| `.claude/skills/revy-research/mapa/` | Gerado e commitado |
| `.claude/skills/revy-research/learnings/` | `INDEX.md` + um arquivo por armadilha |
| `.claude/skills/revy-research/decisoes/` | `INDEX.md` + um arquivo por escolha do dono |

`varredura.py`, `extratores.py` e `cruzamentos.py` são separados de propósito: cada um é testável isolado, e `extratores.py` é o único que precisa entender `ast`.

### O tipo que atravessa todas as tarefas

Definido na Task 2, consumido por todas as seguintes:

```python
@dataclass(frozen=True)
class Entrada:
    secao: str      # "rota" | "modelo" | "migration" | "worker" | "flag" | "template"
    chave: str      # "POST /webhook/cloud"  — o que se procura no mapa
    simbolo: str    # "/webhook/cloud"       — o que --verificar exige na linha
    arquivo: str    # "app/main.py"          — relativo à pasta do produto
    linha: int      # 1-based; 0 = "verificar só que o arquivo existe"
```

A regra de `linha: int` é o contrato do `--verificar`: **`linha > 0` → o texto daquela linha precisa conter `simbolo`; `linha == 0` → basta o arquivo existir.** Vale para template solto, que não é renderizado por nenhuma rota.

`simbolo` é o **texto escrito naquela linha**, não o nome lógico do símbolo. Para rota é o path, porque é o path que aparece no decorator — o nome da função está na linha de baixo e o `--verificar` não o acharia lá.

---

### Task 1: Versionar `.claude/skills/`

Sem isto nada mais importa: a skill não existiria no Mac do dono, nem para subagente em worktree. `.gitignore:46` hoje ignora `.claude/` inteiro, e uma pasta excluída não pode ter arquivo re-incluído — é preciso trocar por exclusão de conteúdo.

**Files:**
- Modify: `.gitignore:46`

**Interfaces:**
- Consumes: nada
- Produces: `.claude/skills/**` versionável. Toda tarefa seguinte depende disto.

- [ ] **Step 1: Ver a linha exata antes de mexer**

```bash
grep -n "^\.claude" .gitignore
```

Esperado: `46:.claude/`

- [ ] **Step 2: Provar que hoje é ignorado (o teste que precisa falhar depois)**

```bash
git check-ignore -v .claude/skills/revy-research/SKILL.md
```

Esperado: `.gitignore:46:.claude/	.claude/skills/revy-research/SKILL.md` — ou seja, ignorado.

- [ ] **Step 3: Trocar a exclusão de pasta por exclusão de conteúdo**

Substituir a linha `.claude/` por estas duas:

```gitignore
.claude/*
!.claude/skills/
```

Atenção: a alteração é **só** nessa linha. O `.gitignore` já tem uma modificação não commitada do dono na linha 37 (`workflow-cloud.ready.json`) — não tocar, não commitar.

- [ ] **Step 4: Provar que `skills/` passou e que o resto continua barrado**

```bash
git check-ignore -v .claude/skills/revy-research/SKILL.md ; echo "skills -> exit $?"
git check-ignore -v .claude/settings.local.json         ; echo "settings -> exit $?"
```

Esperado: `skills -> exit 1` (não ignorado, que é o que queremos) e `settings -> exit 0` com a linha `.claude/*` (segue ignorado, que também é o que queremos).

- [ ] **Step 5: Commit — separando a linha do dono**

`git add .gitignore` estagia o arquivo **inteiro**, e o `.gitignore` tem a linha 37 do dono (`deploy/fly/3vm/workflow-cloud.ready.json`) ainda não commitada. Commitar junto viola a Global Constraint. Como as duas mudanças estão em regiões diferentes do arquivo, dá para separá-las com `stash`:

```bash
git stash push -m "linha 37 do dono" -- .gitignore   # tira a mudanca do dono
grep -n "^\.claude" .gitignore                        # confirma: voltou a `.claude/`
```

Agora refaça **só** a troca do Step 3 (o `stash` desfez também a sua), e commite:

```bash
git add .gitignore
git commit -m "chore(git): versionar .claude/skills/ mantendo o resto de .claude ignorado"
git stash pop                                        # devolve a linha 37 ao dono
```

Conferência obrigatória — as duas coisas têm que ser verdade ao mesmo tempo:

```bash
git show --stat HEAD | grep gitignore
git diff .gitignore
```

Esperado: o commit toca `.gitignore` com **2 inserções e 1 remoção** (só a sua troca), e o `git diff` ainda mostra a linha do dono como pendente. Se o `stash pop` der conflito, a linha do dono **não** se perdeu — está em `git stash list`; resolva à mão deixando as duas mudanças no arquivo.

Se o `git diff .gitignore` sair vazio, você commitou a linha do dono junto: desfaça com `git reset --soft HEAD~1` e refaça.

---

### Task 2: Varredura — achar os 694 dos produtos e ignorar os 9.564 dos `.venv`

**Files:**
- Create: `.claude/skills/revy-research/varredura.py`
- Create: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `PRODUTOS: tuple[str, ...]` — os 6 nomes de pasta
  - `IGNORADOS: frozenset[str]`
  - `raiz_repo() -> Path`
  - `arquivos_py(raiz: Path, produto: str) -> list[Path]`
  - `dataclass Entrada(secao, chave, simbolo, arquivo, linha)`

- [ ] **Step 1: Escrever o teste que falha**

`.claude/skills/revy-research/test_gerar_mapa.py`:

```python
import unittest
from pathlib import Path

import varredura


class TestVarredura(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_raiz_do_repo_tem_agents_md(self):
        self.assertTrue((self.raiz / "AGENTS.md").exists())

    def test_acha_arquivos_do_chatbot(self):
        arquivos = varredura.arquivos_py(self.raiz, "chatbot-api")
        self.assertGreater(len(arquivos), 10)

    def test_nunca_entra_em_venv_nem_pycache(self):
        for produto in varredura.PRODUTOS:
            for caminho in varredura.arquivos_py(self.raiz, produto):
                partes = caminho.parts
                self.assertNotIn(".venv", partes, f"venv vazou em {caminho}")
                self.assertNotIn("__pycache__", partes, f"pycache vazou em {caminho}")

    def test_projeto_e_muito_menor_que_a_arvore_toda(self):
        do_projeto = sum(
            len(varredura.arquivos_py(self.raiz, p)) for p in varredura.PRODUTOS
        )
        self.assertGreater(do_projeto, 300)
        self.assertLess(do_projeto, 2000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `ModuleNotFoundError: No module named 'varredura'`

- [ ] **Step 3: Implementar**

`.claude/skills/revy-research/varredura.py`:

```python
"""Acha os arquivos do PROJETO, nunca os das dependencias."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PRODUTOS: tuple[str, ...] = (
    "chatbot-api",
    "portal-gestao",
    "motor-simulacao",
    "estoque-api",
    "revy-trafego",
    "catalogo-publico",
)

IGNORADOS: frozenset[str] = frozenset({
    ".venv", "__pycache__", "node_modules", ".git",
    ".pytest_cache", ".pytest-tmp", "graphify-out", ".mypy_cache",
})


@dataclass(frozen=True)
class Entrada:
    secao: str
    chave: str
    simbolo: str
    arquivo: str
    linha: int


def raiz_repo() -> Path:
    """Sobe de .claude/skills/revy-research/ ate a raiz do repo."""
    return Path(__file__).resolve().parents[3]


def _ignorado(caminho: Path, base: Path) -> bool:
    for parte in caminho.relative_to(base).parts:
        if parte in IGNORADOS or parte.startswith("test-tmp"):
            return True
    return False


def arquivos_py(raiz: Path, produto: str) -> list[Path]:
    base = raiz / produto
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.rglob("*.py")
        if p.is_file() and not _ignorado(p, base)
    )
```

- [ ] **Step 4: Rodar e ver passar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `OK`, 4 testes. Se `test_projeto_e_muito_menor_que_a_arvore_toda` falhar por passar de 2000, algum diretório de dependência escapou — imprima os caminhos e acrescente o culpado a `IGNORADOS`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/varredura.py .claude/skills/revy-research/test_gerar_mapa.py
git commit -m "feat(revy-research): varredura que enxerga o projeto e ignora os 5 venv"
```

---

### Task 3: Extrator de rotas

O maior ganho isolado do mapa: 56 rotas do chatbot moram num `main.py` de 2.038 linhas.

**Files:**
- Create: `.claude/skills/revy-research/extratores.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: `varredura.Entrada`
- Produces: `extratores.rotas(texto: str, arquivo_rel: str) -> list[Entrada]` — `secao="rota"`, `chave="POST /webhook/cloud"`, `simbolo` = **o path** (`"/webhook/cloud"`), que é o texto da linha do decorator. Não é o nome da função: ele está na linha de baixo e o `--verificar` não o acharia.
- Produces (Step 3b): `extratores.prefixos_de_router(texto: str, arquivo_rel: str) -> list[tuple[str | None, str | None, str]]` e `extratores.aplicar_prefixos(entradas: list[Entrada], includes: list[tuple]) -> list[Entrada]`.

Verificado no levantamento: `APIRouter()` e `include_router()` são chamados **sem `prefix=`** em todo o repo, então hoje o path do decorator é o path real.

**Hoje.** É o único ponto por onde o mapa consegue mentir sem o `--verificar` perceber: se alguém acrescentar `include_router(r, prefix="/v1")`, o decorator continua com o path nu, o `--verificar` segue verde e a `chave` do mapa passa a apontar para uma rota que não existe. Por isso o Step 3b implementa a regra do spec — **compõe o que dá para resolver estaticamente, marca `?` no que não dá, nunca inventa** — e deixa um teste-armadilha que fica vermelho no dia em que o primeiro `prefix=` aparecer.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `test_gerar_mapa.py`:

```python
import extratores

FONTE_ROTAS = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/app/loja/agente", response_class=HTMLResponse)
def pagina_agente(request):
    return 1

@app.post("/webhook/cloud")
async def webhook_cloud(request):
    return 2

@app.exception_handler(RequestValidationError)
def nao_e_rota(request, exc):
    return 3
'''


class TestExtratorDeRotas(unittest.TestCase):
    def test_le_verbo_path_e_funcao(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        chaves = {e.chave for e in achadas}
        self.assertIn("GET /app/loja/agente", chaves)
        self.assertIn("POST /webhook/cloud", chaves)

    def test_exception_handler_nao_e_rota(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        self.assertEqual(len(achadas), 2)

    def test_simbolo_e_o_path_porque_e_isso_que_esta_na_linha(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        por_chave = {e.chave: e for e in achadas}
        self.assertEqual(por_chave["POST /webhook/cloud"].simbolo, "/webhook/cloud")

    def test_linha_aponta_para_o_decorator(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        por_chave = {e.chave: e for e in achadas}
        linha = FONTE_ROTAS.splitlines()[por_chave["POST /webhook/cloud"].linha - 1]
        self.assertIn("/webhook/cloud", linha)

    def test_no_repo_real_o_webhook_cloud_existe(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "main.py"
        achadas = extratores.rotas(alvo.read_text(encoding="utf-8"), "app/main.py")
        self.assertIn("POST /webhook/cloud", {e.chave for e in achadas})
        self.assertGreater(len(achadas), 30)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `ModuleNotFoundError: No module named 'extratores'`

- [ ] **Step 3: Implementar**

`.claude/skills/revy-research/extratores.py`:

```python
"""Extratores puros: texto de um arquivo -> list[Entrada]. Nunca importam o app."""
from __future__ import annotations

import ast

from varredura import Entrada

VERBOS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _decorators_de_rota(no: ast.AST):
    for dec in getattr(no, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        alvo = dec.func
        if not isinstance(alvo, ast.Attribute) or alvo.attr not in VERBOS:
            continue
        if not dec.args or not isinstance(dec.args[0], ast.Constant):
            continue
        path = dec.args[0].value
        if not isinstance(path, str):
            continue
        yield alvo.attr.upper(), path, dec.lineno


def rotas(texto: str, arquivo_rel: str) -> list[Entrada]:
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    achadas: list[Entrada] = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for verbo, path, linha in _decorators_de_rota(no):
            achadas.append(Entrada(
                secao="rota",
                chave=f"{verbo} {path}",
                simbolo=path,
                arquivo=arquivo_rel,
                linha=linha,
            ))
    return achadas
```

Por que `simbolo` é o **path** e não o nome da função: `--verificar` reabre a linha do *decorator*, e o que está escrito naquela linha é o path. O nome da função existe no AST (`no.name`) mas não aparece na linha verificada, então não serve de âncora. A `chave` (`"POST /webhook/cloud"`) é o que se procura no mapa; o `simbolo` é o que prova que a linha é aquela.

- [ ] **Step 3b: Fechar o buraco do `prefix=`**

Regra do spec: *"o gerador compõe quando conseguir resolver estaticamente e marca `?` quando não conseguir — nunca inventa"*. Hoje o repo tem zero `prefix=`, então este código não muda nenhuma linha do mapa. Ele existe para o dia em que mudar.

Acrescentar a `extratores.py`:

```python
from dataclasses import replace


def _alias_para_modulo(arvore: ast.Module) -> dict[str, str]:
    """{nome_local: stem_do_modulo} para os imports deste arquivo."""
    mapa: dict[str, str] = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            origem = (no.module or "").rsplit(".", 1)[-1]
            for a in no.names:
                mapa[a.asname or a.name] = origem
        elif isinstance(no, ast.Import):
            for a in no.names:
                mapa[a.asname or a.name] = a.name.rsplit(".", 1)[-1]
    return mapa


def prefixos_de_router(texto: str, arquivo_rel: str) -> list[tuple]:
    """Todo `include_router(x, prefix=...)` deste arquivo.

    Devolve [(stem_do_modulo | None, prefixo | None, "arquivo:linha")].
    None em qualquer posicao = nao deu para resolver estaticamente.
    include_router SEM prefix= nao entra: nao altera path nenhum.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    alias = _alias_para_modulo(arvore)
    achados: list[tuple] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
        if nome != "include_router":
            continue
        kw = next((k for k in no.keywords if k.arg == "prefix"), None)
        if kw is None:
            continue
        prefixo = kw.value.value if isinstance(kw.value, ast.Constant) else None
        if not isinstance(prefixo, str):
            prefixo = None
        primeiro = no.args[0] if no.args else None
        stem = None
        if isinstance(primeiro, ast.Name):
            stem = alias.get(primeiro.id)
        elif isinstance(primeiro, ast.Attribute) and isinstance(primeiro.value, ast.Name):
            stem = alias.get(primeiro.value.id)
        achados.append((stem, prefixo, f"{arquivo_rel}:{no.lineno}"))
    return achados


def aplicar_prefixos(entradas: list[Entrada], includes: list[tuple]) -> list[Entrada]:
    """Compoe prefixo + path na `chave` das rotas. Nunca inventa.

    `simbolo` NUNCA muda: continua o path do decorator, que e o texto escrito na
    linha e o que o `--verificar` reabre. E por isso que compor a `chave` nao
    quebra a verificacao.
    """
    if not includes:
        return entradas
    por_stem: dict[str, set] = {}
    orfaos: list[str] = []
    for stem, prefixo, onde in includes:
        if stem is None:
            orfaos.append(onde)          # nao da para saber a quais rotas se aplica
        else:
            por_stem.setdefault(stem, set()).add(prefixo)

    saida: list[Entrada] = []
    for e in entradas:
        if e.secao != "rota":
            saida.append(e)
            continue
        stem = e.arquivo.rsplit("/", 1)[-1].removesuffix(".py")
        prefixos = por_stem.get(stem)
        if not prefixos:
            saida.append(e)
        elif len(prefixos) == 1 and None not in prefixos:
            verbo, path = e.chave.split(" ", 1)
            saida.append(replace(e, chave=f"{verbo} {next(iter(prefixos))}{path}"))
        else:
            # prefixo nao literal, ou dois prefixos diferentes para o mesmo modulo
            saida.append(replace(e, chave=f"{e.chave} ?"))

    for onde in sorted(set(orfaos)):
        arquivo, _, _linha = onde.rpartition(":")
        saida.append(Entrada(
            secao="aviso",
            chave="`include_router` com `prefix=` que nao deu para rastrear - "
                  "os paths deste produto podem estar incompletos",
            simbolo="",
            arquivo=arquivo,
            linha=0,
        ))
    return saida
```

O aviso é uma `Entrada` de `linha=0` de propósito: assim ele atravessa `coletar` → `render` → `_frescor.json` → `--verificar` sem mudar assinatura nenhuma, e o `--verificar` só confere que o arquivo existe (o contrato de `linha == 0`).

Acrescentar aos testes:

```python
FONTE_PREFIXO = '''
from fastapi import FastAPI
from .rotas_oferta import router as router_oferta
from .rotas_misterio import router as router_misterio

app = FastAPI()
app.include_router(router_oferta, prefix="/v1")
app.include_router(router_misterio, prefix=PREFIXO_QUE_E_VARIAVEL)
app.include_router(router_oferta)
'''


class TestPrefixoDeRouter(unittest.TestCase):
    def test_armadilha_hoje_o_repo_nao_tem_nenhum_prefix(self):
        """Fica vermelho no dia em que o primeiro prefix= aparecer.

        Quando acontecer: confira no mapa que a rota saiu com o path composto
        (ou com `?`) e so entao apague este teste.
        """
        raiz = varredura.raiz_repo()
        achados = []
        for produto in varredura.PRODUTOS:
            base = raiz / produto
            for caminho in varredura.arquivos_py(raiz, produto):
                achados.extend(extratores.prefixos_de_router(
                    caminho.read_text(encoding="utf-8", errors="replace"),
                    caminho.relative_to(base).as_posix(),
                ))
        self.assertEqual(achados, [], f"apareceu prefix= no repo: {achados}")

    def test_le_o_literal_e_marca_o_que_nao_e_literal(self):
        achados = extratores.prefixos_de_router(FONTE_PREFIXO, "app/main.py")
        self.assertEqual(len(achados), 2)  # o include_router sem prefix= nao conta
        por_stem = {s: p for s, p, _ in achados}
        self.assertEqual(por_stem["rotas_oferta"], "/v1")
        self.assertIsNone(por_stem["rotas_misterio"])

    def test_compoe_o_resolvido_sem_tocar_no_simbolo(self):
        rota = varredura.Entrada(
            secao="rota", chave="POST /oferta", simbolo="/oferta",
            arquivo="app/rotas_oferta.py", linha=10,
        )
        saida = extratores.aplicar_prefixos(
            [rota], [("rotas_oferta", "/v1", "app/main.py:7")]
        )
        self.assertEqual(saida[0].chave, "POST /v1/oferta")
        self.assertEqual(saida[0].simbolo, "/oferta")  # o --verificar continua achando

    def test_marca_interrogacao_quando_nao_resolve(self):
        rota = varredura.Entrada(
            secao="rota", chave="POST /x", simbolo="/x",
            arquivo="app/rotas_misterio.py", linha=3,
        )
        saida = extratores.aplicar_prefixos(
            [rota], [("rotas_misterio", None, "app/main.py:8")]
        )
        self.assertEqual(saida[0].chave, "POST /x ?")
        self.assertEqual(saida[0].simbolo, "/x")

    def test_include_sem_alias_rastreavel_vira_aviso(self):
        saida = extratores.aplicar_prefixos([], [(None, "/v1", "app/main.py:9")])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0].secao, "aviso")
        self.assertEqual(saida[0].linha, 0)
```


- [ ] **Step 4: Rodar e ver passar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `OK`, 14 testes (4 da varredura + 5 de rota + 5 de `prefix=`). O teste contra o repo real deve achar mais de 30 rotas no chatbot (medido: 57 decorators `@app.`, dos quais exatamente um — `@app.exception_handler` na linha 112 — nao e rota; logo 56).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/extratores.py .claude/skills/revy-research/test_gerar_mapa.py
git commit -m "feat(revy-research): extrator de rotas por AST, sem importar o app"
```

---

### Task 4: Extrator de modelos e de migrations

**Files:**
- Modify: `.claude/skills/revy-research/extratores.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: `varredura.Entrada`
- Produces:
  - `extratores.modelos(texto: str, arquivo_rel: str) -> list[Entrada]` — `secao="modelo"`, `chave` = nome da tabela, `simbolo` = nome da tabela
  - `extratores.migrations(pasta_versions: Path) -> tuple[list[Entrada], str]` — a lista e o **head** (a revision que ninguém aponta como `down_revision`). **Atenção**: o `arquivo` da `Entrada` de migration guarda só o **nome do arquivo**, não o caminho relativo ao produto (a pasta é fixa, `alembic/versions/`). Rota e modelo guardam caminho relativo. Quem consumir isso — `render` na Task 6 e `--verificar` na Task 7 — precisa recompor `alembic/versions/<nome>`.

Contagens medidas hoje, para conferir o resultado: chatbot 25, portal 26, control 20, estoque 10, motor 14. Heads medidas em 23/08: `0025_canal_cloud_por_loja`, `0026_copiloto_sinal_destinatario`, `0020_loja_whatsapp_modo`, `0010`, `0014` — **head única nos cinco**, nenhuma divergente.

**Armadilha, achada ao executar esta task:** as migrations do repo usam **dois estilos** de declaração. As antigas escrevem `revision: str = "0001"` (`ast.AnnAssign`, é o caso do motor inteiro e de 8 do estoque); as novas escrevem `revision = "0025_x"` (`ast.Assign`). Ler só `Assign` acha **0 de 14** no motor e 2 de 10 no estoque — e como cada arquivo perdido vira uma head solta, o cálculo do head quebra junto. Daí o helper `_constante_str`, que trata os dois, e o teste `test_le_os_dois_estilos_de_revision_do_repo` que trava a regressão.

- [ ] **Step 1: Escrever os testes que falham**

```python
FONTE_MODELOS = '''
class Loja(Base):
    __tablename__ = "lojas"
    id = Column(Integer)

class FilaVendedor(Base):
    __tablename__ = "fila_vendedor"
'''


class TestExtratorDeModelos(unittest.TestCase):
    def test_acha_tabela_e_classe(self):
        achados = extratores.modelos(FONTE_MODELOS, "app/models_db.py")
        chaves = {e.chave for e in achados}
        self.assertEqual(chaves, {"lojas", "fila_vendedor"})

    def test_linha_aponta_para_o_tablename(self):
        achados = extratores.modelos(FONTE_MODELOS, "app/models_db.py")
        por_chave = {e.chave: e for e in achados}
        linha = FONTE_MODELOS.splitlines()[por_chave["fila_vendedor"].linha - 1]
        self.assertIn("fila_vendedor", linha)

    def test_no_repo_real_fila_vendedor_esta_em_models_db(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "models_db.py"
        achados = extratores.modelos(alvo.read_text(encoding="utf-8"), "app/models_db.py")
        self.assertIn("fila_vendedor", {e.chave for e in achados})


class TestExtratorDeMigrations(unittest.TestCase):
    def test_conta_e_acha_o_head_do_chatbot(self):
        raiz = varredura.raiz_repo()
        entradas, head = extratores.migrations(raiz / "chatbot-api" / "alembic" / "versions")
        self.assertEqual(len(entradas), 25)
        self.assertTrue(head, "head nao pode ser vazio")

    def test_pasta_inexistente_nao_quebra(self):
        entradas, head = extratores.migrations(Path("nao/existe"))
        self.assertEqual(entradas, [])
        self.assertEqual(head, "")
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `AttributeError: module 'extratores' has no attribute 'modelos'`

- [ ] **Step 3: Implementar**

Acrescentar a `extratores.py`:

```python
from pathlib import Path


def modelos(texto: str, arquivo_rel: str) -> list[Entrada]:
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    achados: list[Entrada] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ClassDef):
            continue
        for corpo in no.body:
            alvo_ok = (
                isinstance(corpo, ast.Assign)
                and len(corpo.targets) == 1
                and isinstance(corpo.targets[0], ast.Name)
                and corpo.targets[0].id == "__tablename__"
                and isinstance(corpo.value, ast.Constant)
                and isinstance(corpo.value.value, str)
            )
            if alvo_ok:
                tabela = corpo.value.value
                achados.append(Entrada(
                    secao="modelo",
                    chave=tabela,
                    simbolo=tabela,
                    arquivo=arquivo_rel,
                    linha=corpo.lineno,
                ))
    return achados


def _constante_str(no: ast.AST) -> tuple[str, str] | None:
    """(nome, valor) de `x = "s"` OU de `x: T = "s"`, no topo do modulo.

    As migrations do repo usam os DOIS estilos: as antigas escrevem
    `revision: str = "0001"` (AnnAssign) e as novas `revision = "0020_..."`
    (Assign). Ler so um dos dois perde metade dos arquivos e, pior, quebra a
    cadeia do head: cada arquivo perdido vira uma head solta.
    """
    if isinstance(no, ast.Assign):
        if len(no.targets) != 1 or not isinstance(no.targets[0], ast.Name):
            return None
        nome = no.targets[0].id
    elif isinstance(no, ast.AnnAssign):
        if not isinstance(no.target, ast.Name):
            return None
        nome = no.target.id
    else:
        return None
    if not isinstance(no.value, ast.Constant) or not isinstance(no.value.value, str):
        return None
    return nome, no.value.value


def _revisions(texto: str) -> tuple[str, str]:
    """(revision, down_revision) lidos como constantes de modulo, por AST.

    Nunca importa o modulo do Alembic: rodar uma migration para descobrir o id
    dela executaria codigo de produto (invariante do AGENTS.md).
    """
    revision = down = ""
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return "", ""
    for no in arvore.body:
        par = _constante_str(no)
        if par is None:
            continue
        nome, valor = par
        if nome == "revision":
            revision = valor
        elif nome == "down_revision":
            down = valor
    return revision, down


def migrations(pasta_versions: Path) -> tuple[list[Entrada], str]:
    if not pasta_versions.is_dir():
        return [], ""
    entradas: list[Entrada] = []
    revisions: set[str] = set()
    apontadas: set[str] = set()
    for arquivo in sorted(pasta_versions.glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        revision, down = _revisions(texto)
        if not revision:
            continue
        revisions.add(revision)
        if down:
            apontadas.add(down)
        entradas.append(Entrada(
            secao="migration",
            chave=revision,
            simbolo=revision,
            arquivo=str(arquivo.name),
            linha=0,
        ))
    heads = sorted(revisions - apontadas)
    return entradas, (heads[0] if len(heads) == 1 else ",".join(heads))
```

`linha=0` para migration é intencional: o contrato do `--verificar` é "arquivo existe". O `arquivo` guarda só o nome porque a pasta é fixa por produto.

- [ ] **Step 4: Rodar e ver passar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `OK`. Se o head vier com vírgula, há **duas heads** no produto — isso é um achado real de migration divergente, não um bug do gerador. Pare e reporte ao dono antes de seguir.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/extratores.py .claude/skills/revy-research/test_gerar_mapa.py
git commit -m "feat(revy-research): extratores de modelo e de migration com calculo de head"
```

---

### Task 5: Extratores de worker, flag e template

Três extratores pequenos com a mesma forma. Vão juntos porque um revisor aceitaria ou rejeitaria os três pelo mesmo critério.

**Files:**
- Modify: `.claude/skills/revy-research/extratores.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: `varredura.Entrada`
- Produces:
  - `extratores.workers(texto: str, arquivo_rel: str) -> list[Entrada]` — `secao="worker"`
  - `extratores.flags(texto: str, arquivo_rel: str) -> list[Entrada]` — `secao="flag"`, `chave` = `"REVY_X (default: 0)"`, `simbolo` = `"REVY_X"`
  - `extratores.templates(base_produto: Path) -> list[Entrada]` — `secao="template"`, `linha=0`

Medido em 23/08 **pelo extrator**, não por `grep`: **80 leituras de flag, 67 nomes distintos** (`revy-trafego` 51, `portal-gestao` 27, chatbot 1, catálogo 1, motor 0, estoque 0). O número 74 que circulava vinha de `grep -oE '(REVY_|MULTI_)[A-Z0-9_]+' | sort -u`, que conta pedaço de nome (`REVY_TRAFEGO_`), nome citado só em comentário, e casa no meio de `PORTAL_REVY_TRAFEGO_TIMEOUT`. Não confie nele.

Templates: portal 61, control 20, catálogo 4, estoque 3, chatbot 0, **motor 0**.

**Três armadilhas sintáticas, todas achadas ao executar esta task — é o mesmo padrão do `revision:` da Task 4: o repo usa mais de uma forma onde o plano supunha uma.**

1. **Flag quase nunca é lida por `os.getenv` direto.** O portal lê por `_env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")` (`portal-gestao/app/config.py:5`) e o control por `_env_flag("REVY_CONTROL_DASHBOARD_ENABLED")` (`revy-trafego/app/config.py:6`). Casar só `getenv`/`get` perde **17 flags — justamente as de rollout** da Loja e do Control (Copiloto, Shell, Entitlements, Atendimento, Financeiro, WhatsApp, Dashboard, Provisioning, `MULTI_WHATSAPP_ENABLED`), e o mapa diria "50 flags" sem reclamar. A regra certa é a inversa: **quem recebe o nome da flag como 1º argumento está lendo**, salvo uma lista de escritas (`setenv`, `delenv`, `pop`, …). Assim o próximo helper entra sozinho.
2. **`TemplateResponse` tem três sintaxes, todas vivas no repo:** `("x.html", ctx)` (antiga), `(request, "x.html", ctx)` (Starlette nova) e `(request=request, name="x.html")` (keyword — é o `revy-trafego/app/web/control_ui.py` inteiro). E ~150 das 152 chamadas quebram em várias linhas: **a `linha` da entrada tem de ser a da string, não a do `TemplateResponse(`**, senão o `--verificar` reabre a linha errada e dá falso negativo em todo template.
3. **Worker também mora em `app/worker.py`.** Só os sufixos `_job.py`/`_workers.py` deixam **motor e estoque com zero worker**. E na direção oposta: 7 arquivos de teste casam com o sufixo (`tests/test_rodizio_job.py`, `estoque-api/tests/test_worker.py`) e enfiariam cada `def test_...` no mapa como job de produção — precisa de guarda contra arquivo de teste.

**HTML sob `tests/` não é template.** Os 4 `.html` do motor são páginas de banco salvas como fixture do Playwright (`tests/fixtures/bradesco/ofertas.html`). Listá-las faria o mapa afirmar que o motor renderiza HTML — falso, e é a única forma que sobra de o mapa mentir. Conferido que a exclusão derruba só essas 4: os outros cinco produtos têm zero `.html` sob `tests/`. Teste: `test_html_de_fixture_de_teste_nao_e_template`.

- [ ] **Step 1: Escrever os testes que falham**

```python
FONTE_WORKERS = '''
class FollowupWorker:
    def rodar(self):
        pass

def iniciar_rodizio_job():
    pass
'''

FONTE_FLAGS = '''
import os
ATIVO = os.getenv("REVY_LOJA_COPILOTO_ENABLED", "0") == "1"
MODO = os.environ.get("MULTI_WHATSAPP_ENABLED", "0")
QUALQUER = os.getenv("DATABASE_URL")
'''


class TestExtratorDeWorkers(unittest.TestCase):
    def test_acha_classe_worker(self):
        achados = extratores.workers(FONTE_WORKERS, "app/modo2_workers.py")
        self.assertIn("FollowupWorker", {e.chave for e in achados})

    def test_acha_funcao_job(self):
        achados = extratores.workers(FONTE_WORKERS, "app/rodizio_job.py")
        self.assertIn("iniciar_rodizio_job", {e.chave for e in achados})


class TestExtratorDeFlags(unittest.TestCase):
    def test_pega_revy_e_multi_com_default(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        simbolos = {e.simbolo for e in achados}
        self.assertEqual(simbolos, {"REVY_LOJA_COPILOTO_ENABLED", "MULTI_WHATSAPP_ENABLED"})

    def test_ignora_env_que_nao_e_flag(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        self.assertNotIn("DATABASE_URL", {e.simbolo for e in achados})

    def test_registra_o_default_do_codigo(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        por_simbolo = {e.simbolo: e for e in achados}
        self.assertIn("0", por_simbolo["REVY_LOJA_COPILOTO_ENABLED"].chave)


class TestExtratorDeTemplates(unittest.TestCase):
    def test_portal_tem_dezenas_de_templates(self):
        raiz = varredura.raiz_repo()
        achados = extratores.templates(raiz / "portal-gestao")
        self.assertGreater(len(achados), 40)

    def test_chatbot_nao_tem_template(self):
        raiz = varredura.raiz_repo()
        self.assertEqual(extratores.templates(raiz / "chatbot-api"), [])
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `AttributeError: module 'extratores' has no attribute 'workers'`

- [ ] **Step 3: Implementar**

Acrescentar a `extratores.py`:

```python
from varredura import IGNORADOS

PREFIXOS_DE_FLAG = ("REVY_", "MULTI_")


def workers(texto: str, arquivo_rel: str) -> list[Entrada]:
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    de_arquivo_de_job = arquivo_rel.endswith(("_job.py", "_workers.py"))
    achados: list[Entrada] = []
    for no in arvore.body:
        nome = getattr(no, "name", "")
        if not nome:
            continue
        e_worker = nome.endswith("Worker") or (
            de_arquivo_de_job
            and isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not nome.startswith("_")
        )
        if e_worker:
            achados.append(Entrada(
                secao="worker",
                chave=nome,
                simbolo=nome,
                arquivo=arquivo_rel,
                linha=no.lineno,
            ))
    return achados


def flags(texto: str, arquivo_rel: str) -> list[Entrada]:
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    vistos: dict[str, Entrada] = {}
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not no.args:
            continue
        alvo = no.func
        nome_chamada = getattr(alvo, "attr", "")
        if nome_chamada not in {"getenv", "get"}:
            continue
        primeiro = no.args[0]
        if not isinstance(primeiro, ast.Constant) or not isinstance(primeiro.value, str):
            continue
        nome = primeiro.value
        if not nome.startswith(PREFIXOS_DE_FLAG) or nome in vistos:
            continue
        padrao = ""
        if len(no.args) > 1 and isinstance(no.args[1], ast.Constant):
            padrao = str(no.args[1].value)
        rotulo = f"{nome} (default: {padrao})" if padrao else nome
        vistos[nome] = Entrada(
            secao="flag",
            chave=rotulo,
            simbolo=nome,
            arquivo=arquivo_rel,
            linha=no.lineno,
        )
    return list(vistos.values())


def templates(base_produto: Path) -> list[Entrada]:
    if not base_produto.is_dir():
        return []
    achados: list[Entrada] = []
    for html in sorted(base_produto.rglob("*.html")):
        if any(parte in IGNORADOS for parte in html.parts):
            continue
        rel = html.relative_to(base_produto).as_posix()
        achados.append(Entrada(
            secao="template",
            chave=rel,
            simbolo=html.name,
            arquivo=rel,
            linha=0,
        ))
    return achados
```

- [ ] **Step 4: Rodar e ver passar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `OK`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/extratores.py .claude/skills/revy-research/test_gerar_mapa.py
git commit -m "feat(revy-research): extratores de worker, flag e template"
```

---

### Task 6: Gerar o mapa e o selo de frescor

**Files:**
- Create: `.claude/skills/revy-research/gerar_mapa.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`
- Create (gerado): `.claude/skills/revy-research/mapa/*.md`, `.claude/skills/revy-research/mapa/_frescor.json`

**Interfaces:**
- Consumes: `varredura.*`, `extratores.*`
- Produces:
  - `gerar_mapa.coletar(raiz: Path, produto: str) -> list[Entrada]`
  - `gerar_mapa.render(produto: str, entradas: list[Entrada], head: str, sha: str) -> str`
  - `gerar_mapa.escrever_tudo(raiz: Path) -> None`
  - `gerar_mapa.TESTES: dict[str, dict[str, str]]` — comando por produto e por SO
  - CLI: `python gerar_mapa.py` gera; `--verificar` (Task 7) confere

**A tabela de testes é a única parte escrita à mão do mapa**, porque não é inferível — e é onde mora a exceção que sempre morde:

```python
TESTES: dict[str, dict[str, str]] = {
    "chatbot-api": {
        "macos": "cd chatbot-api && .venv/bin/python -m pytest -q",
        "windows": r"cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "portal-gestao": {
        "macos": "cd portal-gestao && .venv/bin/python -m pytest -q",
        "windows": r"cd portal-gestao && .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q",
        "nota": "No Windows, -p no:cacheprovider: o .pytest_cache do Portal quebra com WinError 183.",
    },
    "motor-simulacao": {
        "macos": "cd motor-simulacao && .venv/bin/python -m pytest -q",
        "windows": r"cd motor-simulacao && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "estoque-api": {
        "macos": "cd estoque-api && .venv/bin/python -m pytest -q",
        "windows": r"cd estoque-api && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "catalogo-publico": {
        "macos": "cd catalogo-publico && .venv/bin/python -m pytest -q",
        "windows": r"cd catalogo-publico && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "revy-trafego": {
        "macos": "cd revy-trafego && ../portal-gestao/.venv/bin/python -m pytest -q",
        "windows": r"cd revy-trafego && ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q",
        "nota": "NAO tem .venv proprio. Usa o do portal-gestao.",
    },
}
```

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestGeracaoDoMapa(unittest.TestCase):
    def test_coleta_do_chatbot_traz_rota_e_modelo(self):
        raiz = varredura.raiz_repo()
        entradas = gerar_mapa.coletar(raiz, "chatbot-api")
        secoes = {e.secao for e in entradas}
        self.assertIn("rota", secoes)
        self.assertIn("modelo", secoes)

    def test_todo_produto_tem_comando_de_teste_nos_dois_sos(self):
        for produto in varredura.PRODUTOS:
            self.assertIn(produto, gerar_mapa.TESTES)
            self.assertIn("macos", gerar_mapa.TESTES[produto])
            self.assertIn("windows", gerar_mapa.TESTES[produto])

    def test_revy_trafego_avisa_que_usa_o_venv_do_portal(self):
        self.assertIn("portal-gestao", gerar_mapa.TESTES["revy-trafego"]["macos"])

    def test_portal_no_windows_desliga_o_cache_do_pytest(self):
        # o .pytest_cache do Portal quebra com WinError 183 no Windows do dono.
        # E conhecimento de "como rodar teste", entao mora no mapa, nao num learning.
        self.assertIn("no:cacheprovider", gerar_mapa.TESTES["portal-gestao"]["windows"])

    def test_render_traz_o_sha_e_as_secoes(self):
        raiz = varredura.raiz_repo()
        entradas = gerar_mapa.coletar(raiz, "chatbot-api")
        texto = gerar_mapa.render("chatbot-api", entradas, head="0025_x", sha="abc1234")
        self.assertIn("abc1234", texto)
        self.assertIn("/webhook/cloud", texto)
        self.assertIn("fila_vendedor", texto)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `ModuleNotFoundError: No module named 'gerar_mapa'`

- [ ] **Step 3: Implementar**

`.claude/skills/revy-research/gerar_mapa.py` (além do `TESTES` acima):

```python
"""Gera mapa/<produto>.md a partir do codigo. Stdlib apenas."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import extratores
import varredura
from varredura import Entrada

PASTA_MAPA = Path(__file__).resolve().parent / "mapa"

ORDEM = ("aviso", "rota", "modelo", "worker", "flag", "migration", "template")
TITULOS = {
    "aviso": "Avisos do gerador",   # so aparece quando ha algo a avisar
    "rota": "Rotas", "modelo": "Modelos", "worker": "Workers",
    "flag": "Flags", "migration": "Migrations", "template": "Templates",
}


def sha_atual(raiz: Path) -> str:
    saida = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=raiz, capture_output=True, text=True, check=False,
    )
    return saida.stdout.strip() or "desconhecido"


def coletar(raiz: Path, produto: str) -> list[Entrada]:
    base = raiz / produto
    entradas: list[Entrada] = []
    includes: list[tuple] = []
    for caminho in varredura.arquivos_py(raiz, produto):
        rel = caminho.relative_to(base).as_posix()
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        entradas.extend(extratores.rotas(texto, rel))
        entradas.extend(extratores.modelos(texto, rel))
        entradas.extend(extratores.workers(texto, rel))
        entradas.extend(extratores.flags(texto, rel))
        includes.extend(extratores.prefixos_de_router(texto, rel))
    # Task 3 Step 3b: prefix= e cross-file, entao so da para aplicar aqui,
    # com o produto inteiro na mao. Hoje `includes` vem vazio e isto e no-op.
    entradas = extratores.aplicar_prefixos(entradas, includes)
    entradas.extend(extratores.templates(base))
    de_migration, _ = extratores.migrations(base / "alembic" / "versions")
    entradas.extend(de_migration)
    return entradas


def head_de(raiz: Path, produto: str) -> str:
    _, head = extratores.migrations(raiz / produto / "alembic" / "versions")
    return head


def render(produto: str, entradas: list[Entrada], head: str, sha: str) -> str:
    por_secao: dict[str, list[Entrada]] = {s: [] for s in ORDEM}
    for e in entradas:
        por_secao.setdefault(e.secao, []).append(e)

    contagem = " · ".join(
        f"{len(por_secao[s])} {TITULOS[s].lower()}"
        for s in ORDEM if s != "aviso" and por_secao[s]
    )
    linhas = [
        f"# {produto} · {contagem}",
        "",
        f"Gerado de `{sha}`. NAO editar a mao — saida de `gerar_mapa.py`.",
        f"Migration head: `{head or 'n/a'}`",
        "",
    ]
    for secao in ORDEM:
        itens = por_secao.get(secao) or []
        if not itens:
            continue
        linhas.append(f"## {TITULOS[secao]}")
        linhas.append("")
        for e in sorted(itens, key=lambda x: (x.arquivo, x.linha, x.chave)):
            alvo = f"{e.arquivo}:{e.linha}" if e.linha else e.arquivo
            linhas.append(f"- `{e.chave}` — {alvo}")
        linhas.append("")

    testes = TESTES[produto]
    linhas.append("## Testes")
    linhas.append("")
    if "nota" in testes:
        linhas.append(f"**{testes['nota']}**")
        linhas.append("")
    linhas.append(f"- macOS: `{testes['macos']}`")
    linhas.append(f"- Windows: `{testes['windows']}`")
    linhas.append("")
    return "\n".join(linhas)


def escrever_tudo(raiz: Path) -> None:
    PASTA_MAPA.mkdir(parents=True, exist_ok=True)
    sha = sha_atual(raiz)
    inventario: dict[str, list[dict]] = {}
    for produto in varredura.PRODUTOS:
        entradas = coletar(raiz, produto)
        head = head_de(raiz, produto)
        (PASTA_MAPA / f"{produto}.md").write_text(
            render(produto, entradas, head, sha), encoding="utf-8"
        )
        inventario[produto] = [vars(e) for e in entradas]
        print(f"{produto}: {len(entradas)} entradas")
    (PASTA_MAPA / "_frescor.json").write_text(
        json.dumps({"sha": sha, "inventario": inventario}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"selo de frescor: {sha}")


def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    escrever_tudo(raiz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Rodar os testes e depois gerar o mapa de verdade**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v && python gerar_mapa.py
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v && python3 gerar_mapa.py
```

Esperado: `OK` nos testes, e depois uma linha por produto. Confira à vista que `chatbot-api` traz mais de 30 rotas e que `portal-gestao` traz mais de 40 templates. Abra `mapa/chatbot-api.md` e confirme que a seção Testes está lá.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/gerar_mapa.py .claude/skills/revy-research/test_gerar_mapa.py .claude/skills/revy-research/mapa/
git commit -m "feat(revy-research): geracao do mapa por produto com selo de frescor"
```

---

### Task 7: `--verificar` — a prova de que o mapa não mente

É a peça que transforma "o mapa está desatualizado?" de opinião em teste.

**Files:**
- Modify: `.claude/skills/revy-research/gerar_mapa.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: `mapa/_frescor.json` escrito na Task 6
- Produces: `gerar_mapa.verificar(raiz: Path) -> list[str]` — lista de divergências, vazia quando tudo bate. CLI `--verificar` sai 1 se houver divergência.

Contrato, já fixado no tipo `Entrada`: **`linha > 0` → o texto daquela linha precisa conter `simbolo`; `linha == 0` → basta o arquivo existir.**

- [ ] **Step 1: Escrever os testes que falham**

```python
class TestVerificacao(unittest.TestCase):
    def test_mapa_recem_gerado_nao_tem_divergencia(self):
        raiz = varredura.raiz_repo()
        gerar_mapa.escrever_tudo(raiz)
        self.assertEqual(gerar_mapa.verificar(raiz), [])

    def test_entrada_mentirosa_e_pega(self):
        raiz = varredura.raiz_repo()
        gerar_mapa.escrever_tudo(raiz)
        caminho = gerar_mapa.PASTA_MAPA / "_frescor.json"
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["inventario"]["chatbot-api"].append({
            "secao": "rota", "chave": "GET /inventado",
            "simbolo": "/rota-que-nao-existe-em-lugar-nenhum",
            "arquivo": "app/main.py", "linha": 1,
        })
        caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        problemas = gerar_mapa.verificar(raiz)
        self.assertTrue(problemas)
        self.assertIn("/rota-que-nao-existe-em-lugar-nenhum", " ".join(problemas))
        gerar_mapa.escrever_tudo(raiz)  # restaura
```

Acrescente `import json` no topo do arquivo de teste.

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `AttributeError: module 'gerar_mapa' has no attribute 'verificar'`

- [ ] **Step 3: Implementar**

Acrescentar a `gerar_mapa.py`:

```python
def verificar(raiz: Path) -> list[str]:
    caminho = PASTA_MAPA / "_frescor.json"
    if not caminho.exists():
        return ["mapa/_frescor.json nao existe — rode o gerador"]
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    problemas: list[str] = []
    for produto, entradas in dados.get("inventario", {}).items():
        base = raiz / produto
        for bruta in entradas:
            if bruta["secao"] == "migration":
                alvo = base / "alembic" / "versions" / bruta["arquivo"]
            else:
                alvo = base / bruta["arquivo"]
            if not alvo.exists():
                problemas.append(f"{produto}: sumiu {bruta['arquivo']}")
                continue
            if bruta["linha"] <= 0:
                continue
            linhas = alvo.read_text(encoding="utf-8", errors="replace").splitlines()
            if bruta["linha"] > len(linhas):
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} passou do fim do arquivo"
                )
                continue
            if bruta["simbolo"] not in linhas[bruta["linha"] - 1]:
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} "
                    f"nao contem {bruta['simbolo']!r}"
                )
    return problemas
```

E trocar o `main` por:

```python
def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    if "--verificar" in argv:
        problemas = verificar(raiz)
        for p in problemas:
            print(f"DIVERGENCIA {p}")
        if problemas:
            print(f"{len(problemas)} divergencias — o mapa esta velho. Rode sem --verificar.")
            return 1
        print("mapa confere com o codigo")
        return 0
    escrever_tudo(raiz)
    return 0
```

- [ ] **Step 4: Rodar e ver passar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v && python gerar_mapa.py --verificar
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v && python3 gerar_mapa.py --verificar
```

Esperado: `OK` nos testes e `mapa confere com o codigo`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/gerar_mapa.py .claude/skills/revy-research/test_gerar_mapa.py .claude/skills/revy-research/mapa/
git commit -m "feat(revy-research): --verificar reabre cada arquivo:linha e prova o mapa"
```

---

### Task 8: `_cruzamentos.md` — as quatro costuras

O bug documentado do Modo 2 (*"o `chatbot-api` não expõe rota de oferta"*, efeito prático: **lead que ninguém pega some**) teria aparecido aqui como uma linha.

Quatro checagens, todas **suspeitas, nunca erros**: rota órfã de servidor, função pública sem chamador, **n8n × chatbot** e **`fly.toml` → app**.

A costura n8n é a de maior severidade do repo: quando ela abre, o bot fica mudo e o produto para. O valor não é achar problema agora — hoje está tudo certo; é a linha aparecer no dia em que alguém renomear uma rota do chatbot.

**Só 2 dos 3 workflows estão no ar.** Conferido no painel do n8n em 23/08:

| Arquivo | Nome declarado | No ar | Última mudança |
|---|---|---|---|
| `workflow-ai-nao-salvos.json` | WhatsApp IA - Somente Nao Salvos | **sim** | 11/08 |
| `workflow-cloud.json` | whatsapp-cloud | **sim** | 16/08 |
| `workflow-teste-numero-autorizado.json` | WhatsApp IA - TESTE 5551980336365 | não | 10/08 |

(`workflow-echo.json` era o quarto — 3 nós, criado em 12/07 no primeiro checkpoint E2E, nunca publicado, sem nenhuma referência em código ou validador. Apagado em 23/08.)

A checagem de rota sem servidor roda **só nos publicados**. Workflow morto chamando rota removida não é incidente, e alarme falso mata a seção.

O `nome` é derivável (está dentro do JSON); **estar publicado não é** — vira a tabela `PUBLICADOS` escrita à mão, no mesmo padrão de `TESTES` e `ALVO_POR_CLIENTE`. Para ela não envelhecer em silêncio, o render **denuncia** qualquer `workflow-*.json` que não esteja classificado: publicou um terceiro, a linha aparece pedindo para acrescentar.

**Armadilha real, colhida ao desenhar isto:** uma primeira checagem crua acusou `/pode-responder` como faltando. Era falso positivo — casou o prefixo `/v1/conversas/` contra a rota `/v1/conversas/{telefone}/mensagens`. A rota certa existe em `chatbot-api/app/main.py:921`. **O casamento é de path inteiro normalizado, nunca de substring.** O teste `test_nao_casa_por_substring` existe para travar isso.

**Files:**
- Create: `.claude/skills/revy-research/cruzamentos.py`
- Modify: `.claude/skills/revy-research/gerar_mapa.py`
- Modify: `.claude/skills/revy-research/test_gerar_mapa.py`

**Interfaces:**
- Consumes: `varredura.arquivos_py`, `gerar_mapa.coletar`
- Produces:
  - `cruzamentos.ALVO_POR_CLIENTE: dict[str, str]` — arquivo de cliente → produto alvo
  - `cruzamentos.paths_chamados(texto: str) -> set[str]` — paths literais e f-strings normalizadas
  - `cruzamentos.normalizar(path: str) -> str` — `/v1/lojas/{id}` e `/v1/lojas/{loja_id}` viram o mesmo
  - `cruzamentos.funcoes_publicas(raiz: Path, produto: str) -> dict[str, tuple[str, int]]`
  - `cruzamentos.nomes_usados(raiz: Path) -> set[str]` — varredura única, cara; nunca chamar dentro de laço
  - `cruzamentos.sem_chamador(raiz: Path, produto: str, usados: set[str]) -> list[tuple[str, str, int]]`
  - `cruzamentos.PUBLICADOS: dict[str, str]` — arquivo → nome no n8n, só os que estão no ar
  - `cruzamentos.n8n_costura(raiz: Path) -> tuple[list[dict], set[str]]` — um dict por workflow (`arquivo`, `nome`, `webhook`, `publicado`) e o conjunto de paths do chatbot chamados **apenas pelos publicados**
  - `cruzamentos.fly_tomls(raiz: Path) -> list[tuple[str, str]]` — `[(caminho_do_toml, app_declarado)]`
  - `cruzamentos.render(raiz: Path, rotas_por_produto: dict[str, set[str]]) -> str` — os paths já chegam normalizados

Padrão verificado no repo: `portal-gestao/app/clients/*.py` chamam `self._request("GET", "/v1/provedores")` e `self._request("GET", f"/v1/provedores/{nome}/credenciais")`.

- [ ] **Step 1: Escrever os testes que falham**

```python
import cruzamentos

FONTE_CLIENTE = '''
class MotorClient:
    def listar(self):
        return self._request("GET", "/v1/provedores")

    def obter(self, nome):
        return self._request("GET", f"/v1/provedores/{nome}/credenciais")
'''


class TestCruzamentos(unittest.TestCase):
    def test_acha_path_literal(self):
        self.assertIn("/v1/provedores", cruzamentos.paths_chamados(FONTE_CLIENTE))

    def test_acha_path_de_fstring_normalizado(self):
        achados = cruzamentos.paths_chamados(FONTE_CLIENTE)
        self.assertIn("/v1/provedores/{}/credenciais", achados)

    def test_normalizar_iguala_nomes_de_parametro(self):
        self.assertEqual(
            cruzamentos.normalizar("/v1/lojas/{id}"),
            cruzamentos.normalizar("/v1/lojas/{loja_id}"),
        )

    def test_todo_cliente_mapeado_aponta_para_produto_real(self):
        for arquivo, alvo in cruzamentos.ALVO_POR_CLIENTE.items():
            self.assertIn(alvo, varredura.PRODUTOS, f"{arquivo} aponta para {alvo}")


class TestCosturaN8n(unittest.TestCase):
    def test_acha_os_tres_arquivos_e_seus_webhooks(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        self.assertEqual(len(workflows), 3)
        paths = {w["webhook"] for w in workflows}
        self.assertIn("whatsapp-ai", paths)     # o canonico
        self.assertIn("whatsapp-cloud", paths)

    def test_so_dois_estao_no_ar(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        no_ar = {w["arquivo"] for w in workflows if w["publicado"]}
        self.assertEqual(no_ar, {"workflow-ai-nao-salvos.json", "workflow-cloud.json"})

    def test_nome_declarado_vem_do_proprio_json(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        por_arquivo = {w["arquivo"]: w["nome"] for w in workflows}
        self.assertEqual(por_arquivo["workflow-cloud.json"], "whatsapp-cloud")

    def test_so_conta_rota_de_workflow_no_ar(self):
        raiz = varredura.raiz_repo()
        _, chamadas = cruzamentos.n8n_costura(raiz)
        self.assertIn("/webhook/cloud", chamadas)
        self.assertIn("/v1/operacao/roteamento", chamadas)
        self.assertGreaterEqual(len(chamadas), 5)

    def test_nao_casa_por_substring(self):
        # /v1/conversas/{}/pode-responder NAO pode casar com
        # /v1/conversas/{}/mensagens so porque compartilham prefixo
        self.assertNotEqual(
            cruzamentos.normalizar("/v1/conversas/{telefone}/pode-responder"),
            cruzamentos.normalizar("/v1/conversas/{telefone}/mensagens"),
        )


class TestFlyTomls(unittest.TestCase):
    def test_acha_os_sete_tomls_e_os_apps(self):
        raiz = varredura.raiz_repo()
        achados = dict(cruzamentos.fly_tomls(raiz))
        apps = set(achados.values())
        self.assertIn("n8n2037", apps)
        self.assertIn("portal2037", apps)
        self.assertGreaterEqual(len(achados), 6)
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v
```

Esperado: `ModuleNotFoundError: No module named 'cruzamentos'`

- [ ] **Step 3: Implementar**

`.claude/skills/revy-research/cruzamentos.py`:

```python
"""Quem chama quem entre produtos. Tudo aqui e SUSPEITA, nunca erro."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import varredura

# Escrito a mao: qual produto cada cliente HTTP consome.
# fipe.py e deepseek.py sao servicos externos e ficam de fora de proposito.
ALVO_POR_CLIENTE: dict[str, str] = {
    "portal-gestao/app/clients/motor.py": "motor-simulacao",
    "portal-gestao/app/clients/chatbot.py": "chatbot-api",
    "portal-gestao/app/clients/estoque.py": "estoque-api",
    "portal-gestao/app/clients/revy_trafego.py": "revy-trafego",
    "chatbot-api/app/inventory.py": "estoque-api",
    "chatbot-api/app/simulation.py": "motor-simulacao",
}

_PARAMETRO = re.compile(r"\{[^}]*\}")


def normalizar(path: str) -> str:
    return _PARAMETRO.sub("{}", path)


def _de_fstring(no: ast.JoinedStr) -> str:
    partes = []
    for pedaco in no.values:
        if isinstance(pedaco, ast.Constant) and isinstance(pedaco.value, str):
            partes.append(pedaco.value)
        else:
            partes.append("{}")
    return "".join(partes)


def paths_chamados(texto: str) -> set[str]:
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return set()
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        for arg in no.args:
            valor = ""
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                valor = arg.value
            elif isinstance(arg, ast.JoinedStr):
                valor = _de_fstring(arg)
            if valor.startswith("/"):
                achados.add(normalizar(valor))
    return achados


def funcoes_publicas(raiz: Path, produto: str) -> dict[str, tuple[str, int]]:
    achadas: dict[str, tuple[str, int]] = {}
    base = raiz / produto
    for caminho in varredura.arquivos_py(raiz, produto):
        rel = caminho.relative_to(base).as_posix()
        if rel.startswith("tests/") or rel.startswith("alembic/"):
            continue
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for no in arvore.body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and not no.name.startswith("_"):
                achadas.setdefault(no.name, (rel, no.lineno))
    return achadas


def nomes_usados(raiz: Path) -> set[str]:
    """Todo identificador referenciado em qualquer produto. Calcular UMA vez."""
    usados: set[str] = set()
    for produto in varredura.PRODUTOS:
        for caminho in varredura.arquivos_py(raiz, produto):
            try:
                arvore = ast.parse(caminho.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for no in ast.walk(arvore):
                if isinstance(no, ast.Name):
                    usados.add(no.id)
                elif isinstance(no, ast.Attribute):
                    usados.add(no.attr)
    return usados


def sem_chamador(raiz: Path, produto: str, usados: set[str]) -> list[tuple[str, str, int]]:
    # a propria definicao nao conta: um `def foo` vira FunctionDef, nao Name
    return [
        (nome, arquivo, linha)
        for nome, (arquivo, linha) in sorted(funcoes_publicas(raiz, produto).items())
        if nome not in usados
    ]


import json
import re as _re

_APP_NO_TOML = _re.compile(r'^\s*app\s*=\s*[\'"]([^\'"]+)[\'"]', _re.MULTILINE)


def _urls_do_json(no) -> set[str]:
    """Desce a arvore do workflow atras de campos url/path."""
    achados: set[str] = set()
    if isinstance(no, dict):
        for chave, valor in no.items():
            if chave in {"url", "path"} and isinstance(valor, str):
                achados.add(valor)
            else:
                achados |= _urls_do_json(valor)
    elif isinstance(no, list):
        for item in no:
            achados |= _urls_do_json(item)
    return achados


# Escrito a mao: quais workflows estao PUBLICADOS no n8n. Conferido no painel
# em 23/08. Nao e derivavel do repo — o arquivo existir nao significa estar no ar.
# workflow-teste-numero-autorizado.json existe no repo e NAO esta publicado.
PUBLICADOS: dict[str, str] = {
    "workflow-ai-nao-salvos.json": "WhatsApp IA - Somente Nao Salvos",
    "workflow-cloud.json": "whatsapp-cloud",
}


def n8n_costura(raiz: Path) -> tuple[list[dict], set[str]]:
    """(um dict por workflow, paths do chatbot chamados pelos PUBLICADOS)."""
    workflows: list[dict] = []
    chamadas: set[str] = set()
    for arquivo in sorted((raiz / "n8n").glob("workflow-*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError):
            continue
        publicado = arquivo.name in PUBLICADOS
        webhook = ""
        for bruto in _urls_do_json(dados):
            if "chatbot-api" in bruto:
                # tira host e expressao n8n; fica so o path
                pedaco = bruto.split("chatbot-api:8000", 1)[-1]
                pedaco = pedaco.split("'", 1)[0].split('"', 1)[0].strip()
                if pedaco.startswith("/") and publicado:
                    chamadas.add(normalizar(pedaco.rstrip("/")))
            elif not bruto.startswith(("http", "=", "{")) and "/" not in bruto:
                webhook = bruto
        workflows.append({
            "arquivo": arquivo.name,
            "nome": dados.get("name", "?"),
            "webhook": webhook,
            "publicado": publicado,
        })
    return workflows, chamadas


def fly_tomls(raiz: Path) -> list[tuple[str, str]]:
    achados: list[tuple[str, str]] = []
    for toml in sorted(raiz.rglob("fly.toml")):
        partes = toml.relative_to(raiz).parts
        if any(p in varredura.IGNORADOS for p in partes):
            continue
        m = _APP_NO_TOML.search(toml.read_text(encoding="utf-8", errors="replace"))
        achados.append((toml.relative_to(raiz).as_posix(), m.group(1) if m else "?"))
    return achados


def render(raiz: Path, rotas_por_produto: dict[str, set[str]]) -> str:
    linhas = [
        "# Cruzamentos entre produtos",
        "",
        "**Tudo aqui e SUSPEITA, nao erro.** Chamada por string montada, dispatch",
        "dinamico e funcao consumida so por teste geram falso positivo.",
        "Regra: suspeita nao vira commit, vira pergunta.",
        "",
        "## Rotas chamadas por cliente HTTP sem servidor declarado",
        "",
    ]
    achou_orfa = False
    for arquivo_cliente, alvo in sorted(ALVO_POR_CLIENTE.items()):
        caminho = raiz / arquivo_cliente
        if not caminho.exists():
            linhas.append(f"- cliente sumiu do repo: `{arquivo_cliente}`")
            achou_orfa = True
            continue
        chamados = paths_chamados(caminho.read_text(encoding="utf-8", errors="replace"))
        declarados = rotas_por_produto.get(alvo, set())
        for path in sorted(chamados - declarados):
            linhas.append(f"- `{path}` chamado em `{arquivo_cliente}` — `{alvo}` nao declara")
            achou_orfa = True
    if not achou_orfa:
        linhas.append("Nenhuma. Todo path chamado tem rota declarada no produto alvo.")
    linhas.append("")

    linhas.append("## Funcoes publicas sem nenhum chamador")
    linhas.append("")
    achou_solta = False
    usados = nomes_usados(raiz)  # uma varredura so, nao uma por produto
    for produto in varredura.PRODUTOS:
        for nome, arquivo, linha in sem_chamador(raiz, produto, usados):
            linhas.append(f"- `{nome}` — {produto}/{arquivo}:{linha}")
            achou_solta = True
    if not achou_solta:
        linhas.append("Nenhuma.")
    linhas.append("")

    # --- costura n8n x chatbot: a junta onde o bot fica mudo ---
    workflows, chamadas = n8n_costura(raiz)
    declaradas = rotas_por_produto.get("chatbot-api", set())
    linhas.append("## n8n x chatbot")
    linhas.append("")
    linhas.append("| Arquivo | Nome | Webhook | No ar |")
    linhas.append("|---|---|---|---|")
    for w in workflows:
        marca = "SIM" if w["publicado"] else "nao"
        linhas.append(f"| `{w['arquivo']}` | {w['nome']} | `{w['webhook'] or '-'}` | {marca} |")
    linhas.append("")
    nao_classificados = [
        w["arquivo"] for w in workflows
        if not w["publicado"] and w["arquivo"] not in PUBLICADOS
    ]
    if nao_classificados:
        linhas.append(
            "Workflows fora da tabela PUBLICADOS em `cruzamentos.py`: "
            + ", ".join(f"`{a}`" for a in nao_classificados)
            + ". Se algum entrou no ar, acrescente — senao a checagem abaixo o ignora."
        )
        linhas.append("")
    linhas.append("Rotas chamadas pelos workflows **no ar**:")
    linhas.append("")
    faltando = sorted(chamadas - declaradas)
    if faltando:
        for path in faltando:
            linhas.append(f"- **SEM SERVIDOR** `{path}` — nenhuma rota do chatbot declara")
    else:
        linhas.append(f"Todas as {len(chamadas)} estao declaradas no chatbot.")
    linhas.append("")

    # --- fly.toml: quais existem e para que app cada um aponta ---
    linhas.append("## fly.toml no repo")
    linhas.append("")
    linhas.append("Os da pasta de cada produto apontam para apps monoliticos DESTRUIDOS")
    linhas.append("(ver AGENTS.md secao 5). Deploy so por deploy/fly/3vm/.")
    linhas.append("")
    for caminho, app in fly_tomls(raiz):
        linhas.append(f"- `{caminho}` -> `{app}`")
    linhas.append("")
    return "\n".join(linhas)
```

Em `gerar_mapa.py`: acrescentar `import cruzamentos` no topo, junto dos outros imports, e inserir este bloco em `escrever_tudo` **depois** do laço `for produto in varredura.PRODUTOS:` e **antes** da escrita do `_frescor.json`. Ele reaproveita o `inventario` que o laço já preencheu — não precisa de variável nova nem de segunda coleta:

```python
    rotas_por_produto = {
        produto: {
            cruzamentos.normalizar(item["simbolo"])
            for item in itens
            if item["secao"] == "rota"
        }
        for produto, itens in inventario.items()
    }
    (PASTA_MAPA / "_cruzamentos.md").write_text(
        cruzamentos.render(raiz, rotas_por_produto), encoding="utf-8"
    )
    print(f"cruzamentos: {sum(len(v) for v in rotas_por_produto.values())} rotas declaradas")
```

- [ ] **Step 4: Rodar e ver passar, depois ler o resultado**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v && python gerar_mapa.py && cat mapa/_cruzamentos.md
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v && python3 gerar_mapa.py && cat mapa/_cruzamentos.md
```

Esperado: `OK`, e um `_cruzamentos.md` legível com as quatro seções. **Leia a saída antes de commitar**, conferindo três coisas:

1. A lista de funções sem chamador não pode ter centenas de linhas. Se tiver, o detector está frouxo demais: restrinja `funcoes_publicas` a `app/*.py` de primeiro nível e rode de novo. Seção que grita lobo é seção que ninguém lê.
2. A seção **n8n × chatbot** deve trazer 3 linhas na tabela, **2 marcadas `SIM`** em "No ar", e dizer que todas as rotas chamadas pelos publicados estão declaradas — foi o estado medido em 23/08. Se aparecer `SEM SERVIDOR`, **pare e leve ao dono**: ou é falso positivo de normalização, ou é o bot prestes a ficar mudo. Nenhum dos dois se resolve commitando.
3. A tabela de `fly.toml` deve trazer **7 linhas**.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/cruzamentos.py .claude/skills/revy-research/gerar_mapa.py .claude/skills/revy-research/test_gerar_mapa.py .claude/skills/revy-research/mapa/
git commit -m "feat(revy-research): cruzamentos — rota orfa e funcao sem chamador, como suspeita"
```

---

### Task 9: `SKILL.md` e o passo 0 no `AGENTS.md`

Sem esta tarefa nada do que foi construído é lido por ninguém.

**Files:**
- Create: `.claude/skills/revy-research/SKILL.md`
- Create: `.claude/skills/revy-research/propostas.md`
- Modify: `AGENTS.md` §1 ("Antes de qualquer ferramenta") — **abre** o loop
- Modify: `AGENTS.md` §6 ("Antes de dizer que acabou") — **fecha** o loop

**Interfaces:**
- Consumes: tudo que as tarefas anteriores produziram
- Produces: o disparo, o tronco→briefing→roteamento e as três camadas do loop

O `SKILL.md` é o único arquivo que carrega em **todo** disparo. Cada linha aqui
custa em toda tarefa futura — escreva curto e não deixe conteúdo entrar. Teto:
~70 linhas. Conteúdo mora nos arquivos vizinhos, carregados sob demanda.

- [ ] **Step 1: Escrever o `SKILL.md`**

```markdown
---
name: revy-research
description: Use antes de codar, corrigir, implementar, debugar ou propor qualquer coisa em qualquer produto do monorepo Revy (chatbot-api, portal-gestao, motor-simulacao, estoque-api, revy-trafego, catalogo-publico). Entrega arquivo:linha de rota, modelo, worker, migration, flag e template, as armadilhas ja conhecidas e as decisoes do dono que nao devem ser re-propostas.
---

# revy-research

694 arquivos `.py` nos seis produtos, dentro de uma arvore de 10.288: 93% do que
uma busca as cegas devolve e codigo-fonte dos cinco `.venv`. Esta skill e **porta, nao caminho** — da o
contexto que so ela tem e entrega para quem ja sabe o resto. Nao improvise
protocolo de implementar, propor ou depurar.

## 1. Tronco — sempre, antes de qualquer coisa

1. **Um produto, dos seis.** Cruzou dois? PARE e diga ao dono: entre produtos so
   ha HTTP versionado.
2. **Frescor:** `git diff --name-only <sha>..HEAD -- <produto>/`, `<sha>` de
   `mapa/_frescor.json`. Vazio: siga calado. Nao vazio: diga quantos e ofereca regerar.
3. **Abra `mapa/<produto>.md`**, nunca `main.py` inteiro (o do portal tem 2.609
   linhas): `arquivo:linha` de rota, modelo, worker, migration, flag e template,
   mais o comando de teste nos dois SOs.
4. **Leia `learnings/INDEX.md` e `decisoes/INDEX.md`;** abra so os que batem —
   normalmente zero, um ou dois. As decisoes sao lidas **aqui**, antes de rotear:
   depois, a skill destino ja comecou cega e re-poe o que o dono recusou.

## 2. Briefing

Empacote no formato de `docs/referencia-viva/agents/task-brief.md`: produto,
arquivos com linha, invariantes, learnings que batem, decisoes que restringem,
comando de teste nos dois SOs. Roteamento sem briefing e so um "va para la".

## 3. Roteamento

| O que o dono quer | Va para |
|---|---|
| construir algo novo, desenhar, decidir rumo | `superpowers:brainstorming` |
| bug, teste vermelho, comportamento estranho | `superpowers:systematic-debugging` |
| implementar feature ou correcao | `superpowers:test-driven-development` |
| ja tem spec, quer plano | `superpowers:writing-plans` |
| ja tem plano, quer executar | `superpowers:subagent-driven-development` |
| mudar UI da Loja/Control | `frontend-design` + as 13 recusas em `decisoes/` |
| achar que acabou | `superpowers:verification-before-completion` |

Destino nao instalado? Siga o tronco e **avise**; nunca improvise o que faltou. O
fechamento mora no `AGENTS.md` §6 — a esta altura outra skill esta no comando.

## Regras

- **O mapa nao se edita a mao.** E saida de script: erro no mapa e erro no gerador.
- **`_cruzamentos.md` e suspeita, nao erro.** Suspeita nao vira commit, vira pergunta.
- **Julgamento nao mora aqui.** Armadilha de arquitetura e "nao mexa aqui" sao do
  `README.md` do produto. O mapa aponta; nao copia.
- **Poda.** Learning sem `gatilho` ninguem acha. Ja ha um do mesmo gatilho? edite o
  existente. Seguiu um e ele nao e mais verdade? apague arquivo e linha do indice
  no mesmo commit. Passou de ~40? avise: indice de 200 linhas mata o passo 4.
- **Nao edite este `SKILL.md`.** Protocolo errado vira uma linha em `propostas.md`.
  Ele carrega em todo disparo: derivando sozinho vira 400 linhas que ninguem revisou.
- **Nao re-proponha:** separar isto em quatro skills, nem escrever protocolo proprio
  de implementar/propor/depurar. Recusado em 23/08.

## Regerar

Windows usa `python`; o Mac do dono so tem `python3`. Vale para os dois comandos.

    cd .claude/skills/revy-research
    python gerar_mapa.py               # regera o mapa
    python gerar_mapa.py --verificar   # so confere; sai 1 se o mapa mentir
```

- [ ] **Step 1b: Criar o `propostas.md` vazio**

`.claude/skills/revy-research/propostas.md`:

```markdown
# Propostas de mudanca no protocolo

O agente escreve aqui quando **este protocolo** falhou — nao quando o codigo
falhou. Uma linha por proposta: o que falhou, o que mudaria. O dono le e decide.
Proposta aplicada sai desta lista e entra no `SKILL.md`.

| Data | O que falhou no protocolo | O que eu mudaria |
|---|---|---|
```

- [ ] **Step 2: Verificar que a skill é reconhecida**

```bash
ls -la .claude/skills/revy-research/SKILL.md
head -4 .claude/skills/revy-research/SKILL.md
```

Esperado: o arquivo existe e as 4 primeiras linhas são o frontmatter com `name:` e `description:`.

- [ ] **Step 3: Acrescentar o passo 0 no `AGENTS.md`**

Em `AGENTS.md` §1 ("Antes de qualquer ferramenta"), inserir **antes** do atual item 1:

```markdown
0. Invoque a skill `revy-research`. Ela dá `arquivo:linha` de tudo, as
   armadilhas conhecidas e as decisões que não se re-propõem.
```

Não renumerar os itens seguintes — o texto do repo referencia "§1 passo 3" em outros lugares. O item novo é o zero.

- [ ] **Step 3b: Fechar o loop no `AGENTS.md` §6**

Este passo é o que impede o loop de morrer. A skill só faz o primeiro passo; quando a tarefa acaba, quem está no comando é o `test-driven-development` ou o `systematic-debugging`, e a `revy-research` já saiu de cena. O fechamento tem que morar onde todo mundo passa.

Em `AGENTS.md` §6 ("Antes de dizer que acabou"), que hoje já lista testes do produto, `alembic upgrade head`, `validate_workflow.py` e `git diff --check`, acrescentar ao fim:

```markdown
Mexeu em rota, modelo, worker, migration ou flag? Regere o mapa e commite junto
com o código: `cd .claude/skills/revy-research && python gerar_mapa.py` (Windows)
ou `python3 gerar_mapa.py` (macOS).
Algo te surpreendeu? Escreva um learning — procurando duplicata pelo gatilho antes.
```

- [ ] **Step 4: Confirmar que nada mais no `AGENTS.md` mudou**

```bash
git diff AGENTS.md
```

Esperado: **6 linhas acrescentadas** (2 no §1, 4 no §6), nenhuma removida. Se aparecer linha removida, alguma numeração foi mexida — desfaça.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/revy-research/SKILL.md .claude/skills/revy-research/propostas.md AGENTS.md
git commit -m "feat(revy-research): SKILL.md com tronco, briefing, roteamento e passo 0 no AGENTS.md"
```

Antes de commitar, confira o teto:

```bash
wc -l .claude/skills/revy-research/SKILL.md
```

Esperado: **67 linhas**, teto de ~70. (O spec estimou ~55 contando só tronco
+ briefing + roteamento; Poda e Regras, que o próprio spec manda estarem aqui, não
cabiam nessa conta.) Passou muito de 65: tem conteúdo no lugar de porta, ou
protocolo que alguma skill do superpowers já faz. Mova ou corte.

---

### Task 10: Migrar as memórias para `learnings/` e `decisoes/`

**Files:**
- Create: `.claude/skills/revy-research/learnings/INDEX.md` + ~20 arquivos
- Create: `.claude/skills/revy-research/decisoes/INDEX.md` + ~6 arquivos

**Interfaces:**
- Consumes: `SKILL.md` (define o formato)
- Produces: os dois índices que o protocolo manda ler

Fonte: `~/.claude/projects/C--Users-guilh-Documents-codigo-bot-whatsapp-financiamento/memory/`. Ler `MEMORY.md` (o índice) e depois cada arquivo citado.

Classificação, já decidida com o dono:

| Vai para | Critério | Exemplos |
|---|---|---|
| `learnings/` | armadilha técnica reproduzível | *o chatbot responde SQLite e mente*; *teste verde ≠ feature existe*; *pytest não roda o JS do Copiloto*; *n8n cheio derruba o bot*; *bump do `?v=` no `app.css`*; *scripts Fly falham silenciosamente no Windows*; *import do n8n desativa o workflow*; *flags do app2037 são secrets*; *nunca casar lead↔auditoria por telefone mascarado* |
| `decisoes/` | escolha do dono a não re-propor | *financeiro sem rateio*; *vendedor confirma venda*; *Copiloto ≠ Seller AI*; *13 itens de UX recusados*; *effort xhigh é intencional* |
| **fica na memória pessoal** | estado que expira em dias | *bancos LIVE e próximo foco*; *v114 LIVE*; *bugs de nav relatados em 02/08* |

**Exceção:** *"revy-trafego não tem `.venv`, use o do portal-gestao"* **não vira learning** — já está na tabela `TESTES` do gerador (Task 6), onde é lida sempre. Não duplicar.

- [ ] **Step 1: Ler o índice das memórias**

```bash
cat ~/.claude/projects/C--Users-guilh-Documents-codigo-bot-whatsapp-financiamento/memory/MEMORY.md
```

- [ ] **Step 2: Escrever um learning, no formato exato**

Exemplo real, `.claude/skills/revy-research/learnings/2026-08-23-alembic-mente-sem-database-url.md`:

```markdown
---
gatilho: rodar alembic ou conferir migration de producao
produto: chatbot-api
custo: 1h30
---
# `alembic current` responde SQLite e mente

Sem `CHATBOT_DATABASE_URL` no ambiente, o `alembic current` do chatbot responde
a partir do SQLite local, com cara de sucesso. Voce conclui que producao esta na
head e nao esta. As migrations sao fail-fast no boot do bundle, entao o erro so
aparece no deploy.

Sempre:

    CHATBOT_DATABASE_URL=<postgres> .venv/bin/alembic current
```

Regras do formato: `gatilho` em linguagem de tarefa (o que a pessoa vai *fazer*), não em jargão; corpo curto; o comando correto no fim.

- [ ] **Step 3: Escrever uma decisão, no formato exato**

`.claude/skills/revy-research/decisoes/2026-08-16-financeiro-sem-rateio.md`:

```markdown
---
decidido: 2026-08-16
nao_reproponha: rateio de despesa fixa no lucro por moto
---
# Despesa fixa nao entra no lucro de cada moto

O lugar da despesa fixa e o ponto de equilibrio, nao o rateio por unidade.
Nao e falta de implementacao — foi escolha do dono.
```

- [ ] **Step 4: Escrever os dois índices e conferir a contagem**

`learnings/INDEX.md` — uma linha por learning, e nada mais:

```markdown
# Learnings — indice

Leia **so** os de gatilho compatavel com a sua tarefa. Normalmente 0, 1 ou 2.

| Gatilho | Arquivo |
|---|---|
| rodar alembic ou conferir migration de producao | `2026-08-23-alembic-mente-sem-database-url.md` |
| deployar no Fly | `2026-08-23-fly-deploy-usa-arvore-local.md` |
| mexer em app.css do portal ou do control | `2026-08-23-bump-do-v-no-base-html.md` |
```

`decisoes/INDEX.md` no mesmo molde, com a coluna `nao_reproponha` no lugar de `gatilho`. **Acrescente as quatro decisões de 23/08 que estão em "Fora de escopo" na spec**, porque são exatamente o tipo de coisa que volta como sugestão daqui a um mês:

- cortar o diário de trabalho (o `git log` já cobre);
- não separar a skill em quatro (`implementar` / `feature` / `debug` / `research`) — descrições competem pelo mesmo gatilho;
- a skill **não escreve protocolo próprio** de implementar, propor ou depurar — roteia para o superpowers, que já faz e evolui sozinho;
- o `SKILL.md` não se auto-edita; a válvula é `propostas.md`.

```bash
ls .claude/skills/revy-research/learnings/*.md | wc -l   # esperado: ~21 (20 + INDEX)
ls .claude/skills/revy-research/decisoes/*.md  | wc -l   # esperado: ~11 (6 migradas + 4 de 23/08 + INDEX)
```

- [ ] **Step 5: Verificar que todo arquivo está no índice e vice-versa**

```bash
cd .claude/skills/revy-research
for f in learnings/*.md; do
  nome=$(basename "$f")
  [ "$nome" = "INDEX.md" ] && continue
  grep -q "$nome" learnings/INDEX.md || echo "FORA DO INDICE: $nome"
done
echo "conferencia terminada"
```

Esperado: nenhuma linha `FORA DO INDICE`. Um learning fora do índice é um learning morto.

Agora o outro lado, que é a poda: dois learnings com o **mesmo gatilho** significam que a regra "edite o existente" já foi violada na largada.

```bash
cd .claude/skills/revy-research
grep -o "^| [^|]*" learnings/INDEX.md | sort | uniq -d
echo "acima: gatilhos duplicados (esperado: nada)"
```

Esperado: nenhuma saída. Se houver duplicata, funda os dois learnings num só antes de commitar.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/revy-research/learnings/ .claude/skills/revy-research/decisoes/
git commit -m "feat(revy-research): migra learnings e decisoes das memorias de sessao para o repo"
```

---

### Task 11: Ensaio de ponta a ponta e fechamento

Nenhuma tarefa anterior provou que a skill **funciona na prática** — só que o código passa nos testes.

**Files:**
- Modify: `docs/fila/README.md` (mover este card para concluído)
- Modify: `docs/referencia-viva/contexto-compacto.md`

- [ ] **Step 1: Rodar a suíte inteira e o verificador**

```bash
# Windows
cd .claude/skills/revy-research && python -m unittest test_gerar_mapa -v && python gerar_mapa.py --verificar
# macOS
cd .claude/skills/revy-research && python3 -m unittest test_gerar_mapa -v && python3 gerar_mapa.py --verificar
```

Esperado: `OK` e `mapa confere com o codigo`, exit 0. **Cole a saída real no relatório** — não escreva "passou" sem ela.

- [ ] **Step 2: Ensaio cego — a única prova que importa**

Escolha uma pergunta que o mapa deveria responder e responda **usando só o mapa**, sem abrir código:

> "Onde está a rota que recebe o webhook do WhatsApp Cloud, e qual worker faz a re-notificação de 10 minutos do Modo 2?"

```bash
cd .claude/skills/revy-research
grep -n "webhook/cloud" mapa/chatbot-api.md
grep -in "worker\|followup" mapa/chatbot-api.md
```

Esperado: as duas respostas saem do mapa com `arquivo:linha`. Se alguma não sair, **falta uma seção no gerador** — volte à tarefa correspondente antes de fechar. Registre o resultado do ensaio no relatório.

Segunda metade do ensaio: **o roteamento aponta para skills que existem?** Uma tabela que manda ir para uma skill não instalada é pior que tabela nenhuma.

```bash
ls ~/.claude/plugins/cache/*/superpowers/*/skills/ 2>/dev/null | head -20
```

Confira que `brainstorming`, `systematic-debugging`, `test-driven-development`, `writing-plans`, `subagent-driven-development` e `verification-before-completion` aparecem. Alguma faltando: tire a linha da tabela do `SKILL.md` em vez de deixar apontando para o vazio, e anote no relatório.

- [ ] **Step 2b: Cronometrar o gerador — o loop depende disso**

O passo 6 do protocolo manda regerar o mapa e commitá-lo junto com o código sempre que a tarefa mexer em rota, modelo, worker, migration ou flag. Uma regra que custa um minuto **não é obedecida**, e o loop morre em silêncio.

```bash
# Windows
cd .claude/skills/revy-research && powershell -c "Measure-Command { python gerar_mapa.py } | Select-Object -ExpandProperty TotalSeconds"
# macOS
cd .claude/skills/revy-research && time python3 gerar_mapa.py
```

Esperado: **abaixo de ~15 segundos**. Se passar disso, o gargalo quase certamente é `cruzamentos.nomes_usados`, que reparseia todos os produtos. Nesse caso, tire a geração do `_cruzamentos.md` do caminho padrão e ponha atrás de uma flag `--cruzamentos`, para o passo 6 ficar barato. Registre o tempo medido no relatório.

- [ ] **Step 3: Conferir que nenhuma mudança alheia entrou**

```bash
git status --short
git log --oneline -12
```

Esperado: os arquivos do dono (`n8n/*`, `site/*`, `deploy/fly/3vm/prepare-workflow.ps1`, e a linha 37 do `.gitignore`) continuam **modificados e não commitados**. Se algum deles aparecer num commit deste plano, desfaça com `git restore --staged` e refaça o commit com caminhos explícitos.

- [ ] **Step 4: Conferir que nenhum segredo entrou**

```bash
git diff --check
git log -p --since="1 day ago" -- .claude/skills/ | grep -inE "token|secret|password|api[_-]key" | head
```

Esperado: `git diff --check` sem saída, e nenhum segredo real na segunda busca (menção à palavra em comentário é aceitável; valor real não).

- [ ] **Step 5: Mover o card e atualizar o contexto**

Conforme `docs/README.md`: quando um card entra no `main`, no mesmo PR move-se o arquivo, atualiza-se `fila/README.md` e `referencia-viva/contexto-compacto.md`.

```bash
git mv docs/fila/2026-08-23-skill-revy-research.md docs/referencia-viva/planos/
```

Em `fila/README.md`, tirar a linha deste card. Em `contexto-compacto.md`, acrescentar uma linha dizendo que a skill `revy-research` existe, que o mapa é gerado e commitado, e qual o comando de regerar.

- [ ] **Step 6: Commit**

```bash
git add docs/fila/README.md docs/referencia-viva/planos/2026-08-23-skill-revy-research.md docs/referencia-viva/contexto-compacto.md
git commit -m "docs(fila): skill revy-research concluida — card para planos, contexto atualizado"
```
