from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db import SessionLocal
from app.models import Campanha, Loja, VendaProjetada, novo_id
from app.vendas_projection import VendaSnapshot, projetar_venda


def _snapshot(*, loja_slug, status="confirmada", atualizada_em=None, valor="100", **extras):
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
        **extras,
    )


def _campanha(db, *, loja_slug, nome="MT03 Agosto", utm="MT03AGOSTO"):
    campanha = Campanha(
        id=novo_id(),
        loja_slug=loja_slug,
        nome=nome,
        canal="meta",
        status="ativa",
        utm_campaign=utm,
        utm_campaign_norm=utm.casefold(),
        criada_por_email="dono@loja.test",
    )
    db.add(campanha)
    db.flush()
    return campanha


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


def test_projecao_descarta_campanha_id_desconhecido():
    """O Portal envia UUID do cadastro dele; Campanha.id no Revy e gerado local.

    Aceitar o id de fora grava lixo na venda e desliga tanto o casamento por UTM
    quanto a heranca do lead (roi_calc: ambos exigem campanha_id vazio).
    """
    db = SessionLocal()
    try:
        snap = _snapshot(
            loja_slug="moto-center",
            campanha_id_last="uuid-do-portal",
            campanha_id_first="uuid-do-portal",
            utm_campaign_last="MT03AGOSTO",
            utm_campaign_first="MT03AGOSTO",
        )
        r = projetar_venda(db, snap)
        db.commit()

        assert r.venda.campanha_id_last is None
        assert r.venda.campanha_id_first is None
        assert r.venda.utm_campaign_last == "MT03AGOSTO"
        assert r.venda.utm_campaign_first == "MT03AGOSTO"
    finally:
        db.close()


def test_projecao_mantem_campanha_id_conhecido():
    db = SessionLocal()
    try:
        campanha = _campanha(db, loja_slug="moto-center")
        r = projetar_venda(
            db,
            _snapshot(
                loja_slug="moto-center",
                campanha_id_last=campanha.id,
                campanha_id_first=campanha.id,
            ),
        )
        db.commit()

        assert r.venda.campanha_id_last == campanha.id
        assert r.venda.campanha_id_first == campanha.id
    finally:
        db.close()


def test_projecao_descarta_campanha_id_de_outra_loja():
    """Id valido no Revy, mas de outra loja: nao pode atravessar a fronteira."""
    db = SessionLocal()
    try:
        alheia = _campanha(db, loja_slug="outra-loja")
        r = projetar_venda(
            db, _snapshot(loja_slug="moto-center", campanha_id_last=alheia.id)
        )
        db.commit()

        assert r.venda.campanha_id_last is None
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
