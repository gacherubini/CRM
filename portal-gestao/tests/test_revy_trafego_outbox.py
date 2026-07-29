import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.conversions import PurchaseConversion
from app.cripto import decifrar
from app.db import SessionLocal
from app.models import RevyTrafegoEventOutbox, Venda, VendaCustoDireto
from app.revy_trafego_outbox import (
    enfileirar_venda_atualizada,
    enfileirar_venda_confirmada,
    processar_pendentes,
    tentar_entregar,
)


class RevyFake:
    def __init__(self, resposta=None):
        self.resposta = resposta
        self.confirmadas = []
        self.atualizadas = []

    def notificar_venda_confirmada(self, *, loja_slug, payload):
        self.confirmadas.append((loja_slug, payload))
        return self.resposta

    def notificar_venda_atualizada(self, *, loja_slug, payload):
        self.atualizadas.append((loja_slug, payload))
        return self.resposta


def _venda(db, *, venda_id="venda-revy-1", status="confirmada"):
    instante = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    venda = Venda(
        id=venda_id,
        loja_slug="loja-teste",
        lead_ref="lead-secreto",
        vendedor_email="vendedor@loja.test",
        descricao="Honda Civic",
        preco_venda=Decimal("85000.50"),
        custo_veiculo=Decimal("70000.00"),
        status=status,
        criada_em=instante - timedelta(days=1),
        confirmada_em=instante if status == "confirmada" else None,
        atualizada_em=instante,
        campanha_id_first="campanha-1",
        utm_campaign_first="seminovos-julho",
    )
    venda.custos_diretos.append(
        VendaCustoDireto(categoria="documentacao", valor=Decimal("500.00"))
    )
    db.add(venda)
    db.flush()
    return venda


def test_outbox_confirmacao_criptografa_pii_e_e_idempotente():
    db = SessionLocal()
    try:
        venda = _venda(db)
        purchase = PurchaseConversion.from_sale(
            venda,
            {
                "telefone": "5511999999999",
                "email": "cliente@example.com",
                "fbclid": "fbclid-secreto",
                "ctwa_clid": "ctwa-secreto",
            },
        )

        item = enfileirar_venda_confirmada(db, venda, purchase)
        repetido = enfileirar_venda_confirmada(db, venda, purchase)
        db.commit()

        assert repetido.id == item.id
        assert db.query(RevyTrafegoEventOutbox).count() == 1
        assert "5511999999999" not in item.payload_ciphertext
        assert "cliente@example.com" not in item.payload_ciphertext

        payload = json.loads(decifrar(item.payload_ciphertext))
        assert payload["cliente_telefone"] == "5511999999999"
        assert payload["custos_diretos_total"] == "500.00"
        assert payload["confirmada_em"].startswith("2026-07-28T12:00:00")

        destino = RevyFake({"ok": True})
        assert tentar_entregar(db, item, client=destino) is True
        db.refresh(item)
        assert item.status == "delivered"
        assert item.attempts == 1
        assert destino.confirmadas[0][1]["event_id"] == purchase.event_id
    finally:
        db.close()


def test_outbox_atualizacao_falha_sem_expor_payload():
    db = SessionLocal()
    try:
        venda = _venda(db, venda_id="venda-revy-2", status="cancelada")
        item = enfileirar_venda_atualizada(db, venda)
        db.commit()

        assert tentar_entregar(db, item, client=RevyFake(None)) is False
        db.refresh(item)
        assert item.status == "failed"
        assert item.attempts == 1
        assert item.last_error == "Revy Trafego indisponivel"
        assert "lead-secreto" not in (item.last_error or "")
    finally:
        db.close()


def test_worker_respeita_backoff_e_reprocessa_depois(monkeypatch):
    db = SessionLocal()
    try:
        venda = _venda(db, venda_id="venda-revy-3", status="cancelada")
        item = enfileirar_venda_atualizada(db, venda)
        item.status = "failed"
        item.attempts = 1
        item.atualizada_em = datetime.now(timezone.utc)
        db.commit()
        item_id = item.id
    finally:
        db.close()

    destino = RevyFake({"ok": True})
    monkeypatch.setattr(
        "app.revy_trafego_outbox.RevyTrafegoClient", lambda: destino
    )
    cedo = processar_pendentes(SessionLocal, backoff_base_seconds=60)
    assert cedo["processados"] == 0
    assert cedo["aguardando_backoff"] == 1

    db = SessionLocal()
    try:
        item = db.get(RevyTrafegoEventOutbox, item_id)
        item.atualizada_em = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.commit()
    finally:
        db.close()

    devido = processar_pendentes(SessionLocal, backoff_base_seconds=60)
    assert devido["entregues"] == 1
    assert destino.atualizadas


def test_worker_respeita_lease_e_recupera_processamento_abandonado(monkeypatch):
    db = SessionLocal()
    try:
        venda = _venda(db, venda_id="venda-revy-4", status="cancelada")
        item = enfileirar_venda_atualizada(db, venda)
        item.status = "processing"
        item.atualizada_em = datetime.now(timezone.utc)
        db.commit()
        item_id = item.id
    finally:
        db.close()

    destino = RevyFake({"ok": True})
    monkeypatch.setattr(
        "app.revy_trafego_outbox.RevyTrafegoClient", lambda: destino
    )
    ocupado = processar_pendentes(SessionLocal, lease_seconds=60)
    assert ocupado["processados"] == 0
    assert ocupado["aguardando_lease"] == 1
    assert destino.atualizadas == []

    db = SessionLocal()
    try:
        item = db.get(RevyTrafegoEventOutbox, item_id)
        item.atualizada_em = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.commit()
    finally:
        db.close()

    recuperado = processar_pendentes(SessionLocal, lease_seconds=60)
    assert recuperado["entregues"] == 1
    assert len(destino.atualizadas) == 1
