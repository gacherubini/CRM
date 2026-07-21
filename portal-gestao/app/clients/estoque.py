from __future__ import annotations

from typing import Any

import httpx


class EstoqueIndisponivel(RuntimeError):
    pass


class VeiculoNaoEncontrado(RuntimeError):
    pass


class ConflitoEstoque(RuntimeError):
    pass


class EstoqueClient:
    def __init__(self, base_url: str, token: str, timeout: float = 5):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

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
                resposta = client.request(method, path, **kwargs)
                if resposta.status_code == 404 and erro_404 is not None:
                    raise erro_404("veículo não encontrado")
                if resposta.status_code == 409 and erro_409 is not None:
                    raise erro_409("veículo em estado incompatível")
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EstoqueIndisponivel("Não foi possível acessar o estoque agora") from exc

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
