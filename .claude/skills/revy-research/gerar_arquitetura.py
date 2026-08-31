"""Gera arquitetura.html a partir do codigo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5) — le o _frescor.json,
que gerar_mapa.py ja produziu, e a camada de intencao do arquitetura.py.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import arq_layout
import arq_modelo
import arq_design
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
    conhecidas = (arquitetura.SECOES_ARQUITETURA
                  | arquitetura.SECOES_SCHEMA
                  | arquitetura.SECOES_DISPENSADAS)
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
    completo = arq_modelo.carregar(
        raiz, frescor, arquitetura.NOS, arquitetura.ARESTAS + arquitetura.ARESTAS_INTERNAS,
        arquitetura.VMS, arquitetura.FLUXOS, arquitetura.BANCOS)
    # Task 10: as duas vistas (Arquitetura x Schema) entram no MESMO html,
    # com um alternador — arq_render.render agora recebe as duas de uma vez.
    # manter_manuais=True: na Arquitetura o componente escrito a mao e' o
    # conteudo, mesmo sem entrada de inventario. Ver arq_modelo._podar.
    arq = arq_modelo.filtrar(completo, arquitetura.SECOES_ARQUITETURA,
                             manter_manuais=True)
    sch = arq_modelo.filtrar(completo, arquitetura.SECOES_SCHEMA)
    # `filtrar` so poda NO (por secao); arestas e fluxos que nao citem um no
    # podado sobrevivem intactos — por isso a Schema ainda carregaria as
    # mesmas arestas/fluxos da Arquitetura se nao fossem zerados aqui. A
    # decisao "Schema nao tem aresta nem fluxo" (fluxo e caminho de
    # execucao, nao relacao de dado) e desta vista, entao e aqui que ela se
    # aplica — nao em `arq_modelo.filtrar`, que e generico para as duas.
    sch = replace(sch, arestas=(), fluxos=())
    vistas = (
        arq_render.Vista("arquitetura", "Arquitetura",
                         arq_layout.dispor(arq, arq.vms, arquitetura.POSICOES), arq),
        arq_render.Vista("schema", "Schema",
                         arq_layout.dispor(sch, sch.bancos), sch),
    )
    # Os tokens da marca sao LIDOS na geracao. `revy-tokens.css` se declara
    # fonte unica; uma pagina de design system que repete os valores a mao
    # vira mentira no primeiro sync_tokens.py.
    tokens = arq_design.ler_tokens(raiz / "shared" / "brand" / "revy-tokens.css")
    return arq_render.render(vistas, ZOOM.read_text(encoding="utf-8"), tokens)


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
