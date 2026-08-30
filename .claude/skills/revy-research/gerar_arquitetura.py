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


def _avisar_secoes_desconhecidas(frescor: dict) -> None:
    """Task 9: a checagem de secao desconhecida mora AQUI, nao em
    `arq_modelo.filtrar`, porque so aqui as duas vistas (SECOES_ARQUITETURA
    + SECOES_SCHEMA) sao vistas juntas — `filtrar` so conhece o conjunto que
    a chamada corrente pediu, e toda secao fora dele (inclusive a da OUTRA
    vista) soaria como desconhecida se a checagem morasse la.

    Nunca levanta: uma secao nova que o extrator passa a emitir e que nao
    cai em nenhuma das duas vistas so precisa aparecer — sumir calada e
    exatamente como este arquivo apodreceria. Um aviso por SECAO, nao por
    entrada (816 entradas nao viram 816 linhas de aviso).
    """
    conhecidas = arquitetura.SECOES_ARQUITETURA | arquitetura.SECOES_SCHEMA
    desconhecidas = set()
    for entradas in frescor.get("inventario", {}).values():
        for e in entradas:
            if e["secao"] not in conhecidas:
                desconhecidas.add(e["secao"])
    for secao in sorted(desconhecidas):
        print(f"AVISO secao desconhecida no inventario, fora das duas vistas: {secao}")


def montar(raiz: Path) -> str:
    frescor = json.loads(FRESCOR.read_text(encoding="utf-8"))
    _avisar_secoes_desconhecidas(frescor)
    modelo = arq_modelo.carregar(
        raiz, frescor, arquitetura.NOS, arquitetura.ARESTAS,
        arquitetura.VMS, arquitetura.FLUXOS, arquitetura.BANCOS)
    # A vista Schema (SECOES_SCHEMA + modelo.bancos) ainda nao vai pro HTML
    # nesta task — so o caminho fica pronto e coberto por teste
    # (test_gerar_arquitetura.py). arquitetura.html continua sendo so a
    # vista Arquitetura, agora filtrada.
    m = arq_modelo.filtrar(modelo, arquitetura.SECOES_ARQUITETURA)
    cena = arq_layout.dispor(m, m.vms)
    return arq_render.render(cena, m, ZOOM.read_text(encoding="utf-8"))


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
