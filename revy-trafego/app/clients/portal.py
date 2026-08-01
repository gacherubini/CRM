from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.clients._retry import requisicao_com_retry
from app.config import settings


class PortalIndisponivel(RuntimeError):
    pass


class ConviteDonoRecusado(RuntimeError):
    """Portal recusou o convite por conflito (ex.: e-mail de outro tipo de acesso)."""

    pass


class PortalClient:
    """Cliente mínimo Control → Portal (provisionamento com X-Service-Token)."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout: float = 5,
        *,
        retries: int | None = None,
        retry_backoff: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout = timeout
        self.retries = settings.request_retries if retries is None else max(0, retries)
        self.retry_backoff = (
            settings.request_retry_backoff
            if retry_backoff is None
            else max(0.0, retry_backoff)
        )
        self.sleeper = sleeper

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.service_token)

    def convidar_dono(self, email: str, nome: str, loja_slug: str) -> dict:
        """Solicita ao Portal um convite idempotente para o dono da Loja."""
        if not self.configurado:
            raise PortalIndisponivel(
                "Integra\u00e7\u00e3o do portal ainda n\u00e3o configurada"
            )

        email_normalizado = (email or "").strip().lower()
        nome_normalizado = " ".join((nome or "").split())
        loja_normalizada = (loja_slug or "").strip().lower()
        material_chave = "|".join((loja_normalizada, email_normalizado))
        idempotency_key = "revy-owner-invite-" + hashlib.sha256(
            material_chave.encode("utf-8")
        ).hexdigest()
        headers = {
            "X-Service-Token": self.service_token,
            "Idempotency-Key": idempotency_key,
        }
        payload = {
            "email": email_normalizado,
            "nome": nome_normalizado,
            "loja_slug": loja_normalizada,
        }
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"X-Service-Token": self.service_token},
                timeout=self.timeout,
            ) as client:
                resposta = requisicao_com_retry(
                    client,
                    "POST",
                    "/internal/v1/lojistas/convite",
                    # O endpoint do Portal NÃO é idempotente (não honra
                    # Idempotency-Key): retry poderia duplicar convite/e-mail.
                    retries=0,
                    backoff=self.retry_backoff,
                    sleeper=self.sleeper,
                    headers=headers,
                    json=payload,
                )
                if resposta.status_code == 409:
                    # 409 = conflito real do Portal (e-mail pertence a outro tipo de
                    # acesso). NÃO é sucesso idempotente — surge como erro claro.
                    detalhe = ""
                    try:
                        corpo = resposta.json()
                        if isinstance(corpo, dict):
                            detalhe = str(corpo.get("detail") or "")
                    except ValueError:
                        detalhe = ""
                    raise ConviteDonoRecusado(
                        detalhe or "e-mail já pertence a outro tipo de acesso"
                    )
                resposta.raise_for_status()
                corpo = resposta.json()
                if not isinstance(corpo, dict):
                    raise ValueError("resposta invalida")
                return corpo
        except (httpx.HTTPError, ValueError) as exc:
            raise PortalIndisponivel(
                "N\u00e3o foi poss\u00edvel solicitar o convite no portal agora"
            ) from exc

    def aplicar_estado_operacional(self, payload: dict) -> dict:
        if not self.configurado:
            raise PortalIndisponivel("Integração do portal ainda não configurada")
        headers = {"X-Service-Token": self.service_token}
        try:
            with httpx.Client(
                base_url=self.base_url, headers=headers, timeout=self.timeout
            ) as client:
                resposta = requisicao_com_retry(
                    client,
                    "POST",
                    "/internal/v1/provisioning/state",
                    retries=self.retries,
                    backoff=self.retry_backoff,
                    sleeper=self.sleeper,
                    json=payload,
                )
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PortalIndisponivel(
                "Não foi possível acessar o portal agora"
            ) from exc
