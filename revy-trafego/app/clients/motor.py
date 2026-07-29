from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.clients._retry import requisicao_com_retry
from app.config import settings


class MotorIndisponivel(RuntimeError):
    pass


class MotorClient:
    """Cliente mínimo Control → Motor (provisionamento com Bearer por cliente)."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 5,
        *,
        retries: int | None = None,
        retry_backoff: float | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
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
        return bool(self.base_url and self.token)

    def aplicar_estado_operacional(self, payload: dict) -> dict:
        if not self.configurado:
            raise MotorIndisponivel("Integração do motor ainda não configurada")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(
                base_url=self.base_url, headers=headers, timeout=self.timeout
            ) as client:
                resposta = requisicao_com_retry(
                    client,
                    "POST",
                    "/v1/internal/provisioning/state",
                    retries=self.retries,
                    backoff=self.retry_backoff,
                    sleeper=self.sleeper,
                    json=payload,
                )
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MotorIndisponivel(
                "Não foi possível acessar o motor agora"
            ) from exc
