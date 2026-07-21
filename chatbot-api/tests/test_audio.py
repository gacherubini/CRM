import base64
import json
import logging
from pathlib import Path

import httpx

from app import config
from app.audio import (
    AudioIndisponivel,
    AudioProcessor,
    EvolutionMediaDownloader,
    NoopTranscriptionProvider,
    get_audio_processor,
)
from app.main import app


class DownloaderFake:
    def __init__(self, conteudo=b"audio-opus", mime="audio/ogg"):
        self.conteudo = conteudo
        self.mime = mime
        self.chamadas = []

    def baixar(self, instancia, message_id, mime_declarado=None):
        self.chamadas.append((instancia, message_id, mime_declarado))
        return self.conteudo, self.mime


class ProviderFake:
    def __init__(self, texto="quero saber o preço da moto"):
        self.texto = texto
        self.arquivo: Path | None = None
        self.conteudo = None

    def transcrever(self, arquivo, mime_type):
        assert arquivo.exists()
        assert mime_type == "audio/ogg"
        self.arquivo = arquivo
        self.conteudo = arquivo.read_bytes()
        return self.texto


class ProviderComErro:
    def __init__(self):
        self.arquivo = None

    def transcrever(self, arquivo, mime_type):
        self.arquivo = arquivo
        assert arquivo.exists()
        raise AudioIndisponivel("erro privado do provider")


def _payload(instancia, **alteracoes):
    dados = {
        "instance": instancia,
        "provider_message_id": "MSG-AUDIO-1",
        "mime_type": "audio/ogg; codecs=opus",
        "duration_seconds": 12,
    }
    dados.update(alteracoes)
    return dados


def test_audio_transcreve_e_remove_arquivo_temporario(client, loja_a):
    downloader = DownloaderFake()
    provider = ProviderFake()
    processor = AudioProcessor(downloader, provider)
    app.dependency_overrides[get_audio_processor] = lambda: processor
    try:
        resposta = client.post(
            "/webhook/audio/transcrever",
            json=_payload(loja_a["instance"]),
        )
    finally:
        app.dependency_overrides.pop(get_audio_processor, None)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "transcrito": True,
        "texto": "quero saber o preço da moto",
        "fallback": None,
    }
    assert downloader.chamadas == [
        (loja_a["instance"], "MSG-AUDIO-1", "audio/ogg; codecs=opus")
    ]
    assert provider.conteudo == b"audio-opus"
    assert provider.arquivo is not None and not provider.arquivo.exists()


def test_audio_instancia_desconhecida_nao_faz_download(client):
    downloader = DownloaderFake()
    processor = AudioProcessor(downloader, ProviderFake())
    app.dependency_overrides[get_audio_processor] = lambda: processor
    try:
        resposta = client.post(
            "/webhook/audio/transcrever",
            json=_payload("instancia-inexistente"),
        )
    finally:
        app.dependency_overrides.pop(get_audio_processor, None)

    assert resposta.status_code == 404
    assert downloader.chamadas == []


def test_audio_reentregue_nao_transcreve_novamente(client, loja_a):
    client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": "5511988887777",
            "texto": "[Áudio não transcrito]",
            "provider_message_id": "MSG-AUDIO-1",
            "tipo": "audio",
        },
    )
    downloader = DownloaderFake()
    processor = AudioProcessor(downloader, ProviderFake())
    app.dependency_overrides[get_audio_processor] = lambda: processor
    try:
        resposta = client.post(
            "/webhook/audio/transcrever",
            json=_payload(loja_a["instance"]),
        )
    finally:
        app.dependency_overrides.pop(get_audio_processor, None)

    assert resposta.status_code == 200
    assert resposta.json()["duplicada"] is True
    assert downloader.chamadas == []


