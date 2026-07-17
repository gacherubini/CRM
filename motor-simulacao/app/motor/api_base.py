"""Base reutilizável para integrações bancárias HTTP oficiais."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
)


class ApiBankDriver(ABC):
    """Cliente síncrono comum com timeout e erros sanitizados.

    O driver concreto só monta autenticação/payload e interpreta o JSON. Respostas
    integrais nunca entram em exceções ou logs, pois podem conter dados pessoais.
    """

    provedor = "api"
    real = True
    # Não consome slot do teto MOTOR_MAX_BROWSER_WORKERS.
    usa_browser = False

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.transport = transport

    def __call__(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> ResultadoDriver | list[ResultadoDriver]:
        return self.simular(sol, ctx)

    @abstractmethod
    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> ResultadoDriver | list[ResultadoDriver]:
        raise NotImplementedError

    def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_s,
                transport=self.transport,
            ) as client:
                resposta = client.request(method, path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ErroTransitorio("api_indisponivel") from exc

        if resposta.status_code in (401, 403):
            raise IntervencaoNecessaria("credencial_invalida")
        if resposta.status_code == 429 or resposta.status_code >= 500:
            raise ErroTransitorio(
                "api_rate_limit" if resposta.status_code == 429 else "api_indisponivel"
            )
        if resposta.status_code >= 400:
            raise RejeicaoNegocio(f"api_http_{resposta.status_code}")
        try:
            return resposta.json()
        except ValueError as exc:
            raise ErroTransitorio("api_resposta_invalida") from exc
