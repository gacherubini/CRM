"""Endpoint service-token GET /v1/lojas/{slug}/integracoes/health (Fase 4).

Superfície que o Portal/Revy Loja consome server-side para o badge de status das
integrações. Espelha o agregador da UI de gestor do Control (Fase 1-2), mas por
slug e guardado por X-Service-Token. Os probes reais são monkeypatchados: o
teste NUNCA bate na rede.
"""
from __future__ import annotations

from dataclasses import replace

from app import api_v1 as api_v1_mod
from app import config as config_mod
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore
from app.db import SessionLocal
from app.models import GestorRevy


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _token(valor: str = "tok-teste-svc") -> dict[str, str]:
    config_mod.settings = replace(config_mod.settings, service_token=valor)
    return {"X-Service-Token": valor}


class _FakeProbe:
    def validar_token(self, token, pixel_id):
        return (True, None)


class _FakeExchanger:
    def obter_access_token(self, refresh_token):
        return "access-xyz"


class _FakeWppPort:
    """`None` => WhatsApp 'missing' sem tocar no chatbot (sem rede)."""

    def listar_canais(self, loja_slug):
        return None


def _mock_ports(monkeypatch) -> None:
    monkeypatch.setattr(api_v1_mod, "_build_integ_probe", lambda: _FakeProbe())
    monkeypatch.setattr(api_v1_mod, "_build_integ_exchanger", lambda: _FakeExchanger())
    monkeypatch.setattr(
        api_v1_mod, "_build_integ_whatsapp_port", lambda: _FakeWppPort()
    )


def _criar_loja(slug: str) -> None:
    StoreControl(SessionLocal).create(_admin_actor(), CreateStore(name=slug, slug=slug))


def test_health_exige_service_token(client):
    config_mod.settings = replace(config_mod.settings, service_token="tok-obrigatorio")
    r = client.get("/v1/lojas/loja-x/integracoes/health")
    assert r.status_code == 401


def test_health_loja_inexistente_404(client, monkeypatch):
    headers = _token()
    _mock_ports(monkeypatch)
    r = client.get("/v1/lojas/nao-existe/integracoes/health", headers=headers)
    assert r.status_code == 404


def test_health_ok_shape_sem_config(client, monkeypatch):
    headers = _token()
    _mock_ports(monkeypatch)
    _criar_loja("loja-integ-api")
    r = client.get("/v1/lojas/loja-integ-api/integracoes/health", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"meta", "google", "whatsapp"}
    for grupo in ("meta", "google", "whatsapp"):
        assert body[grupo]["status"] in {"connected", "error", "missing"}


def test_health_aceita_forcar(client, monkeypatch):
    headers = _token()
    _mock_ports(monkeypatch)
    _criar_loja("loja-integ-forcar")
    r = client.get(
        "/v1/lojas/loja-integ-forcar/integracoes/health?forcar=1", headers=headers
    )
    assert r.status_code == 200, r.text
