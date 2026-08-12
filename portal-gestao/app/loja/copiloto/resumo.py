"""Resumo de hoje — determinístico, sem LLM.

É o caminho mais usado da seção. Tirar o modelo daqui zera alucinação no lugar
de maior tráfego, mantém o botão de pé quando o provedor de IA cai e não gasta
token nenhum.

Os chips de sugestão saem do dado real ("3 motos paradas +60d"), não de uma
lista fixa — resolvem o chat em branco de graça.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.loja.copiloto.cache import cache_overview, chave_overview
from app.loja.copiloto.consultas_estoque import estoque_parado
from app.loja.copiloto.consultas_leads import LeadsStatus, leads_status
from app.loja.copiloto.consultas_origem import venda_origem_ultima
from app.loja.copiloto.consultas_vendas import ranking_vendedores, vendas_resumo
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.tipos import CopilotoContexto

DIAS_PARADO_RESUMO = 60
TOP_RANKING = 3


@dataclass(frozen=True)
class Chip:
    """Sugestão viva: o texto é o que aparece, a pergunta é o que vai ao chat."""

    texto: str
    pergunta: str

    def to_dict(self) -> dict[str, str]:
        return {"texto": self.texto, "pergunta": self.pergunta}


@dataclass(frozen=True)
class ResumoHoje:
    gerado_em: str
    janela: Janela
    vendas: Any
    ranking: Any
    origem_ultima: Any
    parado: Any
    leads: LeadsStatus | None
    chips: tuple[Chip, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gerado_em": self.gerado_em,
            "periodo": self.janela.to_dict(),
            "vendas": self.vendas.to_dict(),
            "ranking": self.ranking.to_dict(),
            "origem_ultima": self.origem_ultima.to_dict(),
            "estoque_parado": self.parado.to_dict(),
            "leads": self.leads.to_dict() if self.leads else None,
            "chips": [c.to_dict() for c in self.chips],
        }


def _overview_cacheado(db: Session, ctx: CopilotoContexto, chatbot: Any):
    """Fan-out caro atrás do cache TTL (§3.5)."""
    from app.loja.sales_overview import build_sales_overview

    chave = chave_overview(ctx.loja_slug, ctx.papel, None, None)

    def _produzir():
        try:
            return build_sales_overview(
                db, loja_slug=ctx.loja_slug, papel=ctx.papel, chatbot=chatbot
            )
        except Exception:
            return None

    return cache_overview.obter(chave, _produzir)


def _chips(vendas: Any, parado: Any, leads: LeadsStatus | None) -> tuple[Chip, ...]:
    chips: list[Chip] = []

    if vendas.qtd_vendas:
        chips.append(
            Chip(
                texto="De onde veio a última venda",
                pergunta="De onde veio a última venda que eu fiz?",
            )
        )
    if getattr(parado, "total", None):
        n = parado.total
        chips.append(
            Chip(
                texto=f"{n} parada{'s' if n != 1 else ''} +{parado.dias_min}d",
                pergunta=(
                    f"Quais veículos estão parados há mais de {parado.dias_min} dias "
                    "e quanto de capital está preso neles?"
                ),
            )
        )
    if leads is not None and leads.sem_resposta:
        chips.append(
            Chip(
                texto=f"{leads.sem_resposta} sem resposta",
                pergunta="Quantos leads ninguém respondeu e há quanto tempo?",
            )
        )
    if vendas.cobertura_margem.parcial:
        faltam = vendas.cobertura_margem.total - vendas.cobertura_margem.com_dado
        chips.append(
            Chip(
                texto=f"{faltam} venda(s) sem custo",
                pergunta="Quais vendas estão sem custo informado?",
            )
        )

    # Base: a tela nunca fica sem sugestão, mesmo em loja recém-criada.
    chips.append(
        Chip(texto="Resultado do mês", pergunta="Como foi meu mês vs. o mês passado?")
    )
    return tuple(chips[:5])


def montar_resumo_hoje(
    db: Session,
    ctx: CopilotoContexto,
    *,
    estoque: Any,
    chatbot: Any,
    agora: datetime | None = None,
) -> ResumoHoje:
    """Conjunto fixo de leituras + view-model. Nenhuma chamada de LLM."""
    ref = agora or datetime.now(timezone.utc)
    janela = janela_do_periodo(None, None)

    vendas = vendas_resumo(db, ctx)
    ranking = ranking_vendedores(db, ctx, limite=TOP_RANKING)
    origem = venda_origem_ultima(db, ctx)
    parado = estoque_parado(estoque, ctx, dias_min=DIAS_PARADO_RESUMO, agora=ref)

    overview = _overview_cacheado(db, ctx, chatbot)
    leads = (
        leads_status(overview, chatbot, ctx=ctx, agora=ref)
        if overview is not None
        else None
    )

    return ResumoHoje(
        gerado_em=ref.isoformat(),
        janela=janela,
        vendas=vendas,
        ranking=ranking,
        origem_ultima=origem,
        parado=parado,
        leads=leads,
        chips=_chips(vendas, parado, leads),
    )
