"""Funde arquitetura.py + _frescor.json + decisoes/ num Modelo. Stdlib apenas.

Nao importa `app` de produto nenhum (AGENTS.md secao 5).

O modelo e RECURSIVO: um `No` pode ter `filhos`, sem profundidade fixa (dict
`dentro` no dict cru). So a RAIZ de NOS e cobrada contra o `_frescor.json` —
e la que moram os nomes de produto. Sub-no e estrutura de dominio (um canal
por loja, um worker, um modulo), nao produto, entao nao teria como existir
no frescor. A validacao de `decisoes/` vale em qualquer profundidade.
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
    modulo: str | None = None
    decisoes: tuple[str, ...] = ()
    spof: bool = False
    spof_porque: str | None = None
    entradas: tuple[Entrada, ...] = ()
    filhos: tuple["No", ...] = ()


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


def _entradas_de(inventario: dict, produto: str) -> list[Entrada]:
    # sorted() aqui e no resto do modulo: layout deve ser determinstico, e a
    # ordem do JSON nao e contrato.
    brutas = inventario.get(produto, [])
    achatadas = [
        Entrada(secao=e["secao"], chave=e["chave"], simbolo=e["simbolo"],
                arquivo=e["arquivo"], linha=e["linha"])
        for e in brutas
    ]
    return sorted(achatadas, key=lambda e: (e.secao, e.chave, e.arquivo))


def _coletar_modulos(bruto: dict, caminho: tuple) -> list:
    """Lista `(modulo, caminho_do_no)` pra todo no do bruto que declara
    `modulo`, em qualquer profundidade. `caminho` vazio = a raiz do produto.

    Um no sem `modulo` (grupo de dominio, tipo "canais" ou "workers") nao
    entra aqui — mas isso NAO bloqueia os filhos dele, que sao percorridos
    do mesmo jeito. E assim que um sub-no sem modulo proprio deixa passar
    a competicao ate os netos.
    """
    resultado = []
    modulo = bruto.get("modulo")
    if modulo:
        resultado.append((modulo, caminho))
    dentro = bruto.get("dentro") or {}
    for subchave in dentro:
        resultado.extend(_coletar_modulos(dentro[subchave], caminho + (subchave,)))
    return resultado


def _designar_por_caminho(pool: list[Entrada], bruto_raiz: dict) -> dict:
    """Devolve `{caminho_do_no: [Entrada, ...]}` pra uma arvore inteira.

    Prefixo mais especifico (mais longo) ganha — e assim que
    `app/control/google_ads` (o sub-no) fica com a entrada em vez de
    `app/control/` (o pai dele) quando os dois casam o mesmo arquivo.
    Nada casando: fica na raiz (`caminho == ()`), nunca preso num
    intermediario sem `modulo`. `sorted()` no desempate por tamanho garante
    ordem deterministica mesmo com dois `modulo` do mesmo tamanho.
    """
    candidatos = sorted(
        _coletar_modulos(bruto_raiz, ()),
        key=lambda mc: (-len(mc[0]), mc[1]),
    )
    designacao: dict = {(): []}
    for e in pool:
        alvo = ()
        for modulo, caminho in candidatos:
            if e.arquivo.startswith(modulo):
                alvo = caminho
                break
        designacao.setdefault(alvo, []).append(e)
    return designacao


def _construir_no(chave: str, bruto: dict, caminho: tuple, designacao: dict,
                   pasta_decisoes: Path) -> No:
    decisoes = tuple(bruto.get("decisoes") or ())
    for d in decisoes:
        if not (pasta_decisoes / d).exists():
            raise ReferenciaMorta(
                f"no '{chave}' cita a decisao '{d}', que nao existe em decisoes/"
            )

    dentro = bruto.get("dentro") or {}
    filhos = tuple(
        _construir_no(subchave, dentro[subchave], caminho + (subchave,),
                      designacao, pasta_decisoes)
        for subchave in sorted(dentro)
    )
    entradas_aqui = tuple(sorted(
        designacao.get(caminho, []),
        key=lambda e: (e.secao, e.chave, e.arquivo),
    ))

    return No(
        chave=chave,
        titulo=bruto["titulo"],
        papel=bruto["papel"],
        vm=bruto.get("vm"),
        termo=bruto.get("termo"),
        modulo=bruto.get("modulo"),
        decisoes=decisoes,
        spof=bool(bruto.get("spof")),
        spof_porque=bruto.get("spof_porque"),
        entradas=entradas_aqui,
        filhos=filhos,
    )


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
        pool = _entradas_de(inventario, chave)
        designacao = _designar_por_caminho(pool, bruto)
        construidos.append(_construir_no(chave, bruto, (), designacao, pasta_decisoes))

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
