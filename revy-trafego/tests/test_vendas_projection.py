from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db import SessionLocal
from app.models import Loja, VendaProjetada
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


def test_projecao_vincula_loja_id_pelo_slug():
    """Sem loja_id a venda some da Visao Geral do Control, que filtra por ele."""
    db = SessionLocal()
    try:
        loja = Loja(nome="Loja A", slug="loja-a", status="ativa")
        db.add(loja)
        db.flush()

        projetar_venda(db, _snapshot(loja_slug="loja-a"))
        db.commit()

        assert db.get(VendaProjetada, ("venda-igual", "loja-a")).loja_id == loja.id
    finally:
        db.close()


def test_projecao_sem_loja_cadastrada_nao_quebra():
    """Slug ainda nao provisionado no Control: projeta com loja_id nulo."""
    db = SessionLocal()
    try:
        resultado = projetar_venda(db, _snapshot(loja_slug="loja-sem-cadastro"))
        db.commit()

        assert resultado.aplicada is True
        assert resultado.venda.loja_id is None
    finally:
        db.close()


def test_projecao_vincula_loja_id_em_venda_ja_existente():
    """Venda orfa recebe o vinculo assim que a loja passa a existir."""
    db = SessionLocal()
    try:
        projetar_venda(db, _snapshot(loja_slug="loja-a"))
        db.commit()
        assert db.get(VendaProjetada, ("venda-igual", "loja-a")).loja_id is None

        loja = Loja(nome="Loja A", slug="loja-a", status="ativa")
        db.add(loja)
        db.flush()
        projetar_venda(
            db,
            _snapshot(
                loja_slug="loja-a",
                atualizada_em=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
            ),
        )
        db.commit()

        assert db.get(VendaProjetada, ("venda-igual", "loja-a")).loja_id == loja.id
    finally:
        db.close()


def test_backfill_religa_vendas_orfas_sem_tocar_vinculos_existentes():
    """Passivo anterior a correcao: vendas com loja_id NULL voltam para o Control."""
    from app.control.backfill import religar_vendas_orfas

    db = SessionLocal()
    try:
        certa = Loja(nome="Loja A", slug="loja-a", status="ativa")
        outra = Loja(nome="Loja B", slug="loja-b", status="ativa")
        db.add_all([certa, outra])
        db.flush()

        orfa = VendaProjetada(
            id="venda-orfa",
            loja_slug="loja-a",
            preco_venda=Decimal("100"),
            status="confirmada",
            criada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
            confirmada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
            atualizada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
        )
        # Vínculo já correto não pode ser reescrito pelo slug.
        vinculada = VendaProjetada(
            id="venda-vinculada",
            loja_slug="loja-a",
            loja_id=outra.id,
            preco_venda=Decimal("200"),
            status="confirmada",
            criada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
            confirmada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
            atualizada_em=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
        )
        db.add_all([orfa, vinculada])
        db.flush()

        religadas = religar_vendas_orfas(db.connection())
        db.commit()

        assert religadas == 1
        assert db.get(VendaProjetada, ("venda-orfa", "loja-a")).loja_id == certa.id
        assert db.get(VendaProjetada, ("venda-vinculada", "loja-a")).loja_id == outra.id
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
