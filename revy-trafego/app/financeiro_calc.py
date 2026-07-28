"""Helpers de data/período e lucro (subset do portal para ROI)."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Venda

CENTAVOS = Decimal("0.01")
FUSO_PORTAL = ZoneInfo(settings.timezone)


def _data(momento):
    if not isinstance(momento, datetime):
        return momento
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_PORTAL).date()


def hoje_portal() -> date:
    return datetime.now(timezone.utc).astimezone(FUSO_PORTAL).date()


def ultimo_dia_mes(dia: date) -> date:
    return date(dia.year, dia.month, calendar.monthrange(dia.year, dia.month)[1])


def periodo_padrao(inicio: str | None, fim: str | None) -> tuple[date, date]:
    hoje = hoje_portal()
    try:
        d_inicio = date.fromisoformat(inicio) if inicio else hoje.replace(day=1)
    except ValueError:
        d_inicio = hoje.replace(day=1)
    try:
        d_fim = date.fromisoformat(fim) if fim else ultimo_dia_mes(hoje)
    except ValueError:
        d_fim = ultimo_dia_mes(hoje)
    return d_inicio, d_fim


def lucro_bruto_venda(venda: Venda) -> Decimal | None:
    if venda.custo_veiculo is None:
        return None
    custo = venda.custo_veiculo
    diretos = sum((c.valor for c in venda.custos_diretos), Decimal("0"))
    return (venda.preco_venda - custo - diretos).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_metricas_vendas(db: Session, loja_slug: str, d_inicio: date, d_fim: date) -> dict:
    confirmadas = [
        v
        for v in db.query(Venda)
        .filter(Venda.loja_slug == loja_slug, Venda.status == "confirmada")
        .all()
        if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    faturamento = sum((v.preco_venda for v in confirmadas), Decimal("0"))
    lucros_conhecidos = [
        valor for venda in confirmadas if (valor := lucro_bruto_venda(venda)) is not None
    ]
    lucro = sum(lucros_conhecidos, Decimal("0"))
    vendas_lucro_incompleto = len(confirmadas) - len(lucros_conhecidos)
    return {
        "confirmadas": confirmadas,
        "quantidade": len(confirmadas),
        "faturamento": faturamento,
        "lucro_bruto": lucro,
        "lucro_completo": vendas_lucro_incompleto == 0,
        "vendas_lucro_incompleto": vendas_lucro_incompleto,
    }
