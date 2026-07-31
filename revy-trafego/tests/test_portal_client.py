from __future__ import annotations

import json
import re

import httpx
import pytest

from app.clients import portal as portal_module
from app.clients.portal import PortalClient, PortalIndisponivel


def _mock_http_client(monkeypatch, handler):
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(portal_module.httpx, "Client", factory)


def test_convidar_dono_posta_payload_e_chave_idempotente_sem_pii(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"status": "pending"})

    _mock_http_client(monkeypatch, handler)
    client = PortalClient("https://portal.example", "service-secret", retries=0)

    result = client.convidar_dono(
        " Dono@Example.COM ", "  Maria   da Silva  ", " Loja-Um "
    )

    assert result == {"status": "pending"}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/internal/v1/lojistas/convite"
    assert request.headers["X-Service-Token"] == "service-secret"
    key = request.headers["Idempotency-Key"]
    assert re.fullmatch(r"revy-owner-invite-[0-9a-f]{64}", key)
    assert "dono" not in key.lower()
    assert json.loads(request.content) == {
        "email": "dono@example.com",
        "nome": "Maria da Silva",
        "loja_slug": "loja-um",
    }


def test_convidar_dono_nao_repete_post_transitorio_sem_idempotencia_no_portal(
    monkeypatch,
):
    keys = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers["Idempotency-Key"])
        return httpx.Response(503, text="temporarily unavailable")

    _mock_http_client(monkeypatch, handler)
    client = PortalClient(
        "https://portal.example",
        "service-secret",
        retries=1,
        retry_backoff=0.25,
        sleeper=sleeps.append,
    )

    with pytest.raises(PortalIndisponivel) as caught:
        client.convidar_dono("dono@example.com", "Dono", "loja")

    assert str(caught.value) == (
        "N\u00e3o foi poss\u00edvel solicitar o convite no portal agora"
    )
    assert len(keys) == 1
    assert sleeps == []


def test_convidar_dono_erro_e_sanitizado(monkeypatch):
    sensitive_email = "segredo@example.com"
    response_secret = "token-super-secreto"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=response_secret)

    _mock_http_client(monkeypatch, handler)
    client = PortalClient("https://portal.example", "service-secret", retries=0)

    with pytest.raises(PortalIndisponivel) as caught:
        client.convidar_dono(sensitive_email, "Nome", "loja")

    message = str(caught.value)
    assert sensitive_email not in message
    assert response_secret not in message
    assert "service-secret" not in message
    assert message == "N\u00e3o foi poss\u00edvel solicitar o convite no portal agora"


def test_convidar_dono_exige_integracao_configurada():
    with pytest.raises(PortalIndisponivel, match="ainda n\u00e3o configurada"):
        PortalClient("", "").convidar_dono("dono@example.com", "Dono", "loja")
