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
