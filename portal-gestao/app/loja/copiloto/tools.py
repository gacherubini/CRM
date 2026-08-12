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

from app.loja.copiloto.acoes import ACOES_PERMITIDAS
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


def _overview(r: RecursosTools, *, inicio: str | None = None, fim: str | None = None):
    from app.loja.sales_overview import build_sales_overview

    def _produzir():
        try:
            return build_sales_overview(
                r.db,
                loja_slug=r.ctx.loja_slug,
                papel=r.ctx.papel,
                chatbot=r.chatbot,
                inicio=inicio,
                fim=fim,
            )
        except Exception:
            return None

    return cache_overview.obter(
        chave_overview(r.ctx.loja_slug, r.ctx.papel, inicio, fim), _produzir
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
    from app.loja.sales_overview import _serializar_linhas_midia

    overview = _overview(
        r, inicio=_texto(argumentos, "inicio"), fim=_texto(argumentos, "fim")
    )
    if overview is None or overview.aquisicao is None:
        return {"status": "indisponivel", "campanhas": [], "canais": []}
    campanhas = _serializar_linhas_midia(overview.aquisicao_campanhas)
    canais = _serializar_linhas_midia(overview.aquisicao_canais)
    return {
        "status": overview.aquisicao_status,
        "totais": overview.aquisicao.to_dict(),
        "campanhas": campanhas,
        "canais": canais,
        "detalhe_disponivel": bool(campanhas or canais),
    }


def _f_consultar_fipe(argumentos: dict, r: RecursosTools) -> dict:
    """FIPE do veículo. O modelo escolhe QUAL veículo, não o texto da busca.

    Marca, modelo, ano e tipo vêm do Estoque — o LLM não redigita nada.
    """
    from app.clients.fipe import FipeClient
    from app.config import settings
    from app.loja.copiloto.fipe import consultar_fipe_do_veiculo

    client = FipeClient(
        settings.copiloto_fipe_url, timeout=settings.copiloto_fipe_timeout
    )
    return consultar_fipe_do_veiculo(
        client,
        r.estoque,
        r.ctx,
        veiculo_id=_texto(argumentos, "veiculo_id") or "",
        fipe_codigo=_texto(argumentos, "fipe_codigo"),
    ).to_dict()


def _f_propor_acao(argumentos: dict, r: RecursosTools) -> dict:
    """Monta o CARTÃO. Não executa nada — quem executa é o clique humano."""
    from app.loja.copiloto.acoes import AcaoRecusada
    from app.loja.copiloto.cartao import montar_cartao

    acao = str(argumentos.get("acao") or "").strip()
    # Nenhuma proposta de preço a partir de FIPE não confirmada (§4.5).
    if acao == "ajustar_preco":
        fipe_status = str(argumentos.get("fipe_status") or "").strip()
        justificativa = str(argumentos.get("justificativa") or "").strip()
        if fipe_status != "ok" and justificativa not in {"dias_parado", "pedido_do_dono"}:
            return {
                "status": "recusado",
                "motivo_code": "fipe_nao_confirmada",
                "motivo": (
                    "Não posso propor preço sem a FIPE confirmada. Pergunte qual "
                    "modelo é o certo, ou justifique pelo tempo parado."
                ),
            }
    try:
        cartao = montar_cartao(r.estoque, r.ctx, acao=acao, parametros=argumentos)
    except AcaoRecusada as exc:
        return {"status": "recusado", "motivo_code": exc.code, "motivo": str(exc)}
    return {"status": "cartao", "cartao": cartao.to_dict()}


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
        Ferramenta(
            nome="consultar_fipe",
            descricao=(
                "Valor de referência FIPE de um veículo DO ESTOQUE, pelo id. "
                "Marca, modelo e ano são lidos do cadastro — não os informe. "
                "Se voltar status 'ambiguo', PERGUNTE ao usuário qual dos "
                "modelos é o certo e chame de novo com o fipe_codigo que ele "
                "escolheu — nunca escolha por ele. Se voltar 'nao_encontrado', "
                "diga que não achou na FIPE."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "veiculo_id": {
                        "type": "string",
                        "description": "Id do veículo no estoque (veio de estoque_parado).",
                    },
                    "fipe_codigo": {
                        "type": "string",
                        "description": (
                            "Só quando o usuário já escolheu entre candidatos "
                            "de uma consulta 'ambiguo' anterior."
                        ),
                    },
                },
                "required": ["veiculo_id"],
            },
            executar=_f_consultar_fipe,
            esforco_sugerido="high",
        ),
        Ferramenta(
            nome="propor_acao",
            descricao=(
                "Monta o cartão de confirmação de uma ação. NÃO executa nada: "
                "quem confirma é o usuário, com um clique. Use depois de ter o "
                "dado que justifica a ação."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        # Derivado da whitelist, nunca escrito à mão: duas
                        # listas mantidas separadas divergem cedo ou tarde —
                        # ACOES_PERMITIDAS é a fonte da verdade, e o enum
                        # aqui é só a projeção dela para o modelo.
                        "enum": sorted(ACOES_PERMITIDAS),
                    },
                    "veiculo_id": {"type": "string"},
                    "novo_preco": {"type": "string"},
                    "fipe_status": {
                        "type": "string",
                        "description": "Status devolvido por consultar_fipe, se usou.",
                    },
                    "justificativa": {
                        "type": "string",
                        "enum": ["dias_parado", "pedido_do_dono"],
                    },
                },
                "required": ["acao", "veiculo_id"],
            },
            executar=_f_propor_acao,
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
