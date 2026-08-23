"""Gera mapa/<produto>.md a partir do codigo. Stdlib apenas.

Nao importa `app` de produto nenhum (invariante do AGENTS.md secao 5): tudo o
que entra aqui foi lido como texto e parseado com `ast` pelos extratores.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import extratores
import varredura
from varredura import Entrada

PASTA_MAPA = Path(__file__).resolve().parent / "mapa"

# Onde o Alembic de TODO produto guarda as versions. Medido em 23/08: os cinco
# produtos com migration usam exatamente esta pasta (o catalogo nao tem
# migration nenhuma). Uma constante so, porque o mesmo valor localiza o arquivo
# e recompoe o caminho que vai para o mapa - se fossem dois, um dia divergiam.
SUBPASTA_DE_MIGRATIONS = "alembic/versions"

ORDEM = ("aviso", "rota", "modelo", "worker", "flag", "migration", "template")
TITULOS = {
    "aviso": "Avisos do gerador",   # so aparece quando ha algo a avisar
    "rota": "Rotas", "modelo": "Modelos", "worker": "Workers",
    "flag": "Flags", "migration": "Migrations", "template": "Templates",
}

# A UNICA parte escrita a mao do mapa, porque nao e inferivel do codigo - e e
# onde moram as duas excecoes que sempre mordem quem chega agora.
TESTES: dict[str, dict[str, str]] = {
    "chatbot-api": {
        "macos": "cd chatbot-api && .venv/bin/python -m pytest -q",
        "windows": r"cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "portal-gestao": {
        "macos": "cd portal-gestao && .venv/bin/python -m pytest -q",
        "windows": (
            r"cd portal-gestao && .\.venv\Scripts\python.exe "
            r"-m pytest -p no:cacheprovider -q"
        ),
        "nota": (
            "No Windows, -p no:cacheprovider: o .pytest_cache do Portal quebra "
            "com WinError 183."
        ),
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
        "windows": (
            r"cd revy-trafego && ..\portal-gestao\.venv\Scripts\python.exe "
            r"-m pytest -q"
        ),
        "nota": "NAO tem .venv proprio. Usa o do portal-gestao.",
    },
}


def sha_atual(raiz: Path) -> str:
    saida = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=raiz, capture_output=True, text=True, check=False,
    )
    return saida.stdout.strip() or "desconhecido"


def _com_pasta_de_migration(entrada: Entrada) -> Entrada:
    """Recompoe `alembic/versions/<nome>` no `arquivo` da migration.

    `extratores.migrations` guarda so o NOME do arquivo, porque a pasta e fixa
    e ele recebe a pasta pronta. Todas as outras secoes guardam caminho
    relativo a pasta do produto - que e o que o contrato da `Entrada` pede e o
    que o `--verificar` vai reabrir. Sem esta recomposicao o mapa mandaria o
    leitor para `0025_x.py`, que nao existe a partir da raiz do produto.

    Montar o caminho pela `chave` seria pior ainda: no motor a revision e
    "0014" e o arquivo e "0014_cliente_operacional_projecao.py".
    """
    if entrada.secao != "migration" or "/" in entrada.arquivo:
        return entrada
    return replace(entrada, arquivo=f"{SUBPASTA_DE_MIGRATIONS}/{entrada.arquivo}")


def _pasta_de_versions(raiz: Path, produto: str) -> Path:
    return raiz / produto / SUBPASTA_DE_MIGRATIONS


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
    de_migration, _ = extratores.migrations(_pasta_de_versions(raiz, produto))
    entradas.extend(_com_pasta_de_migration(e) for e in de_migration)
    return entradas


def head_de(raiz: Path, produto: str) -> str:
    _, head = extratores.migrations(_pasta_de_versions(raiz, produto))
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
            # linha 0 = "basta o arquivo existir" (contrato do --verificar).
            # Escrever "arquivo:0" mandaria o leitor para uma linha que nao ha.
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
        inventario[produto] = [asdict(e) for e in entradas]
        print(f"{produto}: {len(entradas)} entradas")
    (PASTA_MAPA / "_frescor.json").write_text(
        json.dumps({"sha": sha, "inventario": inventario}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"selo de frescor: {sha}")


def verificar(raiz: Path) -> list[str]:
    """Reabre cada `arquivo:linha` do selo e prova que a promessa se cumpre.

    Contrato da `Entrada`, literal: `linha > 0` -> o texto daquela linha
    precisa CONTER o `simbolo`; `linha == 0` -> basta o arquivo existir.

    De proposito NAO regenera nada antes de conferir. Se regenerasse, o mapa
    concordaria consigo mesmo e o comando passaria sempre - a graca e pegar o
    mapa commitado envelhecendo em relacao ao codigo.

    O `arquivo` da `Entrada` ja e relativo a pasta do produto, migration
    inclusive (`_com_pasta_de_migration` recompoe `alembic/versions/` na
    geracao). Recompor de novo aqui mandaria toda migration para
    `alembic/versions/alembic/versions/...` e inventaria centenas de
    divergencias que nao existem.
    """
    caminho = PASTA_MAPA / "_frescor.json"
    if not caminho.exists():
        return ["mapa/_frescor.json nao existe - rode o gerador"]
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    problemas: list[str] = []
    for produto, entradas in dados.get("inventario", {}).items():
        base = raiz / produto
        for bruta in entradas:
            alvo = base / bruta["arquivo"]
            if not alvo.exists():
                problemas.append(f"{produto}: sumiu {bruta['arquivo']}")
                continue
            if bruta["linha"] <= 0:
                continue
            linhas = alvo.read_text(encoding="utf-8", errors="replace").splitlines()
            if bruta["linha"] > len(linhas):
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} "
                    f"passou do fim do arquivo ({len(linhas)} linhas)"
                )
                continue
            if bruta["simbolo"] not in linhas[bruta["linha"] - 1]:
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} "
                    f"nao contem {bruta['simbolo']!r}"
                )
    return problemas


def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    if "--verificar" in argv:
        problemas = verificar(raiz)
        for p in problemas:
            print(f"DIVERGENCIA {p}")
        if problemas:
            print(
                f"{len(problemas)} divergencias - o mapa esta velho. "
                "Rode sem --verificar."
            )
            return 1
        print("mapa confere com o codigo")
        return 0
    escrever_tudo(raiz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
