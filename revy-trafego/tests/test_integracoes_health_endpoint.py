"""Task 5 do plano de status de integrações: endpoint JSON de health por Loja.

`GET /control/v1/lojas/{loja_id}/integracoes/health` expõe `health_da_loja`
(Task 4) via HTTP. Testes usam fakes de probe/exchanger injetados através de
`_build_probe`/`_build_exchanger` (monkeypatch) para nunca bater na rede.
"""

from __future__ import annotations

from dataclasses import replace

from app.config import settings
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore
from app.db import SessionLocal
from app.models import GestorRevy
from app.web import control_ui as control_ui_mod


def _enable_control_ui(monkeypatch):
    monkeypatch.setattr(
        control_ui_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _create_store(slug: str) -> str:
    store = StoreControl(SessionLocal).create(
        _admin_actor(),
        CreateStore(name="Loja Health Endpoint", slug=slug),
    )
    return store.id


class FakeGraphProbe:
    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        return True, None


class FakeExchanger:
    def obter_access_token(self, refresh_token: str) -> str:
        return "access-fake"


class FakeWhatsappPort:
    def listar_canais(self, loja_slug: str):
        return None


def _patch_fakes(monkeypatch):
    monkeypatch.setattr(control_ui_mod, "_build_probe", lambda: FakeGraphProbe())
    monkeypatch.setattr(control_ui_mod, "_build_exchanger", lambda: FakeExchanger())
    monkeypatch.setattr(
        control_ui_mod, "_build_whatsapp_port", lambda: FakeWhatsappPort()
    )


def test_health_endpoint_retorna_200_com_meta_e_google(client_logado, monkeypatch):
    _enable_control_ui(monkeypatch)
    _patch_fakes(monkeypatch)
    store_id = _create_store("loja-health-endpoint-ok")

    response = client_logado.get(f"/control/v1/lojas/{store_id}/integracoes/health")

    assert response.status_code == 200
    body = response.json()
    assert "meta" in body
    assert "google" in body
    assert "whatsapp" in body
    assert "status" in body["meta"]
    assert "status" in body["google"]
    assert "status" in body["whatsapp"]


def test_health_endpoint_aceita_forcar_1(client_logado, monkeypatch):
    _enable_control_ui(monkeypatch)
    _patch_fakes(monkeypatch)
    store_id = _create_store("loja-health-endpoint-forcar")

    response = client_logado.get(
        f"/control/v1/lojas/{store_id}/integracoes/health?forcar=1"
    )

    assert response.status_code == 200
    body = response.json()
    assert "meta" in body
    assert "google" in body


def test_health_endpoint_sem_sessao_retorna_401(client, monkeypatch):
    _enable_control_ui(monkeypatch)
    _patch_fakes(monkeypatch)
    store_id = _create_store("loja-health-endpoint-sem-sessao")

    response = client.get(f"/control/v1/lojas/{store_id}/integracoes/health")

    assert response.status_code == 401


def test_health_endpoint_loja_inexistente_retorna_404(client_logado, monkeypatch):
    _enable_control_ui(monkeypatch)
    _patch_fakes(monkeypatch)

    response = client_logado.get(
        "/control/v1/lojas/loja-que-nao-existe/integracoes/health"
    )

    assert response.status_code == 404
