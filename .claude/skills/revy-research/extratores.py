"""Extratores puros: texto de um arquivo -> list[Entrada]. Nunca importam o app."""
from __future__ import annotations

import ast
from dataclasses import replace

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
