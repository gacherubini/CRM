import httpx
import pytest

from app.audio import AudioIndisponivel, GraphMediaDownloader


def _downloader(handler):
    return GraphMediaDownloader(
        base_url="https://graph.test/v21.0",
        token="tok-sistema",
        transport=httpx.MockTransport(handler),
    )


def test_baixa_em_dois_passos_com_bearer_nos_dois():
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append((str(request.url), request.headers.get("authorization")))
        if request.url.path.endswith("/media-123"):
            return httpx.Response(200, json={
                "url": "https://lookaside.test/asset?token=x",
                "mime_type": "audio/ogg",
            })
        return httpx.Response(200, content=b"OggS-bytes", headers={"content-type": "audio/ogg"})

    conteudo, mime = _downloader(handler).baixar("inst", "media-123", "audio/ogg; codecs=opus")

    assert conteudo == b"OggS-bytes"
    assert mime == "audio/ogg"
    assert len(vistos) == 2
    assert all(auth == "Bearer tok-sistema" for _, auth in vistos)


def test_url_expirada_vira_audio_indisponivel():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media-123"):
            return httpx.Response(200, json={"url": "https://lookaside.test/a", "mime_type": "audio/ogg"})
        return httpx.Response(410, text="expired")

    with pytest.raises(AudioIndisponivel):
        _downloader(handler).baixar("inst", "media-123")


def test_media_id_desconhecido_vira_audio_indisponivel():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "unknown"}})

    with pytest.raises(AudioIndisponivel):
        _downloader(handler).baixar("inst", "sumiu")
