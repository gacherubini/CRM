import httpx

from app.audio import HttpTranscriptionProvider, processador_de_audio


def test_modo_1_nao_transcreve():
    assert processador_de_audio(1) is None


def test_modo_2_devolve_processador(monkeypatch):
    monkeypatch.setattr("app.audio.config.GRAPH_TOKEN", "tok")
    monkeypatch.setattr("app.audio.config.AUDIO_TRANSCRIPTION_URL", "https://stt.test/v1/audio/transcriptions")
    assert processador_de_audio(2) is not None


def test_language_e_iso_639_1(tmp_path):
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["body"] = request.content
        return httpx.Response(200, json={"text": "quero ver a biz"})

    arquivo = tmp_path / "a.ogg"
    arquivo.write_bytes(b"OggS")

    provider = HttpTranscriptionProvider(
        url="https://stt.test/v1/audio/transcriptions",
        token="k",
        transport=httpx.MockTransport(handler),
    )
    assert provider.transcrever(arquivo, "audio/ogg") == "quero ver a biz"

    corpo = capturado["body"]
    assert b'name="language"\r\n\r\npt\r\n' in corpo
    assert b"pt-BR" not in corpo
