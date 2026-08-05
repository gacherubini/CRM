from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.clients._retry import requisicao_com_retry
from app.config import settings


class EstoqueIndisponivel(RuntimeError):
    pass


class VeiculoNaoEncontrado(RuntimeError):
    pass


class ConflitoEstoque(RuntimeError):
    pass


class EstoqueClient:
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

    def _request(
        self,
        method: str,
        path: str,
        erro_404: type[Exception] | None = None,
        erro_409: type[Exception] | None = None,
        **kwargs,
    ) -> Any:
        if not self.configurado:
            raise EstoqueIndisponivel("Integração de estoque ainda não configurada")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout) as client:
                resposta = requisicao_com_retry(
                    client,
                    method,
                    path,
                    retries=self.retries,
                    backoff=self.retry_backoff,
                    sleeper=self.sleeper,
                    **kwargs,
                )
                if resposta.status_code == 404 and erro_404 is not None:
                    raise erro_404("veículo não encontrado")
                if resposta.status_code == 409 and erro_409 is not None:
                    raise erro_409("veículo em estado incompatível")
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError):
            raise EstoqueIndisponivel(
                "Não foi possível acessar o estoque agora"
            ) from None

    def listar(self, **filtros) -> list[dict]:
        params = {k: v for k, v in filtros.items() if v not in (None, "")}
        return self._request("GET", "/v1/veiculos", params=params)["veiculos"]

    def obter(self, veiculo_id: str) -> dict:
        return self._request(
            "GET", f"/v1/veiculos/{veiculo_id}", erro_404=VeiculoNaoEncontrado
        )

    def criar(self, dados: dict) -> dict:
        return self._request("POST", "/v1/veiculos", json=dados)

    def atualizar(self, veiculo_id: str, dados: dict) -> dict:
        return self._request("PATCH", f"/v1/veiculos/{veiculo_id}", json=dados)

    def acao(self, veiculo_id: str, acao: str) -> dict:
        permitidas = {"publicar", "despublicar", "reservar", "vender"}
        if acao not in permitidas:
            raise ValueError("ação de estoque inválida")
        return self._request(
            "POST",
            f"/v1/veiculos/{veiculo_id}/{acao}",
            erro_404=VeiculoNaoEncontrado,
            erro_409=ConflitoEstoque,
        )

    def obter_loja(self) -> dict:
        """Metadados da loja autenticada (slug, nome, whatsapp, catalogo_url)."""
        return self._request("GET", "/v1/loja")

    def atualizar_loja(
        self,
        *,
        whatsapp: str | None | object = ...,
        catalogo_url: str | None | object = ...,
    ) -> dict:
        """Atualiza WhatsApp do CTA e/ou link do catálogo do bot.

        Campos omitidos (ellipsis) não entram no PATCH.
        """
        body: dict = {}
        if whatsapp is not ...:
            body["whatsapp"] = whatsapp
        if catalogo_url is not ...:
            body["catalogo_url"] = catalogo_url
        return self._request("PATCH", "/v1/loja", json=body)

    def reordenar_vitrine(self, itens: list[dict]) -> dict:
        """Atualiza ordem manual dos veículos na vitrine pública."""
        return self._request(
            "PUT",
            "/v1/veiculos/ordem-vitrine",
            json={"itens": itens},
            erro_404=VeiculoNaoEncontrado,
        )
