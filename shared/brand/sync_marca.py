"""Distribui a marca em contorno para os quatro front-ends.

Copia, e nao import HTTP, pelo mesmo motivo de sync_tokens.py: cada produto e
um deploy independente, e uma marca buscada de outro servico criaria um modo de
falha novo para resolver o que uma copia com teste de sincronia ja resolve.

Ordem: `python shared/brand/build_marca.py` gera, este script distribui.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tokens import DESTINOS_MARCA, MARCA_ORIGEM, RAIZ


def _origem(nome: str) -> bytes:
    caminho = MARCA_ORIGEM / nome
    if not caminho.exists():
        raise FileNotFoundError(
            f"{nome} nao existe em {MARCA_ORIGEM}. Rode build_marca.py antes."
        )
    return caminho.read_bytes()


def sincronizar() -> list[Path]:
    escritas = []
    for pasta, nomes in DESTINOS_MARCA.items():
        destino_pasta = RAIZ / pasta
        destino_pasta.mkdir(parents=True, exist_ok=True)
        for nome in nomes:
            destino = destino_pasta / nome
            destino.write_bytes(_origem(nome))
            escritas.append(destino)
    return escritas


def divergentes() -> list[Path]:
    fora = []
    for pasta, nomes in DESTINOS_MARCA.items():
        for nome in nomes:
            destino = RAIZ / pasta / nome
            if not destino.exists() or destino.read_bytes() != _origem(nome):
                fora.append(destino)
    return fora


if __name__ == "__main__":
    for p in sincronizar():
        print("escrito:", p.relative_to(RAIZ))
