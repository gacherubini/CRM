"""Port de envio humano de texto no Atendimento (Fase 4 lean).

O Chatbot é dono da mensagem (persistência + canal). O Portal autoriza,
audita o pedido e nunca escolhe outra loja/canal arbitrária no payload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

import httpx

from app.clients._retry import requisicao_com_retry
from app.clients.chatbot import ChatbotIndisponivel
from app.config import settings


class MensagemHumanaErro(RuntimeError):
    """Falha de negócio ou integração no envio humano."""


class MensagemHumanaNaoAutorizada(MensagemHumanaErro):
    pass


class MensagemHumanaNaoEncontrada(MensagemHumanaErro):
    pass


@dataclass(frozen=True)
class HumanMessageResult:
    telefone: str
    texto: str
    idempotency_key: str
    duplicada: bool
    bot_ativo: bool
    mensagem_id: str | None = None
    enviado: bool = False
    canal_id: str | None = None


class HumanMessagingPort(Protocol):
    """Port: envia texto humano na conversa da loja autenticada."""

    def enviar_texto(
        self,
        telefone: str,
        texto: str,
        *,
        idempotency_key: str,
        instance: str | None = None,
        ator: str | None = None,
    ) -> HumanMessageResult:
        ...


@dataclass
class InMemoryHumanMessagingPort:
    """Adapter de teste: grava em memória, idempotente por chave."""

    enviadas: list[dict] = field(default_factory=list)
    _por_chave: dict[str, HumanMessageResult] = field(default_factory=dict)
    indisponivel: bool = False
    rejeitar_telefone: set[str] = field(default_factory=set)

    def enviar_texto(
        self,
        telefone: str,
        texto: str,
        *,
        idempotency_key: str,
        instance: str | None = None,
        ator: str | None = None,
    ) -> HumanMessageResult:
        if self.indisponivel:
            raise ChatbotIndisponivel("Não foi possível enviar a mensagem agora")
        digitos = "".join(c for c in (telefone or "") if c.isdigit())
        if digitos in self.rejeitar_telefone:
            raise MensagemHumanaNaoEncontrada("conversa não encontrada")
        if idempotency_key in self._por_chave:
            cached = self._por_chave[idempotency_key]
            return HumanMessageResult(
                telefone=cached.telefone,
                texto=cached.texto,
                idempotency_key=cached.idempotency_key,
                duplicada=True,
                bot_ativo=cached.bot_ativo,
                mensagem_id=cached.mensagem_id,
                enviado=cached.enviado,
                canal_id=cached.canal_id,
            )
        texto_limpo = (texto or "").strip()
        if not texto_limpo:
            raise MensagemHumanaErro("texto vazio")
        result = HumanMessageResult(
            telefone=digitos,
            texto=texto_limpo,
            idempotency_key=idempotency_key,
            duplicada=False,
            bot_ativo=False,
            mensagem_id=str(uuid4()),
            enviado=True,
            canal_id=None,
        )
        self._por_chave[idempotency_key] = result
        self.enviadas.append(
            {
                "telefone": digitos,
                "texto": texto_limpo,
                "idempotency_key": idempotency_key,
                "instance": instance,
                "ator": ator,
            }
        )
        return result


class HttpHumanMessagingPort:
    """Adapter HTTP → Chatbot ``POST /v1/conversas/{telefone}/mensagens``."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        *,
        retries: int | None = None,
        retry_backoff: float | None = None,
    ):
        self.base_url = (base_url if base_url is not None else settings.chatbot_url).rstrip(
            "/"
        )
        self.token = token if token is not None else settings.chatbot_token
        self.timeout = timeout if timeout is not None else settings.request_timeout
        self.retries = (
            settings.request_retries if retries is None else max(0, retries)
        )
        self.retry_backoff = (
            settings.request_retry_backoff
            if retry_backoff is None
            else max(0.0, retry_backoff)
        )

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.token)

    def enviar_texto(
        self,
        telefone: str,
        texto: str,
        *,
        idempotency_key: str,
        instance: str | None = None,
        ator: str | None = None,
    ) -> HumanMessageResult:
        if not self.configurado:
            raise ChatbotIndisponivel("Integração do chatbot ainda não configurada")
        digitos = "".join(c for c in (telefone or "") if c.isdigit())
        payload: dict = {
            "texto": texto,
            "idempotency_key": idempotency_key,
        }
        if instance:
            payload["instance"] = instance
        if ator:
            payload["ator"] = ator
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(
                base_url=self.base_url, headers=headers, timeout=self.timeout
            ) as client:
                resposta = requisicao_com_retry(
                    client,
                    "POST",
                    f"/v1/conversas/{digitos}/mensagens",
                    retries=self.retries,
                    backoff=self.retry_backoff,
                    json=payload,
                )
                if resposta.status_code == 404:
                    raise MensagemHumanaNaoEncontrada("conversa não encontrada")
                if resposta.status_code in {401, 403}:
                    raise MensagemHumanaNaoAutorizada("envio não autorizado")
                if resposta.status_code == 423:
                    raise MensagemHumanaErro("loja não operacional")
                resposta.raise_for_status()
                dados = resposta.json()
        except MensagemHumanaErro:
            raise
        except (httpx.HTTPError, ValueError):
            raise ChatbotIndisponivel(
                "Não foi possível enviar a mensagem agora"
            ) from None
        return HumanMessageResult(
            telefone=digitos,
            texto=texto,
            idempotency_key=idempotency_key,
            duplicada=bool(dados.get("duplicada")),
            bot_ativo=bool(dados.get("bot_ativo", False)),
            mensagem_id=dados.get("mensagem_id"),
            enviado=bool(dados.get("enviado", True)),
            canal_id=dados.get("canal_id"),
        )
