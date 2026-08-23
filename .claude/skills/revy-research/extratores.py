"""Extratores puros: texto de um arquivo -> list[Entrada]. Nunca importam o app."""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

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
    """Todo `@app.<verbo>("/path")` / `@router.<verbo>("/path")` do arquivo.

    `simbolo` e o PATH, nao o nome da funcao: o `--verificar` reabre a linha do
    decorator, e o que esta escrito naquela linha e o path. O nome da funcao
    existe no AST mas mora na linha de baixo, entao nao serve de ancora.
    """
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


def modelos(texto: str, arquivo_rel: str) -> list[Entrada]:
    """Toda classe com `__tablename__ = "..."` literal deste arquivo.

    A chave e o nome da TABELA, nao o da classe: e o nome da tabela que aparece
    na migration, no SQL do dono e na linha que o `--verificar` reabre.
    """
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
    """As migrations de UM produto e a head (a revision que ninguem aponta).

    Head com virgula = duas heads = migration divergente naquele produto. E um
    achado real, nao um bug do gerador: nao esconda somando ou escolhendo uma.
    """
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
