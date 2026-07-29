"""Port WhatsAppChannels + rotas Control multi-WA (list/register/connect/RBAC)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import settings
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    CreateStore,
    StoreRef,
)
from app.control.whatsapp_channels import (
    InMemoryWhatsAppChannels,
    WhatsAppChannelView,
    WhatsAppChannelsControl,
)
from app.db import SessionLocal
from app.models import GestorRevy, VinculoTrafego
from app.auth import hash_senha
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
            estado="conectado",
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
            estado="conectado",
        ),
        WhatsAppChannelView(
            id="canal-2",
            loja_id=store_id,
            e164_or_label="linha-2",
            evolution_instance="evo-2",
            ativo=False,
            estado="inativo",
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
        assert items[0]["estado"] == "conectado"
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


def test_http_register_e_connect_no_store(client_logado, monkeypatch):
    _enable(monkeypatch, multi=True)
    admin = _admin_actor()
    store_id = _create_store(admin, "loja-wa-connect")
    port = InMemoryWhatsAppChannels()
    set_whatsapp_channels_port(port)
    try:
        r = client_logado.post(
            f"/control/v1/lojas/{store_id}/whatsapp-canais",
            json={
                "evolution_instance": "evo-nova",
                "e164_or_label": "linha-2",
            },
        )
        assert r.status_code == 201
        canal_id = r.json()["id"]
        assert r.json()["estado"] == "pendente"

        r2 = client_logado.post(
            f"/control/v1/lojas/{store_id}/whatsapp-canais/{canal_id}/connect"
        )
        assert r2.status_code == 200
        assert "no-store" in r2.headers.get("cache-control", "").lower()
        assert r2.json().get("qr_payload")
        assert r2.json()["estado"] == "conectado"
    finally:
        set_whatsapp_channels_port(None)


def test_colaborador_nao_inativa_nem_desconecta(monkeypatch):
    _enable(monkeypatch, multi=True)
    admin = _admin_actor()
    store_id = _create_store(admin, "loja-wa-rbac")
    port = InMemoryWhatsAppChannels()
    port.seed(
        store_id,
        WhatsAppChannelView(
            id="c-rbac",
            loja_id=store_id,
            e164_or_label="legado",
            evolution_instance="evo-rbac",
            ativo=True,
            estado="conectado",
        ),
    )
    control = WhatsAppChannelsControl(SessionLocal, port)

    with SessionLocal() as db:
        collab = GestorRevy(
            email="colab-wa@revy.local",
            nome="Colaborador WA",
            senha_hash=hash_senha("secret-teste"),
            papel="gestor",
            ativo=True,
        )
        db.add(collab)
        db.flush()
        db.add(
            VinculoTrafego(
                loja_id=store_id,
                gestor_id=collab.id,
                tipo="colaborador",
            )
        )
        db.commit()
        collab_id = collab.id

    collab_actor = Actor(
        id=collab_id,
        email="colab-wa@revy.local",
        name="Colaborador WA",
        role="gestor",
    )
    # colaborador lista
    listed = control.list_channels(collab_actor, StoreRef(id=store_id))
    assert len(listed) == 1

    with pytest.raises(AccessDenied):
        control.disconnect(collab_actor, StoreRef(id=store_id), "c-rbac")
    with pytest.raises(AccessDenied):
        control.inactivate(collab_actor, StoreRef(id=store_id), "c-rbac")
    with pytest.raises(AccessDenied):
        control.connect(collab_actor, StoreRef(id=store_id), "c-rbac")
    with pytest.raises(AccessDenied):
        control.register(
            collab_actor,
            StoreRef(id=store_id),
            instance="x",
            label="y",
        )

    # admin muta
    out = control.disconnect(admin, StoreRef(id=store_id), "c-rbac")
    assert out.estado == "desconectado"
