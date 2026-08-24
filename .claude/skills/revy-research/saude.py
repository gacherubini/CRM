"""Saude da camada que o agente escreve: `learnings/` e `decisoes/`.

O mapa tem `--verificar` e o codigo tem teste. Esta camada e prosa, entao nao
da para provar por script que o texto continua verdadeiro. Da para provar duas
coisas mecanicas, e as duas cobrem o comeco do apodrecimento:

1. **o que o aviso manda abrir ainda existe** — caminho e nome de teste citados;
2. **alguem reconferiu ha pouco** — o carimbo `verificado_em`.

O custo de nao cobrar isso ja esta escrito no `learnings/INDEX.md`: o learning
dos bancos afirmou "Portal e Control sao SQLite" por uma semana depois de os
dois virarem Postgres, e quase fez um agente escrever `batch_alter_table` num
Postgres.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import varredura

# Caminho citado em backtick, ancorado logo depois da crase: com pelo menos uma
# barra e extensao conhecida. A ancora e o que separa citacao de mencao —
# `db.py` solto na prosa nao e promessa de abrir, e a glob `*/static/css/...`
# do learning de marca deixa de casar de proposito (nao existe arquivo com
# aquele nome). Sufixo `::funcao` e `:linha` entram e sao aparados.
CAMINHO = re.compile(
    r"`([\w\-./]+/[\w\-.]+\.(?:py|md|json|toml|sh|html|css|ps1))"
    r"(?:::(\w+))?(?::\d+)?`"
)

# Nome de funcao de teste citado sozinho entre crases. Modulo (`test_x.py`) ja
# foi consumido por CAMINHO: tratar os dois com a mesma busca acusava
# `test_loja_financeiro_gate` de nao existir — ele e o arquivo, nao a funcao.
NOME_DE_TESTE = re.compile(r"`(test_[a-z0-9_]+)`")

DEF_DE_TESTE = re.compile(r"^\s*def (test_\w+)", re.M)

CARIMBO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")

# `repo` se confere lendo codigo, e as citacoes dele ja estao sob `--verificar`.
# `infra` e `externo` mudam sem commit nenhum neste repositorio: nada aqui vai
# denunciar que envelheceram, entao o prazo e mais curto.
TETO_DIAS: dict[str, int] = {"repo": 180, "infra": 90, "externo": 90}


@dataclass(frozen=True)
class Reconferir:
    arquivo: str
    fonte: str
    gatilho: str
    motivo: str


def _notas(sk: Path) -> list[Path]:
    notas: list[Path] = []
    for pasta in ("learnings", "decisoes"):
        base = sk / pasta
        if base.is_dir():
            notas += sorted(f for f in base.glob("*.md") if f.name != "INDEX.md")
    return notas


def _cabecalho(texto: str) -> dict[str, str]:
    if not texto.startswith("---\n"):
        return {}
    fim = texto.find("\n---\n", 3)
    if fim < 0:
        return {}
    campos: dict[str, str] = {}
    for linha in texto[4:fim].splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            campos[chave.strip()] = valor.strip()
    return campos


def _resolve(raiz: Path, rel: str) -> bool:
    if (raiz / rel).is_file():
        return True
    return any((raiz / p / rel).is_file() for p in varredura.PRODUTOS)


def _nomes_de_teste(raiz: Path) -> set[str]:
    """Todo `def test_...` do repo, sem entrar em `.venv` nem em `__pycache__`."""
    bases = [raiz / p for p in varredura.PRODUTOS]
    bases += [raiz / "shared", raiz / ".claude/skills/revy-research"]
    nomes: set[str] = set()
    for base in bases:
        if not base.is_dir():
            continue
        for arq in base.rglob("test_*.py"):
            if set(arq.parts) & varredura.IGNORADOS:
                continue
            nomes.update(
                DEF_DE_TESTE.findall(arq.read_text(encoding="utf-8", errors="replace"))
            )
    return nomes


@dataclass(frozen=True)
class Citacao:
    nota: str
    alvo: str
    tipo: str   # "caminho" ou "teste"


def citacoes(sk: Path) -> list[Citacao]:
    """Tudo o que as notas mandam abrir. Separado de `citacoes_mortas` para o
    teste poder cobrar que a busca nao voltou vazia: regex que para de casar
    deixaria a checagem verde por nao ter olhado nada."""
    achadas: list[Citacao] = []
    for nota in _notas(sk):
        texto = nota.read_text(encoding="utf-8")
        nomes: set[str] = set(NOME_DE_TESTE.findall(texto))
        for rel, funcao in CAMINHO.findall(texto):
            achadas.append(Citacao(nota.name, rel, "caminho"))
            if funcao:
                nomes.add(funcao)
        achadas += [Citacao(nota.name, n, "teste") for n in sorted(nomes)]
    return achadas


def citacoes_mortas(sk: Path, raiz: Path) -> list[str]:
    """Aviso que manda abrir o que nao existe mais.

    Nao prova que o texto continua verdadeiro — prova que ele ainda tem para
    onde apontar, que e o primeiro sintoma de learning velho.
    """
    problemas: list[str] = []
    testes: set[str] | None = None
    for c in citacoes(sk):
        if c.tipo == "caminho":
            if not _resolve(raiz, c.alvo):
                problemas.append(f"{c.nota}: nao existe {c.alvo}")
            continue
        if testes is None:
            testes = _nomes_de_teste(raiz)
        if c.alvo not in testes:
            problemas.append(f"{c.nota}: nao existe o teste {c.alvo}")
    return problemas


def a_reconferir(
    sk: Path,
    hoje: date,
    produto: str | None = None,
    teto_dias: dict[str, int] | None = None,
) -> list[Reconferir]:
    """Learnings cujo carimbo venceu — ou que nunca existiu.

    `produto` filtra porque este aviso anda junto do `--frescor <produto>` do
    passo 2: despejar ali os learnings dos outros cinco produtos e o jeito mais
    rapido de ensinar o agente a ignorar a saida inteira.
    """
    tetos = teto_dias or TETO_DIAS
    vencidos: list[Reconferir] = []
    base = sk / "learnings"
    if not base.is_dir():
        return vencidos
    for nota in sorted(f for f in base.glob("*.md") if f.name != "INDEX.md"):
        campos = _cabecalho(nota.read_text(encoding="utf-8"))
        fonte = campos.get("fonte", "")
        if produto is not None:
            dono = campos.get("produto", "")
            if dono != "todos" and produto not in dono:
                continue
        carimbo = CARIMBO.match(campos.get("verificado_em", ""))
        if carimbo is None:
            motivo = "nunca reconferido"
        else:
            dias = (hoje - date(*(int(g) for g in carimbo.groups()))).days
            if dias <= tetos.get(fonte, 90):
                continue
            motivo = f"conferido ha {dias} dias"
        vencidos.append(Reconferir(
            arquivo=nota.name,
            fonte=fonte,
            gatilho=campos.get("gatilho", ""),
            motivo=motivo,
        ))
    return vencidos
