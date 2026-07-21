"""Download e transcrição efêmeros de áudio recebido pelo WhatsApp."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import tempfile
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app import config


logger = logging.getLogger("chatbot.audio")

MIMES_AUDIO_PERMITIDOS = frozenset(
    {
        "audio/aac",
        "audio/amr",
        "audio/m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/webm",
        "audio/x-wav",
    }
)


class AudioIndisponivel(RuntimeError):
    pass


class MediaDownloader(Protocol):
    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]: ...


class TranscriptionProvider(Protocol):
    def transcrever(self, arquivo: Path, mime_type: str) -> str: ...


def normalizar_mime(valor: object) -> str:
    mime = str(valor or "").split(";", 1)[0].strip().lower()
    if mime not in MIMES_AUDIO_PERMITIDOS:
        raise AudioIndisponivel("tipo de áudio não permitido")
    return mime


class EvolutionMediaDownloader:
    """Obtém base64 na Evolution; a apikey nunca passa pelo n8n nem por logs."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or config.AUDIO_EVOLUTION_URL).rstrip("/")
        self.api_key = api_key or config.AUDIO_EVOLUTION_API_KEY
        self.timeout = timeout or config.AUDIO_DOWNLOAD_TIMEOUT
        self.transport = transport

    def baixar(
        self,
        instancia: str,
        message_id: str,
        mime_declarado: str | None = None,
    ) -> tuple[bytes, str]:
        if not self.base_url or not self.api_key:
            raise AudioIndisponivel("download de áudio não configurado")
        if mime_declarado:
            normalizar_mime(mime_declarado)

        limite_json = ((config.AUDIO_MAX_BYTES + 2) // 3 * 4) + 64 * 1024
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"apikey": self.api_key},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST",
                    f"/chat/getBase64FromMediaMessage/{quote(instancia, safe='')}",
                    json={
                        "message": {"key": {"id": message_id}},
                        "convertToMp4": False,
                    },
                ) as resposta:
                    resposta.raise_for_status()
                    bruto = bytearray()
                    for parte in resposta.iter_bytes():
                        bruto.extend(parte)
                        if len(bruto) > limite_json:
                            raise AudioIndisponivel("resposta de mídia acima do limite")
        except AudioIndisponivel:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("não foi possível obter o áudio") from exc

        try:
            payload = json.loads(bruto)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AudioIndisponivel("resposta de mídia inválida") from exc
        return self._decodificar(payload, mime_declarado)

    @staticmethod
    def _decodificar(
        payload: object, mime_declarado: str | None
    ) -> tuple[bytes, str]:
        if not isinstance(payload, dict):
            raise AudioIndisponivel("resposta de mídia inválida")
        dados = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        base64_texto = dados.get("base64")
        if not isinstance(base64_texto, str) or not base64_texto:
            raise AudioIndisponivel("mídia ausente na resposta")

        mime_data_uri = None
        if base64_texto.startswith("data:") and ";base64," in base64_texto[:160]:
            cabecalho, base64_texto = base64_texto.split(",", 1)
            mime_data_uri = cabecalho[5:].split(";", 1)[0]

        mime = normalizar_mime(
            dados.get("mimetype")
            or dados.get("mimeType")
            or mime_data_uri
            or mime_declarado
        )
        tamanho = dados.get("size")
        if isinstance(tamanho, dict):
            tamanho = tamanho.get("fileLength")
        if tamanho not in (None, ""):
            try:
                if int(tamanho) > config.AUDIO_MAX_BYTES:
                    raise AudioIndisponivel("áudio acima do limite")
            except (TypeError, ValueError) as exc:
                raise AudioIndisponivel("tamanho de áudio inválido") from exc

        limite_base64 = ((config.AUDIO_MAX_BYTES + 2) // 3 * 4) + 4
        if len(base64_texto) > limite_base64:
            raise AudioIndisponivel("áudio acima do limite")
        try:
            conteudo = base64.b64decode(base64_texto, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AudioIndisponivel("base64 de áudio inválido") from exc
        if not conteudo or len(conteudo) > config.AUDIO_MAX_BYTES:
            raise AudioIndisponivel("tamanho de áudio inválido")
        return conteudo, mime


class NoopTranscriptionProvider:
    def transcrever(self, arquivo: Path, mime_type: str) -> str:
        raise AudioIndisponivel("transcrição de áudio não configurada")


class HttpTranscriptionProvider:
    """Contrato genérico: multipart `file`; resposta JSON com `text` ou `texto`."""

    def __init__(self, url: str, token: str = "", timeout: float = 15):
        self.url = url
        self.token = token
        self.timeout = timeout

    def transcrever(self, arquivo: Path, mime_type: str) -> str:
        if not self.url:
            raise AudioIndisponivel("provider de transcrição não configurado")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            with arquivo.open("rb") as stream:
                resposta = httpx.post(
                    self.url,
                    headers=headers,
                    files={"file": (arquivo.name, stream, mime_type)},
                    data={"language": "pt-BR"},
                    timeout=self.timeout,
                )
            resposta.raise_for_status()
            payload = resposta.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise AudioIndisponivel("provider de transcrição indisponível") from exc
        texto = None
        if isinstance(payload, dict):
            texto = payload.get("text") or payload.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise AudioIndisponivel("transcrição vazia")
        return texto.strip()


class AudioProcessor:
    def __init__(self, downloader: MediaDownloader, provider: TranscriptionProvider):
        self.downloader = downloader
        self.provider = provider

    def processar(
        self,
        instancia: str,
        message_id: str,
        mime_type: str | None,
        duration_seconds: float | None,
    ) -> dict:
        try:
            if duration_seconds is not None and (
                duration_seconds <= 0
                or duration_seconds > config.AUDIO_MAX_DURATION_SECONDS
            ):
                raise AudioIndisponivel("duração de áudio inválida")
            conteudo, mime = self.downloader.baixar(
                instancia, message_id, mime_type
            )
            sufixo = {
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/webm": ".webm",
                "audio/wav": ".wav",
            }.get(mime, ".audio")
            with tempfile.TemporaryDirectory(prefix="revy-audio-") as diretorio:
                arquivo = Path(diretorio) / f"entrada{sufixo}"
                arquivo.write_bytes(conteudo)
                texto = self.provider.transcrever(arquivo, mime).strip()
            if not texto or len(texto) > config.WEBHOOK_MAX_TEXT_CHARS or "\x00" in texto:
                raise AudioIndisponivel("transcrição inválida")
            return {"transcrito": True, "texto": texto, "fallback": None}
        except Exception:
            logger.warning("áudio não transcrito")
            return {
                "transcrito": False,
                "texto": None,
                "fallback": config.AUDIO_FALLBACK_TEXT,
            }


def get_audio_processor() -> AudioProcessor:
    provider_nome = config.AUDIO_TRANSCRIPTION_PROVIDER.strip().lower()
    if provider_nome == "http":
        provider: TranscriptionProvider = HttpTranscriptionProvider(
            config.AUDIO_TRANSCRIPTION_URL,
            config.AUDIO_TRANSCRIPTION_TOKEN,
            config.AUDIO_TRANSCRIPTION_TIMEOUT,
        )
    else:
        provider = NoopTranscriptionProvider()
    return AudioProcessor(EvolutionMediaDownloader(), provider)
