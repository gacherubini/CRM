"""De qual anúncio veio a venda — o diferencial que abre a venda do Revy.

Lê o snapshot gravado na confirmação (``Venda.campanha_id_first/last``,
``models.py:126-129``). É leitura local: não depende do Revy Tráfego responder.

Regra dura: venda sem ``campanha_id_*`` é NÃO IDENTIFICADA. Jamais deduzir
origem pela data, pela campanha de outra venda ou pela campanha ativa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import _data
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.tipos import (
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)
from app.models import Campanha, Venda

CENTAVOS = Decimal("0.01")


@dataclass(frozen=True)
class OrigemVenda:
    venda_id: str
    descricao: str
    preco_venda: Decimal
    confirmada_em: str | None
    identificada: bool
    campanha_nome: str | None
    campanha_canal: str | None
    utm_campaign: str | None
    primeiro_clique_nome: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "venda_id": self.venda_id,
            "descricao": self.descricao,
            "preco_venda": str(
                self.preco_venda.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            ),
            "confirmada_em": self.confirmada_em,
            "identificada": self.identificada,
            "campanha_nome": self.campanha_nome,
            "campanha_canal": self.campanha_canal,
            "utm_campaign": self.utm_campaign,
            "primeiro_clique_nome": self.primeiro_clique_nome,
        }


@dataclass(frozen=True)
class OrigemUltima:
    status: str
    origem: OrigemVenda | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "origem": self.origem.to_dict() if self.origem else None,
        }


@dataclass(frozen=True)
class OrigemPeriodo:
    status: str
    janela: Janela
    itens: tuple[OrigemVenda, ...]
    cobertura: Cobertura

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "itens": [item.to_dict() for item in self.itens],
            "cobertura": self.cobertura.to_dict(),
        }


def _nomes_de_campanha(db: Session, loja_slug: str, ids: set[str]) -> dict[str, Campanha]:
    if not ids:
        return {}
    linhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == loja_slug, Campanha.id.in_(ids))
        .all()
    )
    return {c.id: c for c in linhas}


def _montar(venda: Venda, campanhas: dict[str, Campanha]) -> OrigemVenda:
    id_last = venda.campanha_id_last or venda.campanha_id_first
    id_first = venda.campanha_id_first
    campanha = campanhas.get(id_last) if id_last else None
    primeira = campanhas.get(id_first) if id_first else None
    primeiro_nome = (
        primeira.nome if primeira is not None and id_first != id_last else None
    )
    return OrigemVenda(
        venda_id=venda.id,
        descricao=venda.descricao,
        preco_venda=venda.preco_venda,
        confirmada_em=(
            venda.confirmada_em.isoformat() if venda.confirmada_em else None
        ),
        # O id do snapshot é a prova de origem; o nome pode ter sumido do CRM.
        identificada=bool(id_last),
        campanha_nome=campanha.nome if campanha else None,
        campanha_canal=campanha.canal if campanha else None,
        utm_campaign=(
            venda.utm_campaign_last
            or venda.utm_campaign_first
            or (campanha.utm_campaign if campanha else None)
        ),
        primeiro_clique_nome=primeiro_nome,
    )


def _vendas_confirmadas(db: Session, loja_slug: str, janela: Janela | None) -> list[Venda]:
    q = db.query(Venda).filter(
        Venda.loja_slug == loja_slug, Venda.status == "confirmada"
    )
    if janela is not None:
        inicio_dt = datetime.combine(
            janela.inicio, datetime.min.time(), tzinfo=timezone.utc
        ) - timedelta(days=1)
        fim_dt = datetime.combine(
            janela.fim, datetime.max.time(), tzinfo=timezone.utc
        ) + timedelta(days=1)
        q = q.filter(Venda.criada_em >= inicio_dt, Venda.criada_em <= fim_dt)
    vendas = q.order_by(Venda.criada_em.desc()).all()
    if janela is None:
        return vendas
    return [v for v in vendas if janela.inicio <= _data(v.criada_em) <= janela.fim]


def venda_origem_ultima(db: Session, ctx: CopilotoContexto) -> OrigemUltima:
    """A pergunta que abre a venda: de onde veio a última moto vendida."""
    vendas = _vendas_confirmadas(db, ctx.loja_slug, None)
    if not vendas:
        return OrigemUltima(status=STATUS_VAZIO, origem=None)
    venda = vendas[0]
    ids = {i for i in (venda.campanha_id_first, venda.campanha_id_last) if i}
    campanhas = _nomes_de_campanha(db, ctx.loja_slug, ids)
    return OrigemUltima(status=STATUS_OK, origem=_montar(venda, campanhas))


def venda_origem_periodo(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
) -> OrigemPeriodo:
    """Origem de todas as vendas do período, com cobertura declarada."""
    janela = janela_do_periodo(inicio, fim)
    vendas = _vendas_confirmadas(db, ctx.loja_slug, janela)
    if not vendas:
        return OrigemPeriodo(
            status=STATUS_VAZIO,
            janela=janela,
            itens=(),
            cobertura=Cobertura(com_dado=0, total=0),
        )

    ids: set[str] = set()
    for v in vendas:
        ids.update(i for i in (v.campanha_id_first, v.campanha_id_last) if i)
    campanhas = _nomes_de_campanha(db, ctx.loja_slug, ids)

    itens = tuple(_montar(v, campanhas) for v in vendas)
    cobertura = Cobertura(
        com_dado=sum(1 for i in itens if i.identificada), total=len(itens)
    )
    return OrigemPeriodo(
        status=STATUS_PARCIAL if cobertura.parcial else STATUS_OK,
        janela=janela,
        itens=itens,
        cobertura=cobertura,
    )
