"""Painel de status das integracoes (Meta/Google/WhatsApp) no detalhe da Loja.

Task 9 (Fase 3): apenas o container HTML + CSS. Task 10 (Fase 3): o JS que
consome `GET /control/v1/lojas/{id}/integracoes/health` e preenche o painel
(`integracoes_health.js`), incluído aqui pela referência ao `<script>`.

O card vive na aba "Visão geral" (`#panel-visao`), que é a aba default e NÃO é
gated por `google_ads_enabled` — diferente de `#panel-integracoes`, que só
renderiza quando `google_ads_sync_enabled` está ligado. Isso garante que o
gestor veja o status assim que abrir a Loja, mesmo com Google Ads desligado.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

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


def _enable_control_ui(monkeypatch, *, google_ads_sync_enabled: bool) -> None:
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(
            settings,
            revy_control_enabled=True,
            google_ads_sync_enabled=google_ads_sync_enabled,
        ),
    )


def _login(client) -> None:
    response = client.post(
        "/login",
        data={"email": "trafego@revy.local", "senha": "secret-teste"},
        follow_redirects=False,
    )
    assert response.status_code == 303


@pytest.mark.parametrize("google_ads_sync_enabled", [False, True])
def test_painel_de_saude_das_integracoes_aparece_na_visao_geral(
    client, monkeypatch, google_ads_sync_enabled
):
    _enable_control_ui(monkeypatch, google_ads_sync_enabled=google_ads_sync_enabled)
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(
            name=f"Loja Integrações UI {google_ads_sync_enabled}",
            slug=f"loja-integracoes-ui-{google_ads_sync_enabled}".lower(),
        ),
    )
    _login(client)

    # Visão geral é a aba default: nenhum ?tab= necessário.
    detail = client.get(f"/app/control/lojas/{store.id}")

    assert detail.status_code == 200
    assert 'id="integracoes-health"' in detail.text
    assert f'data-loja-id="{store.id}"' in detail.text
    assert "Testar agora" in detail.text

    # O card fica dentro de #panel-visao, que nunca é gated pela flag do
    # Google Ads — diferente de #panel-integracoes.
    visao_start = detail.text.index('id="panel-visao"')
    health_index = detail.text.index('id="integracoes-health"')
    assert health_index > visao_start
    if not google_ads_sync_enabled:
        assert 'id="panel-integracoes"' not in detail.text


def test_painel_de_saude_inclui_script_que_consome_o_endpoint(client, monkeypatch):
    """Task 10: o JS que busca `/integracoes/health` e renderiza os badges
    precisa estar incluído na página — sem ele o card fica preso em
    "Carregando…" para sempre."""
    _enable_control_ui(monkeypatch, google_ads_sync_enabled=False)
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Integrações Script", slug="loja-integracoes-script"),
    )
    _login(client)

    detail = client.get(f"/app/control/lojas/{store.id}")

    assert detail.status_code == 200
    assert "integracoes_health.js" in detail.text
