"""Áudio do Vendedor: conversão e arquivo do áudio de saída (só Modo 2).

O navegador grava webm/opus; a Cloud API aceita ogg/opus. A conversão roda com
ffmpeg, e o arquivo fica no volume — mesmo padrão das fotos do Estoque. O banco
guarda só a referência, nunca o binário.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app import config

logger = logging.getLogger("chatbot.audio_humano")

MIME_OGG = "audio/ogg"
MIME_WEBM = "audio/webm"


class AudioMediaError(RuntimeError):
    """Falha ao validar, converter ou guardar o áudio de saída."""


@dataclass(frozen=True)
class AudioArmazenado:
    media_ref: str
    conteudo: bytes
    mime: str
    duracao_segundos: int | None


class AudioMediaPort(Protocol):
    """Port: converte e guarda o áudio; serve os bytes para o play."""

    def armazenar(
        self,
        conteudo: bytes,
        *,
        mime: str,
        loja_id: str,
        mensagem_id: str,
        duracao: float | None,
    ) -> AudioArmazenado: ...

    def ler(self, media_ref: str) -> tuple[bytes, str]: ...

    def apagar(self, media_ref: str) -> None: ...


def _validar_entrada(conteudo: bytes, duracao: float | None) -> None:
    if not conteudo:
        raise AudioMediaError("áudio vazio")
    if len(conteudo) > config.AUDIO_MAX_BYTES:
        raise AudioMediaError("áudio acima do limite")
    if duracao is not None and (
        duracao <= 0 or duracao > config.AUDIO_MAX_DURATION_SECONDS
    ):
        raise AudioMediaError("duração de áudio inválida")


def _converter_ogg_opus(conteudo: bytes) -> bytes:
    """webm/opus (navegador) → ogg/opus (Cloud). Ogg de entrada passa igual."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioMediaError("ffmpeg indisponível para converter áudio")
    try:
        proc = subprocess.run(
            [
                exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-vn",
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-f",
                "ogg",
                "pipe:1",
            ],
            input=conteudo,
            capture_output=True,
            timeout=config.AUDIO_TRANSCODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioMediaError("conversão de áudio expirou") from exc
    except OSError as exc:
        raise AudioMediaError("falha ao executar a conversão") from exc
    if proc.returncode != 0 or not proc.stdout:
        logger.warning("conversao de audio falhou rc=%s", proc.returncode)
        raise AudioMediaError("não foi possível converter o áudio")
    return proc.stdout


def _caminho_seguro(base: Path, media_ref: str) -> Path:
    """Resolve ``media_ref`` dentro de ``base``; recusa escapar do diretório."""
    raiz = base.resolve()
    destino = (raiz / media_ref).resolve()
    if destino != raiz and raiz not in destino.parents:
        raise AudioMediaError("referência de áudio inválida")
    return destino


@dataclass
class ArquivoAudioMedia:
    """Adapter real: ffmpeg + volume."""

    base_dir: str | None = None

    def _base(self) -> Path:
        return Path(self.base_dir or config.AUDIO_MEDIA_DIR)

    def armazenar(
        self,
        conteudo: bytes,
        *,
        mime: str,
        loja_id: str,
        mensagem_id: str,
        duracao: float | None,
    ) -> AudioArmazenado:
        _validar_entrada(conteudo, duracao)
        ogg = _converter_ogg_opus(conteudo)
        ref = f"{loja_id}/{mensagem_id}.ogg"
        caminho = _caminho_seguro(self._base(), ref)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(ogg)
        return AudioArmazenado(
            media_ref=ref,
            conteudo=ogg,
            mime=MIME_OGG,
            duracao_segundos=int(duracao) if duracao else None,
        )

    def ler(self, media_ref: str) -> tuple[bytes, str]:
        caminho = _caminho_seguro(self._base(), media_ref)
        if not caminho.is_file():
            raise AudioMediaError("áudio não encontrado")
        return caminho.read_bytes(), MIME_OGG

    def apagar(self, media_ref: str) -> None:
        try:
            _caminho_seguro(self._base(), media_ref).unlink(missing_ok=True)
        except (OSError, AudioMediaError):
            logger.warning("nao foi possivel apagar audio orfao")


@dataclass
class FakeAudioMedia:
    """Testes: não toca disco nem ffmpeg."""

    armazenados: list[AudioArmazenado] = field(default_factory=list)
    entradas: list[dict] = field(default_factory=list)
    falha: bool = False

    def armazenar(
        self,
        conteudo: bytes,
        *,
        mime: str,
        loja_id: str,
        mensagem_id: str,
        duracao: float | None,
    ) -> AudioArmazenado:
        if self.falha:
            raise AudioMediaError("fake: falha ao armazenar")
        _validar_entrada(conteudo, duracao)
        armazenado = AudioArmazenado(
            media_ref=f"{loja_id}/{mensagem_id}.ogg",
            conteudo=b"OGG" + conteudo[:16],
            mime=MIME_OGG,
            duracao_segundos=int(duracao) if duracao else None,
        )
        self.entradas.append({"mime": mime, "conteudo": conteudo})
        self.armazenados.append(armazenado)
        return armazenado

    def ler(self, media_ref: str) -> tuple[bytes, str]:
        for item in self.armazenados:
            if item.media_ref == media_ref:
                return item.conteudo, MIME_OGG
        raise AudioMediaError("áudio não encontrado")

    def apagar(self, media_ref: str) -> None:
        self.armazenados = [a for a in self.armazenados if a.media_ref != media_ref]


def get_audio_media_port() -> AudioMediaPort:
    """Dependency default; testes sobrescrevem via ``dependency_overrides``."""
    return ArquivoAudioMedia()


_SUFIXO_POR_MIME = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def sufixo_por_mime(mime: str | None) -> str:
    return _SUFIXO_POR_MIME.get(
        (mime or "").split(";")[0].strip().lower(), ".ogg"
    )


def get_transcription_provider():
    """Provider de transcrição do inbound, reusado para o áudio de saída.

    ``None`` quando a transcrição não está configurada — a rota responde 503 em
    vez de gastar com um provedor vazio.
    """
    if not config.AUDIO_TRANSCRIPTION_URL:
        return None
    from app.audio import HttpTranscriptionProvider

    return HttpTranscriptionProvider(
        config.AUDIO_TRANSCRIPTION_URL, config.AUDIO_TRANSCRIPTION_TOKEN
    )
