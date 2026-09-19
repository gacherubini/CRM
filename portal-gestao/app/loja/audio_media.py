"""Leitura do áudio de uma mensagem, pelo Portal (proxy autenticado).

O navegador nunca recebe token do Chatbot: o Portal valida sessão e escopo e
repassa o pedido — inclusive a requisição parcial (Range) que o player usa para
arrastar o áudio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from fastapi import Request

from app.clients.chatbot import ChatbotIndisponivel
from app.config import settings


class AudioMediaNaoEncontrada(RuntimeError):
    """O áudio não existe ou não é da Loja da sessão."""


@dataclass(frozen=True)
class AudioMidia:
    status: int
    content: bytes
    media_type: str
    content_range: str | None = None


class AudioMediaPort(Protocol):
    """Port: baixa os bytes de um áudio da conversa."""

    def baixar(
        self,
        telefone: str,
        mensagem_id: str,
        *,
        range_header: str | None = None,
    ) -> AudioMidia: ...


class HttpAudioMedia:
    """Adapter HTTP → Chatbot ``GET /v1/conversas/{telefone}/mensagens/{id}/midia``."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (
            base_url if base_url is not None else settings.chatbot_url
        ).rstrip("/")
        self.token = token if token is not None else settings.chatbot_token
        self.timeout = (
            timeout if timeout is not None else settings.request_timeout_audio
        )

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.token)

    def baixar(
        self,
        telefone: str,
        mensagem_id: str,
        *,
        range_header: str | None = None,
    ) -> AudioMidia:
        if not self.configurado:
            raise ChatbotIndisponivel("Integração do chatbot ainda não configurada")
        digitos = "".join(c for c in (telefone or "") if c.isdigit())
        headers = {"Authorization": f"Bearer {self.token}"}
        if range_header:
            headers["Range"] = range_header
        try:
            with httpx.Client(
                base_url=self.base_url, headers=headers, timeout=self.timeout
            ) as client:
                resposta = client.get(
                    f"/v1/conversas/{digitos}/mensagens/{mensagem_id}/midia"
                )
        except httpx.HTTPError:
            raise ChatbotIndisponivel(
                "Não foi possível carregar o áudio agora"
            ) from None
        if resposta.status_code == 404:
            raise AudioMediaNaoEncontrada("áudio não encontrado")
        if resposta.status_code >= 400:
            raise ChatbotIndisponivel("Não foi possível carregar o áudio agora")
        return AudioMidia(
            status=resposta.status_code,
            content=resposta.content,
            media_type=resposta.headers.get("content-type", "audio/ogg"),
            content_range=resposta.headers.get("content-range"),
        )


def get_audio_media_port(request: Request) -> AudioMediaPort:
    """Port do Chatbot **da loja da sessão**, como o port de envio humano."""
    from app.loja import identity as loja_identity

    try:
        sessao = request.session
    except (AssertionError, AttributeError):  # sem SessionMiddleware (testes)
        sessao = None
    slug = loja_identity.session_loja_slug(sessao)
    return HttpAudioMedia(token=settings.chatbot_token_para(slug))
