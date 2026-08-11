"""Consultas de vendas do Copiloto.

Reusa ``calcular_metricas_vendas`` (fonte única dos totais do painel) para
que Copiloto e Visão Geral nunca discordem: se um disser 12 vendas e o outro
14, a confiança do dono acaba naquele instante e não volta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import _data, calcular_metricas_vendas
from app.loja.copiloto.periodo import Janela, janela_anterior, janela_do_periodo
from app.loja.copiloto.tipos import (
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)
from app.models import Venda

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


@dataclass(frozen=True)
class LinhaRanking:
    vendedor_email: str
    qtd: int
    receita: Decimal
    ticket_medio: Decimal | None
    posicao: int
    posicao_anterior: int | None
    variacao: str  # subiu | caiu | manteve | novo

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendedor_email": self.vendedor_email,
            "qtd": self.qtd,
            "receita": _dec(self.receita),
            "ticket_medio": _dec(self.ticket_medio),
            "posicao": self.posicao,
            "posicao_anterior": self.posicao_anterior,
            "variacao": self.variacao,
        }


@dataclass(frozen=True)
class RankingVendedores:
    status: str
    janela: Janela
    janela_comparacao: Janela
    linhas: tuple[LinhaRanking, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "periodo_comparacao": self.janela_comparacao.to_dict(),
            "linhas": [linha.to_dict() for linha in self.linhas],
        }


def _totais_por_vendedor(
    db: Session, loja_slug: str, janela: Janela
) -> dict[str, tuple[int, Decimal]]:
    """{email: (qtd, receita)} das vendas confirmadas da janela.

    O ``WHERE`` alarga a janela em 1 dia de cada lado porque o corte oficial do
    Portal é feito no fuso da loja (``financeiro_calc._data``), não em UTC.
    Alargar é barato; divergir do painel não é.
    """
    inicio_dt = datetime.combine(
        janela.inicio, datetime.min.time(), tzinfo=timezone.utc
    ) - timedelta(days=1)
    fim_dt = datetime.combine(
        janela.fim, datetime.max.time(), tzinfo=timezone.utc
    ) + timedelta(days=1)

    linhas = (
        db.query(Venda.vendedor_email, Venda.preco_venda, Venda.criada_em)
        .filter(
            Venda.loja_slug == loja_slug,
            Venda.status == "confirmada",
            Venda.criada_em >= inicio_dt,
            Venda.criada_em <= fim_dt,
        )
        .all()
    )

    totais: dict[str, tuple[int, Decimal]] = {}
    for email, preco, criada_em in linhas:
        if not (janela.inicio <= _data(criada_em) <= janela.fim):
            continue
        chave = (email or "").strip().casefold()
        qtd, receita = totais.get(chave, (0, Decimal("0")))
        totais[chave] = (qtd + 1, receita + preco)
    return totais


def _posicoes(totais: dict[str, tuple[int, Decimal]]) -> dict[str, int]:
    ordenado = sorted(
        totais.items(), key=lambda item: (-item[1][1], -item[1][0], item[0])
    )
    return {email: i + 1 for i, (email, _) in enumerate(ordenado)}


def ranking_vendedores(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
    limite: int = 10,
) -> RankingVendedores:
    """Vendedores ordenados por receita, com quem subiu e quem caiu."""
    janela = janela_do_periodo(inicio, fim)
    anterior = janela_anterior(janela)

    atual = _totais_por_vendedor(db, ctx.loja_slug, janela)
    passado = _totais_por_vendedor(db, ctx.loja_slug, anterior)

    if not atual:
        return RankingVendedores(
            status=STATUS_VAZIO,
            janela=janela,
            janela_comparacao=anterior,
            linhas=(),
        )

    pos_atual = _posicoes(atual)
    pos_anterior = _posicoes(passado)

    linhas: list[LinhaRanking] = []
    for email, posicao in sorted(pos_atual.items(), key=lambda item: item[1]):
        if posicao > max(1, limite):
            break
        qtd, receita = atual[email]
        antiga = pos_anterior.get(email)
        if antiga is None:
            variacao = "novo"
        elif posicao < antiga:
            variacao = "subiu"
        elif posicao > antiga:
            variacao = "caiu"
        else:
            variacao = "manteve"
        linhas.append(
            LinhaRanking(
                vendedor_email=email,
                qtd=qtd,
                receita=_c(receita),
                ticket_medio=_ticket(_c(receita), qtd),
                posicao=posicao,
                posicao_anterior=antiga,
                variacao=variacao,
            )
        )

    return RankingVendedores(
        status=STATUS_OK,
        janela=janela,
        janela_comparacao=anterior,
        linhas=tuple(linhas),
    )
