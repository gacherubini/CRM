"""Funde arquitetura.py + _frescor.json + decisoes/ num Modelo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from varredura import Entrada


class ReferenciaMorta(Exception):
    """O arquitetura.py cita algo que nao existe mais.

    Erro, nunca aviso: referencia morta em silencio e exatamente como este
    arquivo apodreceria. Mesmo espirito do saude.citacoes_mortas.
    """


@dataclass(frozen=True)
class No:
    chave: str
    titulo: str
    papel: str
    vm: str | None = None
    termo: str | None = None
    decisoes: tuple[str, ...] = ()
    spof: bool = False
    spof_porque: str | None = None
    entradas: tuple[Entrada, ...] = ()


@dataclass(frozen=True)
class Aresta:
    de: str
    para: str
    protocolo: str = "http"
    sincrono: bool = True
    retry: bool = False
    inferida: bool = False


@dataclass(frozen=True)
class Vm:
    chave: str
    tipo: str = "fly-machine"
    contem: tuple[str, ...] = ()
    nota: str = ""


@dataclass(frozen=True)
class Passo:
    no: str
    faz: str
    protocolo: str | None = None
    sincrono: bool = True


@dataclass(frozen=True)
class Fluxo:
    chave: str
    titulo: str
    passos: tuple[Passo, ...] = ()
    invariante: str | None = None


@dataclass(frozen=True)
class Modelo:
    nos: tuple[No, ...] = ()
    arestas: tuple[Aresta, ...] = ()
    vms: tuple[Vm, ...] = ()
    fluxos: tuple[Fluxo, ...] = ()
    sha: str = ""


def _entradas_de(inventario: dict, produto: str) -> tuple[Entrada, ...]:
    # sorted() aqui e no resto do modulo: layout deve ser determinstico, e a
    # ordem do JSON nao e contrato.
    brutas = inventario.get(produto, [])
    achatadas = [
        Entrada(secao=e["secao"], chave=e["chave"], simbolo=e["simbolo"],
                arquivo=e["arquivo"], linha=e["linha"])
        for e in brutas
    ]
    return tuple(sorted(achatadas, key=lambda e: (e.secao, e.chave, e.arquivo)))


def carregar(raiz: Path, frescor: dict, nos: dict,
             arestas: list = (), vms: dict = None,
             fluxos: dict = None) -> Modelo:
    inventario = frescor.get("inventario", {})
    pasta_decisoes = Path(__file__).resolve().parent / "decisoes"

    construidos = []
    for chave in sorted(nos):
        bruto = nos[chave]
        if chave not in inventario:
            raise ReferenciaMorta(
                f"no '{chave}' nao existe no _frescor.json. "
                f"Produtos conhecidos: {', '.join(sorted(inventario))}"
            )
        decisoes = tuple(bruto.get("decisoes") or ())
        for d in decisoes:
            if not (pasta_decisoes / d).exists():
                raise ReferenciaMorta(
                    f"no '{chave}' cita a decisao '{d}', que nao existe em decisoes/"
                )
        construidos.append(No(
            chave=chave,
            titulo=bruto["titulo"],
            papel=bruto["papel"],
            vm=bruto.get("vm"),
            termo=bruto.get("termo"),
            decisoes=decisoes,
            spof=bool(bruto.get("spof")),
            spof_porque=bruto.get("spof_porque"),
            entradas=_entradas_de(inventario, chave),
        ))

    conhecidos = {n.chave for n in construidos}
    feitas = []
    for a in arestas or ():
        for ponta in ("de", "para"):
            if a[ponta] not in conhecidos:
                raise ReferenciaMorta(
                    f"aresta {a['de']} -> {a['para']} usa '{a[ponta]}', "
                    "que nao esta em NOS"
                )
        feitas.append(Aresta(
            de=a["de"], para=a["para"],
            protocolo=a.get("protocolo", "http"),
            sincrono=a.get("sincrono", True),
            retry=a.get("retry", False),
            inferida=a.get("inferida", False),
        ))
    feitas.sort(key=lambda a: (a.de, a.para, a.protocolo))

    maquinas = []
    for chave in sorted(vms or {}):
        b = (vms or {})[chave]
        for dentro in b.get("contem", ()):
            if dentro not in conhecidos:
                raise ReferenciaMorta(
                    f"vm '{chave}' contem '{dentro}', que nao esta em NOS"
                )
        maquinas.append(Vm(chave=chave, tipo=b.get("tipo", "fly-machine"),
                           contem=tuple(sorted(b.get("contem", ()))),
                           nota=b.get("nota", "")))

    caminhos = []
    for chave in sorted(fluxos or {}):
        b = (fluxos or {})[chave]
        passos = tuple(Passo(no=p["no"], faz=p["faz"],
                             protocolo=p.get("protocolo"),
                             sincrono=p.get("sincrono", True))
                       for p in b.get("passos", ()))
        caminhos.append(Fluxo(chave=chave, titulo=b["titulo"], passos=passos,
                              invariante=b.get("invariante")))

    return Modelo(nos=tuple(construidos), arestas=tuple(feitas),
                  vms=tuple(maquinas), fluxos=tuple(caminhos),
                  sha=frescor.get("sha", ""))
