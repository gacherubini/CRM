"""Fix-wave Fase 1: cobre `HttpGraphProbe.validar_token` com rede mockada.

Usa `httpx.MockTransport` (injetado via o parâmetro `transport` de
`HttpGraphProbe.__init__`) para nunca bater na rede real. Cobre: sucesso,
erro 401 no formato da Graph API e falha de rede/timeout — em todos os
casos o token informado nunca deve aparecer na mensagem devolvida.
"""

from __future__ import annotations

import httpx

from app.control.graph_probe import HttpGraphProbe

TOKEN = "super-secret-token-nao-pode-vazar"


def test_validar_token_sucesso_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("access_token") == TOKEN
        return httpx.Response(200, json={"id": "123456"})

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "123456")

    assert ok is True
    assert motivo is None


def test_validar_token_401_invalid_oauth_token_nao_vaza_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid OAuth access token."}},
        )

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "123456")

    assert ok is False
    assert motivo is not None
    assert "Invalid OAuth access token" in motivo
    assert TOKEN not in motivo


def test_validar_token_timeout_retorna_mensagem_generica_sem_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "123456")

    assert ok is False
    assert motivo is not None
    assert TOKEN not in motivo


def test_validar_token_capi_missing_permission_no_pixel_fallback_me():
    """Token Events Manager: não lê Pixel (#100), mas GET /me autentica."""
    alvos: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        alvo = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        alvos.append(alvo)
        assert request.url.params.get("access_token") == TOKEN
        if alvo == "123456":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "(#100) Missing Permission",
                        "type": "OAuthException",
                        "code": 100,
                    }
                },
            )
        if alvo == "me":
            return httpx.Response(200, json={"id": "sys-user-1"})
        return httpx.Response(404, json={"error": {"message": "unexpected"}})

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "123456")

    assert ok is True
    assert motivo is None
    assert alvos == ["123456", "me"]


def test_validar_token_missing_permission_e_me_invalido_falha():
    def handler(request: httpx.Request) -> httpx.Response:
        alvo = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        if alvo == "123456":
            return httpx.Response(
                400,
                json={"error": {"message": "(#100) Missing Permission"}},
            )
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid OAuth access token."}},
        )

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "123456")

    assert ok is False
    assert motivo is not None
    assert "Invalid OAuth access token" in motivo
    assert TOKEN not in motivo


def test_validar_token_sem_pixel_usa_me():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/me")
        return httpx.Response(200, json={"id": "1"})

    probe = HttpGraphProbe(timeout=1.0, transport=httpx.MockTransport(handler))

    ok, motivo = probe.validar_token(TOKEN, "")

    assert ok is True
    assert motivo is None
