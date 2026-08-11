"""Consultas de vendas do Copiloto.

Reusa ``calcular_metricas_vendas`` (fonte única dos totais do painel) para
que Copiloto e Visão Geral nunca discordem: se um disser 12 vendas e o outro
14, a confiança do dono acaba naquele instante e não volta.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import calcular_metricas_vendas
from app.loja.copiloto.periodo import Janela, janela_anterior, janela_do_periodo
from app.loja.copiloto.tipos import (
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)

CENTAVOS = Decimal("0.01")
DECIMO = Decimal("0.1")


def _c(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _pct(atual: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Variação percentual. ``None`` quando não há base — nunca -100% fake."""
    if atual is None or anterior is None or anterior == 0:
        return None
    return ((atual - anterior) / anterior * 100).quantize(
        DECIMO, rounding=ROUND_HALF_UP
    )


def _ticket(receita: Decimal, qtd: int) -> Decimal | None:
    return _c(receita / qtd) if qtd else None


def _dec(valor: Decimal | None) -> str | None:
    return None if valor is None else str(_c(valor))


@dataclass(frozen=True)
class VendasResumo:
    status: str
    janela: Janela
    janela_comparacao: Janela
    qtd_vendas: int
    receita: Decimal
    ticket_medio: Decimal | None
    margem: Decimal | None
    cobertura_margem: Cobertura
    qtd_vendas_anterior: int
    receita_anterior: Decimal
    ticket_medio_anterior: Decimal | None
    delta_qtd: int
    delta_receita_pct: Decimal | None
    delta_ticket_pct: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "periodo_comparacao": self.janela_comparacao.to_dict(),
            "qtd_vendas": self.qtd_vendas,
            "receita": _dec(self.receita),
            "ticket_medio": _dec(self.ticket_medio),
            "margem": _dec(self.margem),
            "cobertura_margem": self.cobertura_margem.to_dict(),
            "qtd_vendas_anterior": self.qtd_vendas_anterior,
            "receita_anterior": _dec(self.receita_anterior),
            "ticket_medio_anterior": _dec(self.ticket_medio_anterior),
            "delta_qtd": self.delta_qtd,
            "delta_receita_pct": (
                None if self.delta_receita_pct is None else str(self.delta_receita_pct)
            ),
            "delta_ticket_pct": (
                None if self.delta_ticket_pct is None else str(self.delta_ticket_pct)
            ),
        }


def vendas_resumo(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
) -> VendasResumo:
    """Receita, ticket médio, margem (com cobertura) e Δ vs período anterior."""
    janela = janela_do_periodo(inicio, fim)
    anterior = janela_anterior(janela)

    atual = calcular_metricas_vendas(db, ctx.loja_slug, janela.inicio, janela.fim)
    passado = calcular_metricas_vendas(db, ctx.loja_slug, anterior.inicio, anterior.fim)

    qtd = atual["quantidade"]
    receita = _c(atual["faturamento"])
    receita_ant = _c(passado["faturamento"])
    ticket = _ticket(receita, qtd)
    ticket_ant = _ticket(receita_ant, passado["quantidade"])

    cobertura = Cobertura(
        com_dado=qtd - atual["vendas_lucro_incompleto"],
        total=qtd,
    )
    # Sem nenhuma venda com custo conhecido não há número parcial para
    # mostrar — margem fica None (não é "parcial", é ausente).
    margem = (
        _c(atual["lucro_bruto"])
        if ctx.pode_ver_margem and cobertura.com_dado > 0
        else None
    )

    if qtd == 0:
        status = STATUS_VAZIO
    elif margem is not None and cobertura.parcial:
        status = STATUS_PARCIAL
    else:
        status = STATUS_OK

    return VendasResumo(
        status=status,
        janela=janela,
        janela_comparacao=anterior,
        qtd_vendas=qtd,
        receita=receita,
        ticket_medio=ticket,
        margem=margem,
        cobertura_margem=cobertura,
        qtd_vendas_anterior=passado["quantidade"],
        receita_anterior=receita_ant,
        ticket_medio_anterior=ticket_ant,
        delta_qtd=qtd - passado["quantidade"],
        delta_receita_pct=_pct(receita, receita_ant),
        delta_ticket_pct=_pct(ticket, ticket_ant),
    )
