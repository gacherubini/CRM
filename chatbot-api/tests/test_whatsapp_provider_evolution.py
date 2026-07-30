"""EvolutionWhatsAppProvider: seleção por config e chamadas HTTP (MockTransport)."""
import json as json_module

import httpx
import pytest

from app import config
from app.models_db import WhatsAppCanal
from app.whatsapp_provider import (
    ESTADO_CONECTADO,
    ESTADO_DESCONECTADO,
    ESTADO_PENDENTE,
    EvolutionStubWhatsAppProvider,
    EvolutionWhatsAppProvider,
    WhatsAppProvisionError,
    get_whatsapp_provider,
    set_whatsapp_provider,
)


@pytest.fixture(autouse=True)
def _reset_provider():
    set_whatsapp_provider(None)
    yield
    set_whatsapp_provider(None)


def test_default_e_stub(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "stub")
    assert isinstance(get_whatsapp_provider(), EvolutionStubWhatsAppProvider)


def test_config_evolution_seleciona_adapter_real(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "evolution")
    assert isinstance(get_whatsapp_provider(), EvolutionWhatsAppProvider)


def _canal(instance="loja1-ab12", estado=ESTADO_PENDENTE):
    return WhatsAppCanal(
        id="c1",
        loja_id="l1",
        e164_or_label="linha 2",
        evolution_instance=instance,
        ativo=True,
        estado=estado,
    )


def _provider(handler):
    return EvolutionWhatsAppProvider(
        base_url="http://evo.local",
        api_key="k",
        webhook_url="http://n8n.local/webhook/whatsapp-ai",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "state,esperado",
    [
        ("open", ESTADO_CONECTADO),
        ("connecting", ESTADO_PENDENTE),
        ("close", ESTADO_DESCONECTADO),
        ("qualquer-coisa", ESTADO_DESCONECTADO),
    ],
)
def test_status_mapeia_estados(state, esperado):
    def handler(request):
        assert request.url.path == "/instance/connectionState/loja1-ab12"
        assert request.headers["apikey"] == "k"
        return httpx.Response(200, json={"instance": {"state": state}})

    got = _provider(handler).status(_canal())
    assert got.estado == esperado
    assert got.evolution_instance == "loja1-ab12"


def test_connect_devolve_qr_e_nao_vaza_em_excecao():
    def handler(request):
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": "loja1-ab12"}])
        assert request.url.path == "/instance/connect/loja1-ab12"
        return httpx.Response(
            200, json={"base64": "QR-SECRETO", "pairingCode": "ABCD-1234", "count": 1}
        )

    got = _provider(handler).connect(_canal())
    assert got.qr_payload == "QR-SECRETO"
    assert got.pairing_code == "ABCD-1234"
    assert got.estado == ESTADO_PENDENTE


def test_disconnect_faz_logout():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "SUCCESS"})

    got = _provider(handler).disconnect(_canal(estado=ESTADO_CONECTADO))
    assert got.estado == ESTADO_DESCONECTADO
    assert ("DELETE", "/instance/logout/loja1-ab12") in chamadas


def test_erro_de_rede_vira_provision_error_sem_expor_url():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(WhatsAppProvisionError) as exc:
        _provider(handler).status(_canal())
    assert exc.value.code == "evolution_unreachable"
    assert "evo.local" not in str(exc.value)


def test_sem_credencial_falha_explicito():
    prov = EvolutionWhatsAppProvider(base_url="", api_key="", webhook_url="")
    with pytest.raises(WhatsAppProvisionError) as exc:
        prov.status(_canal())
    assert exc.value.code == "evolution_not_configured"


def test_ensure_instance_cria_com_webhook_quando_nao_existe():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[])
        if request.url.path == "/instance/create":
            corpo = json_module.loads(request.content)
            assert corpo["instanceName"] == "loja1-ab12"
            assert corpo["webhook"]["url"] == "http://n8n.local/webhook/whatsapp-ai"
            assert corpo["webhook"]["events"]
            return httpx.Response(201, json={"instance": {"instanceName": "loja1-ab12"}})
        return httpx.Response(200, json={})

    _provider(handler).ensure_instance(_canal())
    assert ("POST", "/instance/create") in chamadas


def test_ensure_instance_e_idempotente_quando_ja_existe():
    chamadas = []

    def handler(request):
        chamadas.append((request.method, request.url.path))
        if request.url.path == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": "loja1-ab12"}])
        return httpx.Response(200, json={})

    _provider(handler).ensure_instance(_canal())
    assert ("POST", "/instance/create") not in chamadas


def test_ensure_instance_sem_webhook_url_falha_explicito():
    prov = EvolutionWhatsAppProvider(
        base_url="http://evo.local",
        api_key="k",
        webhook_url="",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    )
    with pytest.raises(WhatsAppProvisionError) as exc:
        prov.ensure_instance(_canal())
    assert exc.value.code == "evolution_webhook_not_configured"
