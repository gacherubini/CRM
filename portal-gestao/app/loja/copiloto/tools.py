"""Registro de ferramentas — o "schema" que o modelo enxerga.

MCP-nativo desde a v1: tool interna e servidor MCP externo plugam pela mesma
interface, então acrescentar fonte (FIPE, Meta insights) vira configuração e
não reescrita do runner.

INVARIANTE: nenhum schema expõe identidade (loja_slug, papel, e-mail). O
modelo escolhe QUAL função e QUAIS parâmetros de negócio; quem é o ator vem
do ``RecursosTools.ctx``, montado da sessão autenticada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.loja.copiloto.cache import cache_overview, chave_overview
from app.loja.copiloto.consultas_estoque import estoque_parado
from app.loja.copiloto.consultas_leads import leads_status
from app.loja.copiloto.consultas_origem import (
    venda_origem_periodo,
    venda_origem_ultima,
)
from app.loja.copiloto.consultas_vendas import ranking_vendedores, vendas_resumo
from app.loja.copiloto.port import EsforcoLLM
from app.loja.copiloto.tipos import CopilotoContexto


class FerramentaDesconhecida(RuntimeError):
    """O modelo chamou algo que não está no registro. Recusar."""


@dataclass(frozen=True)
class RecursosTools:
    """O que a ferramenta recebe — e o modelo nunca vê."""

    db: Session
    estoque: Any
    chatbot: Any
    ctx: CopilotoContexto
    agora: datetime | None = None


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any]
    executar: Callable[[dict[str, Any], RecursosTools], dict[str, Any]]
    esforco_sugerido: EsforcoLLM = "low"


def _int(argumentos: dict, chave: str, padrao: int) -> int:
    try:
        return int(argumentos.get(chave, padrao))
    except (TypeError, ValueError):
        return padrao


def _texto(argumentos: dict, chave: str) -> str | None:
    valor = argumentos.get(chave)
    return str(valor).strip() if valor not in (None, "") else None


_PERIODO = {
    "inicio": {
        "type": "string",
        "description": "Data inicial ISO (AAAA-MM-DD). Omitido = mês corrente.",
    },
    "fim": {
        "type": "string",
        "description": "Data final ISO (AAAA-MM-DD). Omitido = mês corrente.",
    },
}


def _f_vendas_resumo(argumentos: dict, r: RecursosTools) -> dict:
    return vendas_resumo(
        r.db, r.ctx, inicio=_texto(argumentos, "inicio"), fim=_texto(argumentos, "fim")
    ).to_dict()


def _f_ranking(argumentos: dict, r: RecursosTools) -> dict:
    return ranking_vendedores(
        r.db,
        r.ctx,
        inicio=_texto(argumentos, "inicio"),
        fim=_texto(argumentos, "fim"),
        limite=_int(argumentos, "limite", 10),
    ).to_dict()


def _f_venda_origem(argumentos: dict, r: RecursosTools) -> dict:
    if (argumentos.get("escopo") or "ultima") == "periodo":
        return venda_origem_periodo(
            r.db, r.ctx, inicio=_texto(argumentos, "inicio"),
            fim=_texto(argumentos, "fim"),
        ).to_dict()
    return venda_origem_ultima(r.db, r.ctx).to_dict()


def _f_estoque_parado(argumentos: dict, r: RecursosTools) -> dict:
    return estoque_parado(
        r.estoque,
        r.ctx,
        dias_min=_int(argumentos, "dias_min", 30),
        limite=_int(argumentos, "limite", 20),
        agora=r.agora,
    ).to_dict()


def _overview(r: RecursosTools):
    from app.loja.sales_overview import build_sales_overview

    def _produzir():
        try:
            return build_sales_overview(
                r.db, loja_slug=r.ctx.loja_slug, papel=r.ctx.papel, chatbot=r.chatbot
            )
        except Exception:
            return None

    return cache_overview.obter(
        chave_overview(r.ctx.loja_slug, r.ctx.papel, None, None), _produzir
    )


def _f_leads_status(argumentos: dict, r: RecursosTools) -> dict:
    overview = _overview(r)
    if overview is None:
        return {"status": "indisponivel", "mensagem": "funil indisponível agora"}
    return leads_status(
        overview,
        r.chatbot,
        ctx=r.ctx,
        agora=r.agora,
        horas_sem_resposta=_int(argumentos, "horas", 4),
    ).to_dict()


def _f_roi_canais(argumentos: dict, r: RecursosTools) -> dict:
    """Totais de aquisição + quebra por canal/campanha QUANDO houver.

    A quebra só existe se a API do Revy Tráfego responder
    (``sales_overview.py:635``); o fallback local devolve listas vazias de
    propósito (``:697-708``). Esta é a ferramenta frágil da v1 — e ela diz
    isso em vez de fingir zero.
    """
    overview = _overview(r)
    if overview is None or overview.aquisicao is None:
        return {"status": "indisponivel", "campanhas": [], "canais": []}
    return {
        "status": overview.aquisicao_status,
        "totais": overview.aquisicao.to_dict(),
        "campanhas": overview.aquisicao_campanhas,
        "canais": overview.aquisicao_canais,
        "detalhe_disponivel": bool(
            overview.aquisicao_campanhas or overview.aquisicao_canais
        ),
    }


def registro_padrao() -> tuple[Ferramenta, ...]:
    return (
        Ferramenta(
            nome="vendas_resumo",
            descricao=(
                "Receita, ticket médio, margem e número de vendas confirmadas do "
                "período, com comparação ao período anterior. Use para 'quanto "
                "vendi', 'como foi o mês', 'meu ticket'."
            ),
            parametros={"type": "object", "properties": dict(_PERIODO)},
            executar=_f_vendas_resumo,
        ),
        Ferramenta(
            nome="ranking_vendedores",
            descricao=(
                "Vendedores ordenados por receita no período, com quem subiu e "
                "quem caiu em relação ao período anterior."
            ),
            parametros={
                "type": "object",
                "properties": {
                    **_PERIODO,
                    "limite": {"type": "integer", "description": "Quantos vendedores (padrão 10)."},
                },
            },
            executar=_f_ranking,
        ),
        Ferramenta(
            nome="venda_origem",
            descricao=(
                "De qual campanha/anúncio veio a venda. escopo='ultima' devolve a "
                "última venda confirmada; escopo='periodo' devolve todas as do "
                "período com a cobertura da atribuição."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "escopo": {
                        "type": "string",
                        "enum": ["ultima", "periodo"],
                        "description": "Padrão: ultima.",
                    },
                    **_PERIODO,
                },
            },
            executar=_f_venda_origem,
        ),
        Ferramenta(
            nome="estoque_parado",
            descricao=(
                "Veículos parados além de N dias, com dias parados e capital "
                "preso somado. A idade conta a partir do cadastro no sistema."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "dias_min": {"type": "integer", "description": "Limiar em dias (padrão 30)."},
                    "limite": {"type": "integer", "description": "Máximo de veículos listados."},
                },
            },
            executar=_f_estoque_parado,
        ),
        Ferramenta(
            nome="leads_status",
            descricao=(
                "Leads do período, taxa de resposta, tempo mediano de primeira "
                "resposta e quantos estão sem resposta humana há N horas."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "horas": {"type": "integer", "description": "Limiar de espera (padrão 4)."}
                },
            },
            executar=_f_leads_status,
        ),
        Ferramenta(
            nome="roi_canais",
            descricao=(
                "Investimento, CAC e ROAS de aquisição. A quebra por campanha/"
                "canal só existe quando a fonte de mídia responde; caso "
                "contrário vem vazia e isso deve ser dito."
            ),
            parametros={"type": "object", "properties": dict(_PERIODO)},
            executar=_f_roi_canais,
            esforco_sugerido="high",
        ),
    )


def schemas(ferramentas: tuple[Ferramenta, ...]) -> list[dict[str, Any]]:
    return [
        {"name": f.nome, "description": f.descricao, "parameters": f.parametros}
        for f in ferramentas
    ]


def despachar(
    nome: str,
    argumentos: dict[str, Any],
    recursos: RecursosTools,
    *,
    ferramentas: tuple[Ferramenta, ...] | None = None,
) -> dict[str, Any]:
    registro = ferramentas or registro_padrao()
    for ferramenta in registro:
        if ferramenta.nome == nome:
            return ferramenta.executar(argumentos or {}, recursos)
    raise FerramentaDesconhecida(f"ferramenta desconhecida: {nome}")