def test_audio_provider_indisponivel_retorna_fallback_sem_vazar_dados(
    client, loja_a, caplog
):
    segredo_audio = b"conteudo-pessoal-do-audio"
    provider = ProviderComErro()
    processor = AudioProcessor(DownloaderFake(segredo_audio), provider)
    app.dependency_overrides[get_audio_processor] = lambda: processor
    caplog.set_level(logging.WARNING, logger="chatbot.audio")
    try:
        resposta = client.post(
            "/webhook/audio/transcrever",
            json=_payload(loja_a["instance"], provider_message_id="ID-PRIVADO-1"),
        )
    finally:
        app.dependency_overrides.pop(get_audio_processor, None)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "transcrito": False,
        "texto": None,
        "fallback": config.AUDIO_FALLBACK_TEXT,
    }
    assert provider.arquivo is not None and not provider.arquivo.exists()
    for sensivel in (
        segredo_audio.decode(),
        loja_a["instance"],
        "ID-PRIVADO-1",
        "erro privado do provider",
    ):
        assert sensivel not in caplog.text


def test_audio_duracao_excessiva_falha_antes_do_download(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_MAX_DURATION_SECONDS", 30)
    downloader = DownloaderFake()
    resultado = AudioProcessor(downloader, ProviderFake()).processar(
        "loja1", "MSG-1", "audio/ogg", 31
    )

    assert resultado["transcrito"] is False
    assert downloader.chamadas == []


def test_provider_none_retorna_fallback_e_nao_retem_audio():
    provider = NoopTranscriptionProvider()
    resultado = AudioProcessor(DownloaderFake(), provider).processar(
        "loja1", "MSG-1", "audio/ogg", 10
    )

    assert resultado == {
        "transcrito": False,
        "texto": None,
        "fallback": config.AUDIO_FALLBACK_TEXT,
    }


def test_downloader_evolution_autentica_e_usa_contrato_oficial():
    conteudo = b"audio-curto"

    def handler(request: httpx.Request):
        assert request.url.path == "/chat/getBase64FromMediaMessage/loja1"
        assert request.headers["apikey"] == "evolution-segredo"
        assert json.loads(request.content) == {
            "message": {"key": {"id": "MSG-1"}},
            "convertToMp4": False,
        }
        return httpx.Response(
            200,
            json={
                "mediaType": "audioMessage",
                "size": {"fileLength": str(len(conteudo))},
                "mimetype": "audio/ogg",
                "base64": base64.b64encode(conteudo).decode(),
            },
        )

    downloader = EvolutionMediaDownloader(
        "https://evolution.test",
        "evolution-segredo",
        transport=httpx.MockTransport(handler),
    )

    baixado, mime = downloader.baixar("loja1", "MSG-1", "audio/ogg")

    assert baixado == conteudo
    assert mime == "audio/ogg"


def test_downloader_rejeita_mime_e_base64_invalidos():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"mimetype": "audio/ogg", "base64": "%%%invalido%%%"},
        )

    downloader = EvolutionMediaDownloader(
        "https://evolution.test",
        "segredo",
        transport=httpx.MockTransport(handler),
    )

    try:
        downloader.baixar("loja1", "MSG-1", "image/jpeg")
        assert False, "mime de imagem deveria ser rejeitado"
    except AudioIndisponivel:
        pass
    try:
        downloader.baixar("loja1", "MSG-1", "audio/ogg")
        assert False, "base64 inválido deveria ser rejeitado"
    except AudioIndisponivel:
        pass


def test_downloader_rejeita_tamanho_declarado_acima_do_limite(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_MAX_BYTES", 4)

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "mimetype": "audio/ogg",
                "size": {"fileLength": "5"},
                "base64": base64.b64encode(b"12345").decode(),
            },
        )

    downloader = EvolutionMediaDownloader(
        "https://evolution.test",
        "segredo",
        transport=httpx.MockTransport(handler),
    )

    try:
        downloader.baixar("loja1", "MSG-1", "audio/ogg")
        assert False, "áudio acima do limite deveria ser rejeitado"
    except AudioIndisponivel:
        pass


def test_audio_payload_invalido_nao_ecoa_identificador(client, loja_a):
    identificador = "ID-SENSIVEL-" * 40
    resposta = client.post(
        "/webhook/audio/transcrever",
        json=_payload(loja_a["instance"], provider_message_id=identificador),
    )

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "payload do webhook inválido"}
    assert identificador not in resposta.text
