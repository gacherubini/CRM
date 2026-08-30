"""Gera arquitetura.html a partir do codigo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5) — le o _frescor.json,
que gerar_mapa.py ja produziu, e a camada de intencao do arquitetura.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import arq_layout
import arq_modelo
import arq_render
import arquitetura
import varredura

PASTA = Path(__file__).resolve().parent
DESTINO = PASTA / "arquitetura.html"
FRESCOR = PASTA / "mapa" / "_frescor.json"
ZOOM = PASTA / "arq_zoom.js"


def montar(raiz: Path) -> str:
    frescor = json.loads(FRESCOR.read_text(encoding="utf-8"))
    modelo = arq_modelo.carregar(
        raiz, frescor, arquitetura.NOS, arquitetura.ARESTAS,
        arquitetura.VMS, arquitetura.FLUXOS)
    cena = arq_layout.dispor(modelo)
    return arq_render.render(cena, modelo, ZOOM.read_text(encoding="utf-8"))


def gerar(raiz: Path, destino: Path) -> None:
    destino.write_text(montar(raiz), encoding="utf-8")


def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    if "--verificar" in argv:
        if not DESTINO.exists():
            print("DIVERGENCIA arquitetura.html nao existe")
            return 1
        if DESTINO.read_text(encoding="utf-8") != montar(raiz):
            print("DIVERGENCIA arquitetura.html esta velho - "
                  "rode sem --verificar e commite")
            return 1
        print("arquitetura confere com o codigo")
        return 0
    gerar(raiz, DESTINO)
    print(f"escrito {DESTINO.relative_to(raiz)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
