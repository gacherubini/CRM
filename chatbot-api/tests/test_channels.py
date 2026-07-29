"""Canais WhatsApp (multi-WA skeleton): list/register/inactivate + backfill + resolver."""
import uuid

import pytest

from app import channels, config, models_db, servico
from fastapi import HTTPException


def test_backfill_legacy_from_loja(db, loja_a):
    loja = db.get(models_db.Loja, loja_a["loja_id"])
    loja.whatsapp = "5511999990001"
    db.commit()

    assert channels.list_channels(db, loja_a["loja_id"]) == []

    canal = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    assert canal is not None
    assert canal["evolution_instance"] == loja_a["instance"]
    assert canal["e164_or_label"] == "5511999990001"
    assert canal["ativo"] is True
    assert canal["loja_id"] == loja_a["loja_id"]

    # Idempotente
    again = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    assert again["id"] == canal["id"]
    assert len(channels.list_channels(db, loja_a["loja_id"])) == 1


def test_backfill_label_legado_quando_sem_whatsapp(db, loja_a):
    canal = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    assert canal["e164_or_label"] == "legado"


def test_register_channel_multi_off_apenas_um(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", False)
    channels.backfill_legacy_from_loja(db, loja_a["loja_id"])

    with pytest.raises(HTTPException) as exc:
        channels.register_channel(
            db, loja_a["loja_id"], "inst-extra", "linha-2"
        )
    assert exc.value.status_code == 409


def test_register_channel_multi_on(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    channels.backfill_legacy_from_loja(db, loja_a["loja_id"])

    extra = channels.register_channel(
        db, loja_a["loja_id"], f"inst-extra-{uuid.uuid4().hex[:6]}", "linha-2"
    )
    assert extra["ativo"] is True
    assert len(channels.list_channels(db, loja_a["loja_id"])) == 2


def test_register_instance_outra_loja_409(db, loja_a, loja_b, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    channels.backfill_legacy_from_loja(db, loja_a["loja_id"])

    with pytest.raises(HTTPException) as exc:
        channels.register_channel(
            db, loja_b["loja_id"], loja_a["instance"], "roubado"
        )
    assert exc.value.status_code == 409
    assert "outra loja" in exc.value.detail


def test_inactivate_channel(db, loja_a):
    canal = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    out = channels.inactivate_channel(db, loja_a["loja_id"], canal["id"])
    assert out["ativo"] is False

    # Idempotente
    again = channels.inactivate_channel(db, loja_a["loja_id"], canal["id"])
    assert again["ativo"] is False


def test_inactivate_outra_loja_404(db, loja_a, loja_b):
    canal = channels.backfill_legacy_from_loja(db, loja_a["loja_id"])
    with pytest.raises(HTTPException) as exc:
        channels.inactivate_channel(db, loja_b["loja_id"], canal["id"])
    assert exc.value.status_code == 404


def test_resolver_via_whatsapp_canais(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    instance = f"canal-only-{uuid.uuid4().hex[:6]}"
    channels.register_channel(db, loja_a["loja_id"], instance, "secundario")

    # Instância só no canal (não em Loja.evolution_instance)
    loja = servico.resolver_loja_por_instancia(db, instance)
    assert loja.id == loja_a["loja_id"]


def test_resolver_fallback_loja_legado(db, loja_a):
    loja = servico.resolver_loja_por_instancia(db, loja_a["instance"])
    assert loja.id == loja_a["loja_id"]


def test_http_list_backfill(client, loja_a):
    r = client.get("/v1/whatsapp/canais", headers=loja_a["headers"])
    assert r.status_code == 200
    body = r.json()
    assert len(body["canais"]) == 1
    assert body["canais"][0]["evolution_instance"] == loja_a["instance"]


def test_http_post_404_quando_multi_off(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", False)
    r = client.post(
        "/v1/whatsapp/canais",
        headers=loja_a["headers"],
        json={"evolution_instance": "x", "e164_or_label": "y"},
    )
    assert r.status_code == 404


def test_http_post_e_inativar(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    # Garante legado
    client.get("/v1/whatsapp/canais", headers=loja_a["headers"])

    inst = f"http-extra-{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/v1/whatsapp/canais",
        headers=loja_a["headers"],
        json={"evolution_instance": inst, "e164_or_label": "linha-2"},
    )
    assert r.status_code == 201
    canal_id = r.json()["id"]

    r2 = client.post(
        f"/v1/whatsapp/canais/{canal_id}/inativar",
        headers=loja_a["headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["ativo"] is False


def test_http_isolamento_loja(client, loja_a, loja_b, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    r = client.get("/v1/whatsapp/canais", headers=loja_a["headers"])
    canal_id = r.json()["canais"][0]["id"]

    r2 = client.post(
        f"/v1/whatsapp/canais/{canal_id}/inativar",
        headers=loja_b["headers"],
    )
    assert r2.status_code == 404
