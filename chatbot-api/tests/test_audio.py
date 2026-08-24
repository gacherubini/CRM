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
    HttpTranscriptionProvider,
    NoopTranscriptionProvider,
    extrair_sinais,
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


# --- Gate de confiança pós-transcrição (o Whisper alucina em trecho mudo) ---


def _segmento(**alteracoes):
    dados = {
        "start": 0.0,
        "end": 4.0,
        "no_speech_prob": 0.02,
        "avg_logprob": -0.25,
        "compression_ratio": 1.4,
    }
    dados.update(alteracoes)
    return dados


def _provider_verbose(payload, capturado=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capturado is not None:
            capturado["body"] = request.content
        return httpx.Response(200, json=payload)

    return HttpTranscriptionProvider(
        url="https://stt.test/v1/audio/transcriptions",
        token="k",
        transport=httpx.MockTransport(handler),
    )


def _processar(payload, capturado=None):
    """Roda o caminho real do Modo 2: sem duração no inbound (`None`)."""
    processor = AudioProcessor(DownloaderFake(), _provider_verbose(payload, capturado))
    return processor.processar("loja1", "MSG-1", "audio/ogg", None)


def _fallback():
    return {"transcrito": False, "texto": None, "fallback": config.AUDIO_FALLBACK_TEXT}


def test_gate_pede_verbose_json_ao_provider():
    capturado = {}
    resultado = _processar(
        {"text": "quero ver a biz", "duration": 3.0, "segments": [_segmento()]},
        capturado,
    )

    assert resultado["transcrito"] is True
    assert b'name="response_format"\r\n\r\nverbose_json\r\n' in capturado["body"]
    assert b'name="language"\r\n\r\npt\r\n' in capturado["body"]


def test_gate_reprova_alucinacao_em_silencio():
    resultado = _processar(
        {
            "text": "Vamos falar sobre o financiamento da moto.",
            "duration": 2.0,
            "segments": [_segmento(end=2.0, no_speech_prob=0.94)],
        }
    )

    assert resultado == _fallback()


def test_gate_reprova_texto_em_loop():
    resultado = _processar(
        {
            "text": "sim sim sim sim sim sim sim sim",
            "duration": 5.0,
            "segments": [_segmento(end=5.0, compression_ratio=3.7)],
        }
    )

    assert resultado == _fallback()


def test_gate_reprova_baixa_confianca():
    resultado = _processar(
        {
            "text": "trezentos reais por mês",
            "duration": 3.0,
            "segments": [_segmento(end=3.0, avg_logprob=-1.6)],
        }
    )

    assert resultado == _fallback()


def test_gate_reprova_frase_conhecida_de_alucinacao():
    for frase in (
        "Legendas pela comunidade Amara.org",
        "  obrigado por assistir!  ",
        "Inscreva-se no canal. Inscreva-se no canal.",
    ):
        resultado = _processar(
            {"text": frase, "duration": 2.0, "segments": [_segmento(end=2.0)]}
        )
        assert resultado == _fallback(), frase


def test_gate_deixa_passar_transcricao_boa_sem_alterar_o_texto():
    resultado = _processar(
        {
            "text": "  Quero saber o preço da Biz 125  ",
            "duration": 6.0,
            "segments": [
                _segmento(start=0.0, end=3.0),
                _segmento(start=3.0, end=6.0, no_speech_prob=0.1),
            ],
        }
    )

    assert resultado == {
        "transcrito": True,
        "texto": "Quero saber o preço da Biz 125",
        "fallback": None,
    }


def test_gate_falha_aberto_quando_o_payload_nao_traz_os_sinais(caplog):
    caplog.set_level(logging.INFO, logger="chatbot.audio")
    resultado = _processar({"text": "quero ver a biz"})

    assert resultado == {
        "transcrito": True,
        "texto": "quero ver a biz",
        "fallback": None,
    }
    assert "sem sinal" in caplog.text


def test_gate_reprova_duracao_acima_do_teto_mesmo_sem_duracao_no_inbound(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_MAX_DURATION_SECONDS", 30)
    resultado = _processar(
        {
            "text": "áudio longo demais",
            "duration": 240.0,
            "segments": [_segmento(end=240.0)],
        }
    )

    assert resultado == _fallback()


def test_gate_nao_loga_o_texto_transcrito(caplog):
    caplog.set_level(logging.INFO, logger="chatbot.audio")
    segredo = "meu nome é fulano e meu cpf é 111"
    resultado = _processar(
        {"text": segredo, "duration": 2.0, "segments": [_segmento(no_speech_prob=0.99)]}
    )

    assert resultado == _fallback()
    assert segredo not in caplog.text
    assert "fulano" not in caplog.text
    assert "no_speech_prob" in caplog.text


def test_agregacao_pondera_por_duracao_e_pega_o_pior_loop():
    # 20 s de fala limpa + 0,4 s de silêncio: a média ponderada não reprova.
    sinais = extrair_sinais(
        {
            "duration": 20.4,
            "segments": [
                _segmento(start=0.0, end=20.0, no_speech_prob=0.01, avg_logprob=-0.2),
                _segmento(start=20.0, end=20.4, no_speech_prob=0.95, avg_logprob=-1.9),
            ],
        }
    )
    assert sinais.no_speech_prob < config.AUDIO_NO_SPEECH_PROB_MAX
    assert sinais.avg_logprob > config.AUDIO_AVG_LOGPROB_MIN
    assert sinais.duration_seconds == 20.4

    # compression_ratio é o pior segmento: um loop no meio não se dilui.
    sinais = extrair_sinais(
        {
            "segments": [
                _segmento(start=0.0, end=10.0, compression_ratio=1.2),
                _segmento(start=10.0, end=12.0, compression_ratio=4.1),
            ]
        }
    )
    assert sinais.compression_ratio == 4.1


def test_gate_ignora_campos_lixo_do_provider():
    sinais = extrair_sinais(
        {
            "duration": "abc",
            "segments": [
                {"no_speech_prob": None, "avg_logprob": "x", "compression_ratio": True},
                "não é dicionário",
            ],
        }
    )

    assert sinais == type(sinais)()


def test_audio_payload_invalido_nao_ecoa_identificador(client, loja_a):
    identificador = "ID-SENSIVEL-" * 40
    resposta = client.post(
        "/webhook/audio/transcrever",
        json=_payload(loja_a["instance"], provider_message_id=identificador),
    )

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "payload do webhook inválido"}
    assert identificador not in resposta.text


def test_multipart_leva_o_model_porque_o_groq_exige():
    """Sem `model` o Groq responde 400 e TODO áudio cairia no fallback.

    O modo de falha seria calado — um bot que parece simplesmente não ouvir —
    então o campo tem de sair por default, não por configuração lembrada.
    """
    capturado = {}
    resultado = _processar(
        {"text": "tem a biz 125?", "duration": 3.0, "segments": [_segmento()]},
        capturado,
    )

    assert resultado["transcrito"] is True
    assert b'name="model"\r\n\r\nwhisper-large-v3\r\n' in capturado["body"]
    assert b'name="temperature"\r\n\r\n0\r\n' in capturado["body"]


def test_model_vazio_nao_manda_o_campo():
    """Provider fora do padrão da OpenAI não recebe campo que não pediu."""
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["body"] = request.content
        return httpx.Response(200, json={"text": "oi"})

    provider = HttpTranscriptionProvider(
        url="https://outro.test/transcrever",
        transport=httpx.MockTransport(handler),
        model="",
    )
    AudioProcessor(DownloaderFake(), provider).processar("loja1", "MSG-1", "audio/ogg", None)

    assert b'name="model"' not in capturado["body"]
