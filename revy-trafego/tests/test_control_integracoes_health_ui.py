"""Painel de status das integracoes (Meta/Google/WhatsApp) no detalhe da Loja.

Task 9 (Fase 3): apenas o container HTML + CSS. Sem dados ao vivo aqui — o JS
que consome `GET /control/v1/lojas/{id}/integracoes/health` vem na Task 10.
"""
from __future__ import annotations

from dataclasses import replace

from app.config import settings
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control_ui as control_ui_mod


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _enable_control_ui(monkeypatch) -> None:
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            google_ads_sync_enabled=True,
        ),
    )


def _login(client) -> None:
    response = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_painel_de_saude_das_integracoes_aparece_no_topo_da_aba(client, monkeypatch):
    _enable_control_ui(monkeypatch)
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Integrações UI", slug="loja-integracoes-ui"),
    )
    _login(client)

    detail = client.get(f"/app/control/lojas/{store.id}")

    assert detail.status_code == 200
    assert 'id="integracoes-health"' in detail.text
    assert f'data-loja-id="{store.id}"' in detail.text
    assert "Testar agora" in detail.text
