"""Matching FIPE. NUNCA adivinha.

O maior risco silencioso da v1: a FIPE exige código de marca/modelo/ano e o
estoque guarda texto livre. Errar o modelo aqui vira conselho de preço errado
— e esse conselho vira uma ação que o dono confirma com um clique.

Três regras duras:
1. zero candidatos → nao_encontrado (jamais aproximar);
2. mais de um → ambiguo + lista, e QUEM ESCOLHE É O HUMANO;
3. só match exato normalizado vira ok.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.clients.estoque import EstoqueIndisponivel, VeiculoNaoEncontrado
from app.clients.fipe import FipeIndisponivel
from app.config import settings
from app.loja.copiloto.cache import CacheTTL
from app.loja.copiloto.consultas_estoque import (
    EscopoLojaDivergente,
    garantir_escopo_loja,
)
from app.loja.copiloto.tipos import CopilotoContexto

STATUS_OK = "ok"
STATUS_AMBIGUO = "ambiguo"
STATUS_NAO_ENCONTRADO = "nao_encontrado"
STATUS_INDISPONIVEL = "indisponivel"

LIMITE_CANDIDATOS = 8

# Marca e modelo mudam uma vez por mês; o /valor nunca é cacheado.
# Se o produtor levantar, o CacheTTL não grava nada — falha não polui cache.
cache_fipe = CacheTTL(ttl_segundos=settings.copiloto_fipe_cache_segundos)

# O estoque diz "moto"/"carro"; a FIPE espera "motos"/"carros"/"caminhoes".
TIPOS_FIPE = {
    "moto": "motos",
    "motos": "motos",
    "carro": "carros",
    "carros": "carros",
    "caminhao": "caminhoes",
    "caminhoes": "caminhoes",
}


def _tipo_fipe(tipo_estoque: str | None) -> str:
    """Traduz o vocabulário do Estoque. Desconhecido cai em motos (moto-first)."""
    return TIPOS_FIPE.get(normalizar(tipo_estoque or ""), "motos")


def _marcas_cacheadas(client: Any, tipo: str) -> list[dict]:
    return cache_fipe.obter(f"fipe:marcas:{tipo}", lambda: client.marcas(tipo))


def _modelos_cacheados(client: Any, tipo: str, marca_codigo: str) -> list[dict]:
    return cache_fipe.obter(
        f"fipe:modelos:{tipo}:{marca_codigo}",
        lambda: client.modelos(tipo, marca_codigo),
    )


def normalizar(texto: str) -> str:
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn"
    )
    limpo = re.sub(r"[^\w\s]", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", limpo).strip()


@dataclass(frozen=True)
class CandidatoFipe:
    marca_codigo: str
    marca_nome: str
    modelo_codigo: str
    modelo_nome: str
    ano_codigo: str | None = None
    ano_nome: str | None = None

    @property
    def fipe_codigo(self) -> str:
        return f"{self.marca_codigo}/{self.modelo_codigo}/{self.ano_codigo or ''}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fipe_codigo": self.fipe_codigo,
            "marca": self.marca_nome,
            "modelo": self.modelo_nome,
            "ano": self.ano_nome,
        }


@dataclass(frozen=True)
class ResultadoFipe:
    status: str
    valor: str | None = None
    referencia: str | None = None
    candidatos: tuple[CandidatoFipe, ...] = ()
    mensagem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "valor": self.valor,
            "referencia": self.referencia,
            "candidatos": [c.to_dict() for c in self.candidatos],
            "mensagem": self.mensagem,
        }


def _achar_marca(marcas: list[dict], termo: str) -> dict | None:
    alvo = normalizar(termo)
    for marca in marcas:
        if normalizar(marca.get("nome")) == alvo:
            return marca
    return None


def _candidatos_de_modelo(modelos: list[dict], termo: str) -> list[dict]:
    alvo = normalizar(termo)
    exatos = [m for m in modelos if normalizar(m.get("nome")) == alvo]
    if exatos:
        return exatos
    # Sem exato: devolve os que CONTÊM o termo — como candidatos, não escolha.
    return [m for m in modelos if alvo and alvo in normalizar(m.get("nome"))]


def _ano_compativel(anos: list[dict], ano: int | None) -> dict | None:
    if not anos:
        return None
    if ano is None:
        return anos[0]
    for item in anos:
        if str(ano) in str(item.get("nome") or "") or str(ano) in str(
            item.get("codigo") or ""
        ):
            return item
    return None


def consultar_fipe(
    client: Any,
    *,
    tipo: str = "motos",
    marca: str = "",
    modelo: str = "",
    ano: int | None = None,
    fipe_codigo: str | None = None,
) -> ResultadoFipe:
    try:
        # Caminho determinístico: código salvo no veículo dispensa matching.
        if fipe_codigo:
            partes = [p for p in str(fipe_codigo).split("/") if p]
            if len(partes) != 3:
                return ResultadoFipe(
                    status=STATUS_NAO_ENCONTRADO, mensagem="código FIPE inválido"
                )
            bruto = client.valor(tipo, partes[0], partes[1], partes[2])
            return ResultadoFipe(
                status=STATUS_OK,
                valor=bruto.get("Valor"),
                referencia=bruto.get("MesReferencia"),
            )

        marcas = _marcas_cacheadas(client, tipo)
        achada = _achar_marca(marcas, marca)
        if achada is None:
            return ResultadoFipe(
                status=STATUS_NAO_ENCONTRADO,
                mensagem=f"não encontrei a marca {marca} na FIPE",
            )

        modelos = _modelos_cacheados(client, tipo, achada["codigo"])
        candidatos_modelo = _candidatos_de_modelo(modelos, modelo)
        if not candidatos_modelo:
            return ResultadoFipe(
                status=STATUS_NAO_ENCONTRADO,
                mensagem=f"não encontrei {marca} {modelo} na FIPE",
            )
        if len(candidatos_modelo) > 1:
            return ResultadoFipe(
                status=STATUS_AMBIGUO,
                candidatos=tuple(
                    CandidatoFipe(
                        marca_codigo=str(achada["codigo"]),
                        marca_nome=str(achada["nome"]),
                        modelo_codigo=str(m["codigo"]),
                        modelo_nome=str(m["nome"]),
                    )
                    for m in candidatos_modelo[:LIMITE_CANDIDATOS]
                ),
                mensagem="mais de um modelo bate com essa descrição",
            )

        escolhido = candidatos_modelo[0]
        anos = client.anos(tipo, achada["codigo"], escolhido["codigo"])
        ano_item = _ano_compativel(anos, ano)
        if ano_item is None:
            return ResultadoFipe(
                status=STATUS_NAO_ENCONTRADO,
                mensagem=f"a FIPE não tem o ano {ano} para esse modelo",
            )

        bruto = client.valor(
            tipo, achada["codigo"], escolhido["codigo"], ano_item["codigo"]
        )
        return ResultadoFipe(
            status=STATUS_OK,
            valor=bruto.get("Valor"),
            referencia=bruto.get("MesReferencia"),
            candidatos=(
                CandidatoFipe(
                    marca_codigo=str(achada["codigo"]),
                    marca_nome=str(achada["nome"]),
                    modelo_codigo=str(escolhido["codigo"]),
                    modelo_nome=str(escolhido["nome"]),
                    ano_codigo=str(ano_item["codigo"]),
                    ano_nome=str(ano_item["nome"]),
                ),
            ),
        )
    except FipeIndisponivel as exc:
        return ResultadoFipe(status=STATUS_INDISPONIVEL, mensagem=str(exc))


def _ano_do_veiculo(veiculo: dict) -> int | None:
    for campo in ("ano_modelo", "ano"):
        try:
            valor = int(veiculo.get(campo))
        except (TypeError, ValueError):
            continue
        if 1900 < valor < 2200:
            return valor
    return None


def consultar_fipe_do_veiculo(
    client: Any,
    estoque: Any,
    ctx: CopilotoContexto,
    *,
    veiculo_id: str,
    fipe_codigo: str | None = None,
) -> ResultadoFipe:
    """Consulta a FIPE de um veículo do estoque da loja.

    É esta que o Copiloto usa. O modelo escolhe QUAL veículo; marca, modelo,
    ano e tipo vêm da fonte, não do texto que ele digitou — isso tira a maior
    superfície de erro do caminho e impede consultar a FIPE de um veículo que
    não é o da conversa.

    ``fipe_codigo`` explícito (escolhido pelo humano depois de um 'ambiguo')
    vence o que estiver salvo no veículo.
    """
    if not (veiculo_id or "").strip():
        return ResultadoFipe(
            status=STATUS_NAO_ENCONTRADO, mensagem="veículo não informado"
        )

    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
        veiculo = estoque.obter(veiculo_id)
    except EscopoLojaDivergente:
        # Falha fechado como "não encontrado": não confirma que o veículo
        # existe em outra loja.
        return ResultadoFipe(
            status=STATUS_NAO_ENCONTRADO, mensagem="veículo não encontrado"
        )
    except VeiculoNaoEncontrado:
        return ResultadoFipe(
            status=STATUS_NAO_ENCONTRADO, mensagem="veículo não encontrado"
        )
    except EstoqueIndisponivel:
        return ResultadoFipe(
            status=STATUS_INDISPONIVEL, mensagem="estoque indisponível agora"
        )

    marca = str(veiculo.get("marca") or "").strip()
    modelo = str(veiculo.get("modelo") or "").strip()
    if not marca or not modelo:
        return ResultadoFipe(
            status=STATUS_NAO_ENCONTRADO,
            mensagem="o cadastro deste veículo está sem marca ou modelo",
        )

    return consultar_fipe(
        client,
        tipo=_tipo_fipe(veiculo.get("tipo")),
        marca=marca,
        modelo=modelo,
        ano=_ano_do_veiculo(veiculo),
        fipe_codigo=(fipe_codigo or veiculo.get("fipe_codigo") or None),
    )
