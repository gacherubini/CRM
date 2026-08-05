"""Canais WhatsApp (multi-WA skeleton): list/register/inactivate + backfill + resolver."""
import re
import uuid

import pytest

from app import channels, config, models_db, servico
from app.whatsapp_provider import WhatsAppProvisionError
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
    assert canal["principal_estoque"] is True

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


def test_register_sem_instance_gera_nome_do_slug(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    inst = canal["evolution_instance"]
    assert inst.startswith(loja_a["slug"] + "-")
    assert re.fullmatch(r"[a-z0-9-]+", inst)


def test_register_sem_instance_duas_vezes_gera_nomes_distintos(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    a = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    b = channels.register_channel(db, loja_a["loja_id"], None, "linha 3")
    assert a["evolution_instance"] != b["evolution_instance"]


def test_register_com_instance_continua_idempotente(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    a = channels.register_channel(db, loja_a["loja_id"], "fixa-1", "linha 2")
    b = channels.register_channel(db, loja_a["loja_id"], "fixa-1", "outro label")
    assert a["id"] == b["id"]


def test_http_post_canal_sem_instance(client, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    r = client.post(
        "/v1/whatsapp/canais",
        headers=loja_a["headers"],
        json={"e164_or_label": "linha 2"},
    )
    assert r.status_code == 201
    assert r.json()["evolution_instance"]


class _ProviderQueFalha:
    def __init__(self):
        self.ensure_chamado = 0

    def ensure_instance(self, canal):
        self.ensure_chamado += 1
        raise WhatsAppProvisionError("evolution fora", code="evolution_unreachable")

    def connect(self, canal):
        raise AssertionError("connect não deve ser chamado se o ensure falhou")

    def status(self, canal):
        raise NotImplementedError

    def disconnect(self, canal):
        raise NotImplementedError


def test_connect_chama_ensure_e_502_quando_evolution_fora(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha 2")
    prov = _ProviderQueFalha()

    with pytest.raises(Exception) as exc:
        channels.connect_channel(db, loja_a["loja_id"], canal["id"], provider=prov)

    assert getattr(exc.value, "status_code", None) == 502
    assert prov.ensure_chamado == 1
    atual = channels.list_channels(db, loja_a["loja_id"])
    alvo = [c for c in atual if c["id"] == canal["id"]][0]
    assert alvo["estado"] == "pendente"


class _ProviderStatusFixo:
    """Devolve estado live sem mutar o ORM (simula Evolution open pós-QR)."""

    def __init__(self, estado: str, *, fail: bool = False):
        self.estado = estado
        self.fail = fail
        self.status_chamado = 0

    def connect(self, canal):
        raise NotImplementedError

    def status(self, canal):
        self.status_chamado += 1
        if self.fail:
            raise WhatsAppProvisionError(
                "evolution fora", code="evolution_unreachable"
            )
        from app.whatsapp_provider import StatusResult

        return StatusResult(
            estado=self.estado,
            ativo=bool(canal.ativo),
            evolution_instance=canal.evolution_instance,
        )

    def disconnect(self, canal):
        raise NotImplementedError


def test_channel_status_persiste_conectado_quando_live_mudou(db, loja_a, monkeypatch):
    """DB pendente + provider conectado → após status, DB = conectado."""
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha status")
    assert canal["estado"] == "pendente"

    prov = _ProviderStatusFixo("conectado")
    out = channels.channel_status(
        db, loja_a["loja_id"], canal["id"], provider=prov
    )
    assert out["estado"] == "conectado"
    assert prov.status_chamado == 1

    na_lista = [
        c
        for c in channels.list_channels(db, loja_a["loja_id"])
        if c["id"] == canal["id"]
    ][0]
    assert na_lista["estado"] == "conectado"

    row = db.get(models_db.WhatsAppCanal, canal["id"])
    assert row is not None
    assert row.estado == "conectado"


def test_channel_status_idempotente_quando_ja_conectado(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha ok")
    row = db.get(models_db.WhatsAppCanal, canal["id"])
    row.estado = "conectado"
    db.commit()

    prov = _ProviderStatusFixo("conectado")
    out = channels.channel_status(
        db, loja_a["loja_id"], canal["id"], provider=prov
    )
    assert out["estado"] == "conectado"
    row2 = db.get(models_db.WhatsAppCanal, canal["id"])
    assert row2.estado == "conectado"
    assert row2.ativo is True


def test_channel_status_nao_reativa_inativo(db, loja_a, monkeypatch):
    """Canal inativo não vira conectado por GET status."""
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha morta")
    channels.inactivate_channel(db, loja_a["loja_id"], canal["id"])

    prov = _ProviderStatusFixo("conectado")
    out = channels.channel_status(
        db, loja_a["loja_id"], canal["id"], provider=prov
    )
    # Resposta pode refletir live, mas DB permanece inativo.
    assert out["estado"] == "conectado"

    row = db.get(models_db.WhatsAppCanal, canal["id"])
    assert row.estado == "inativo"
    assert row.ativo is False
    na_lista = [
        c
        for c in channels.list_channels(db, loja_a["loja_id"])
        if c["id"] == canal["id"]
    ][0]
    assert na_lista["estado"] == "inativo"
    assert na_lista["ativo"] is False


def test_channel_status_502_quando_provider_falha(db, loja_a, monkeypatch):
    monkeypatch.setattr(config, "MULTI_WHATSAPP_ENABLED", True)
    canal = channels.register_channel(db, loja_a["loja_id"], None, "linha fail")
    prov = _ProviderStatusFixo("conectado", fail=True)

    with pytest.raises(HTTPException) as exc:
        channels.channel_status(
            db, loja_a["loja_id"], canal["id"], provider=prov
        )
    assert exc.value.status_code == 502

    row = db.get(models_db.WhatsAppCanal, canal["id"])
    assert row.estado == "pendente"
