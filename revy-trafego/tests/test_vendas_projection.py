from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db import SessionLocal
from app.models import VendaProjetada
from app.vendas_projection import VendaSnapshot, projetar_venda


def _snapshot(*, loja_slug, status="confirmada", atualizada_em=None, valor="100"):
    instante = atualizada_em or datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    return VendaSnapshot(
        venda_id="venda-igual",
        loja_slug=loja_slug,
        status=status,
        valor=Decimal(valor),
        criada_em=instante - timedelta(days=1),
        confirmada_em=instante if status == "confirmada" else None,
        atualizada_em=instante,
        custo_veiculo=Decimal("70"),
        custos_diretos_total=Decimal("5"),
    )


def test_projecao_isola_mesmo_id_por_loja():
    db = SessionLocal()
    try:
        a = projetar_venda(db, _snapshot(loja_slug="loja-a", valor="100"))
        b = projetar_venda(db, _snapshot(loja_slug="loja-b", valor="200"))
        db.commit()

        assert a.aplicada is True and b.aplicada is True
        assert db.query(VendaProjetada).count() == 2
        assert db.get(VendaProjetada, ("venda-igual", "loja-a")).preco_venda == Decimal("100")
        assert db.get(VendaProjetada, ("venda-igual", "loja-b")).preco_venda == Decimal("200")
    finally:
        db.close()


def test_projecao_rejeita_confirmacao_antiga_apos_cancelamento():
    base = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        projetar_venda(
            db,
            _snapshot(
                loja_slug="loja-a",
                status="cancelada",
                atualizada_em=base + timedelta(minutes=1),
            ),
        )
        atrasada = projetar_venda(
            db,
            _snapshot(loja_slug="loja-a", status="confirmada", atualizada_em=base),
        )
        db.commit()

        assert atrasada.aplicada is False
        assert atrasada.motivo == "evento_antigo"
        assert atrasada.venda.status == "cancelada"
    finally:
        db.close()


def test_projecao_repetida_e_idempotente():
    snapshot = _snapshot(loja_slug="loja-a")
    db = SessionLocal()
    try:
        primeira = projetar_venda(db, snapshot)
        repetida = projetar_venda(db, snapshot)
        db.commit()

        assert primeira.aplicada is True
        assert repetida.aplicada is False
        assert repetida.motivo == "idempotente"
    finally:
        db.close()
