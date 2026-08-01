import pytest
from unittest.mock import ANY, MagicMock, patch

import httpx

from app.clients.portal import ConviteDonoRecusado, PortalClient, PortalIndisponivel


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=MagicMock(), response=self
            )

    def close(self):
        pass


def fake_requisicao(response_or_exc, retries=0):
    """Factory de `requisicao_com_retry` que retorna uma resposta fixa ou levanta."""
    def _requisicao(client, method, path, *, retries=0, backoff=0.1, sleeper=None, **kwargs):
        if isinstance(response_or_exc, Exception):
            raise response_or_exc
        return response_or_exc
    return _requisicao


def test_convidar_dono_409_levanta_conflito():
    # 409 do Portal = conflito real (e-mail pertence a outro tipo de acesso),
    # NÃO um "sucesso idempotente". Deve virar erro claro, não success.
    client = PortalClient(
        base_url="http://portal.test",
        service_token="test-token",
        retries=0,
        retry_backoff=0.1,
    )

    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 409
    fake_response.json.return_value = {
        "detail": "e-mail já pertence a outro tipo de acesso",
    }

    with patch(
        "app.clients.portal.requisicao_com_retry",
        return_value=fake_response,
    ):
        with pytest.raises(ConviteDonoRecusado) as caught:
            client.convidar_dono(
                email="vendedor@test.com",
                nome="Vendedor",
                loja_slug="loja-b",
            )

    assert "outro tipo de acesso" in str(caught.value)


def test_convidar_dono_200_with_email_pendente():
    client = PortalClient(
        base_url="http://portal.test",
        service_token="test-token",
        retries=0,
        retry_backoff=0.1,
    )

    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "usuario_id": "some-id",
        "email": "owner@test.com",
        "loja_slug": "loja-a",
        "expira_em": "2026-08-01T00:00:00+00:00",
        "email_pendente": True,
    }

    with patch(
        "app.clients.portal.requisicao_com_retry",
        return_value=fake_response,
    ):
        result = client.convidar_dono(
            email="owner@test.com",
            nome="Owner Test",
            loja_slug="loja-a",
        )

    assert result["email_pendente"] is True
    assert result["usuario_id"] == "some-id"


def test_convidar_dono_502_raises_portal_indisponivel():
    client = PortalClient(
        base_url="http://portal.test",
        service_token="test-token",
        retries=0,
        retry_backoff=0.1,
    )

    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 502
    fake_response.json.return_value = {"detail": "convite criado, mas o e-mail não pôde ser enviado"}
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=fake_response
    )

    with patch(
        "app.clients.portal.requisicao_com_retry",
        return_value=fake_response,
    ):
        with pytest.raises(PortalIndisponivel):
            client.convidar_dono(
                email="owner@test.com",
                nome="Owner Test",
                loja_slug="loja-a",
            )


def test_convidar_dono_unconfigured_raises():
    client = PortalClient(
        base_url="",
        service_token="",
    )
    with pytest.raises(PortalIndisponivel):
        client.convidar_dono("owner@test.com", "Owner", "loja-a")