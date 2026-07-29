"""Port WhatsAppChannels + GET /control/v1/lojas/{id}/whatsapp-canais."""
from __future__ import annotations

from dataclasses import replace

from app.config import settings
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore, StoreRef
from app.control.whatsapp_channels import (
    InMemoryWhatsAppChannels,
    WhatsAppChannelView,
    WhatsAppChannelsControl,
)
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control as control_mod
from app.web.control import set_whatsapp_channels_port


def _enable(monkeypatch, *, multi: bool = True) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            multi_whatsapp_enabled=multi,
        ),
    )


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _create_store(admin: Actor, slug: str = "loja-wa-canais") -> str:
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name=f"Loja {slug}", slug=slug),
    )
    return store.id


def test_inmemory_port_list():
    admin = _admin_actor()
    store_id = _create_store(admin, "loja-wa-mem")
    port = InMemoryWhatsAppChannels()
    port.seed(
        store_id,
        WhatsAppChannelView(
            id="c1",
            loja_id=store_id,
            e164_or_label="5511999990001",
            evolution_instance="inst-legado",
            ativo=True,
            criado_em="2026-07-29T00:00:00+00:00",
        ),
    )
    channels = WhatsAppChannelsControl(SessionLocal, port).list_channels(
        admin, StoreRef(id=store_id)
    )
    assert len(channels) == 1
    assert channels[0].evolution_instance == "inst-legado"


def test_http_404_quando_multi_off(client_logado, monkeypatch):
    _enable(monkeypatch, multi=False)

    admin = _admin_actor()
    store_id = _create_store(admin, "loja-wa-off")

    r = client_logado.get(f"/control/v1/lojas/{store_id}/whatsapp-canais")
    assert r.status_code == 404


def test_http_lista_com_port_inmemory(client_logado, monkeypatch):
    _enable(monkeypatch, multi=True)

    admin = _admin_actor()
    store_id = _create_store(admin, "loja-wa-on")
    port = InMemoryWhatsAppChannels()
    port.seed(
        store_id,
        WhatsAppChannelView(
            id="canal-1",
            loja_id=store_id,
            e164_or_label="legado",
            evolution_instance="evo-1",
            ativo=True,
        ),
        WhatsAppChannelView(
            id="canal-2",
            loja_id=store_id,
            e164_or_label="linha-2",
            evolution_instance="evo-2",
            ativo=False,
        ),
    )
    set_whatsapp_channels_port(port)
    try:
        r = client_logado.get(f"/control/v1/lojas/{store_id}/whatsapp-canais")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["id"] == "canal-1"
        assert items[1]["ativo"] is False
    finally:
        set_whatsapp_channels_port(None)


def test_http_404_loja_inexistente(client_logado, monkeypatch):
    _enable(monkeypatch, multi=True)
    set_whatsapp_channels_port(InMemoryWhatsAppChannels())
    try:
        r = client_logado.get("/control/v1/lojas/nao-existe/whatsapp-canais")
        assert r.status_code == 404
    finally:
        set_whatsapp_channels_port(None)
