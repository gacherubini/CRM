"""PixelResolver — pull do Portal com cache e fallback."""

import httpx

from app.pixel import PixelResolver


def test_sem_portal_usa_fallback():
    r = PixelResolver("", fallback_pixel_id="123")
    assert r.resolve("loja-a") == "123"


def test_portal_responde_pixel():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"loja_slug": "loja-a", "pixel_id": "999", "enabled": True},
        )

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="fallback",
    )
    assert r.resolve("loja-a") == "999"


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
        fallback_pixel_id="fallback",
    )
    assert r.resolve("loja-a") == ""


def test_cache_evita_segunda_chamada():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"loja_slug": "loja-a", "pixel_id": "1", "enabled": True},
        )

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        cache_ttl=120,
    )
    assert r.resolve("loja-a") == "1"
    assert r.resolve("loja-a") == "1"
    assert calls["n"] == 1


def test_falha_http_usa_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    r = PixelResolver(
        "http://portal",
        transport=httpx.MockTransport(handler),
        fallback_pixel_id="fb",
    )
    assert r.resolve("loja-a") == "fb"
