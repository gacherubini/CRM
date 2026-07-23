"""PixelResolver — pull do Portal com cache e fallback."""

import httpx

from app.pixel import PixelResolver


def test_sem_portal_usa_fallback():
    r = PixelResolver("", fallback_pixel_id="123456789012345")
    assert r.resolve("loja-a") == "123456789012345"


def test_portal_responde_pixel():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"loja_slug": "loja-a", "pixel_id": "999888777666555", "enabled": True},
        )

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="111222333444555",
    )
    assert r.resolve("loja-a") == "999888777666555"


def test_portal_responde_flags_de_eventos():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "loja_slug": "loja-a",
                "pixel_id": "999888777666555",
                "enabled": True,
                "enviar_page_view": False,
                "enviar_lead": False,
            },
        )

    config = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
    ).resolve_config("loja-a")
    assert config.pixel_id == "999888777666555"
    assert config.enabled is True
    assert config.enviar_page_view is False
    assert config.enviar_lead is False


def test_portal_nao_aceita_pixel_id_nao_numerico():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "loja_slug": "loja-a",
                "pixel_id": "EAAB-token-invalido",
                "enabled": True,
            },
        )

    config = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
    ).resolve_config("loja-a")
    assert config.pixel_id == ""
    assert config.enabled is False


def test_portal_vazio_nao_usa_fallback():
    """Resposta 200 com pixel_id vazio = dono sem pixel nesta loja."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"loja_slug": "loja-a", "pixel_id": "", "enabled": False},
        )

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="111222333444555",
    )
    assert r.resolve("loja-a") == ""


def test_cache_evita_segunda_chamada():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"loja_slug": "loja-a", "pixel_id": "123456789012345", "enabled": True},
        )

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        cache_ttl=120,
    )
    assert r.resolve("loja-a") == "123456789012345"
    assert r.resolve("loja-a") == "123456789012345"
    assert calls["n"] == 1


def test_falha_http_usa_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="111222333444555",
    )
    assert r.resolve("loja-a") == "111222333444555"
