from __future__ import annotations

from typing import Any

import httpx


class ChatbotIndisponivel(RuntimeError):
    pass


class LeadNaoEncontrado(RuntimeError):
    pass


class ConversaNaoEncontrada(RuntimeError):
    pass


class SimulacaoIndisponivel(RuntimeError):
    pass


class ChatbotClient:
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
            raise ChatbotIndisponivel("Integração do chatbot ainda não configurada")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout) as client:
                resposta = client.request(method, path, **kwargs)
                if resposta.status_code == 404 and erro_404 is not None:
                    raise erro_404("recurso não encontrado")
                if resposta.status_code == 409 and erro_409 is not None:
                    raise erro_409("recurso não habilitado")
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChatbotIndisponivel("Não foi possível acessar o chatbot agora") from exc

    # --- Leads -----------------------------------------------------------------

    def listar_leads(self, etapa: str | None = None) -> list[dict]:
        params = {"etapa": etapa} if etapa else {}
        return self._request("GET", "/v1/leads", params=params)["leads"]

    def obter_lead(self, lead_id: str) -> dict:
        return self._request("GET", f"/v1/leads/{lead_id}", erro_404=LeadNaoEncontrado)

    def atualizar_etapa_lead(self, lead_id: str, etapa: str) -> dict:
        return self._request(
            "PATCH",
            f"/v1/leads/{lead_id}/etapa",
            erro_404=LeadNaoEncontrado,
            json={"etapa": etapa},
        )

    # --- Conversas e handoff ---------------------------------------------------

    def listar_conversas(self, busca: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if busca:
            params["busca"] = busca
        return self._request("GET", "/v1/conversas", params=params)["conversas"]

    def listar_mensagens(self, telefone: str, limit: int = 200, offset: int = 0) -> list[dict]:
        params = {"limit": limit, "offset": offset}
        dados = self._request(
            "GET", f"/v1/conversas/{telefone}/mensagens", erro_404=ConversaNaoEncontrada, params=params
        )
        return dados["mensagens"]

    def obter_estado(self, telefone: str) -> dict:
        return self._request("GET", f"/v1/conversas/{telefone}/estado")

    def definir_bot_ativo(self, telefone: str, bot_ativo: bool) -> dict:
        return self._request(
            "PATCH", f"/v1/conversas/{telefone}/estado", json={"bot_ativo": bot_ativo}
        )

    # --- Simulação -------------------------------------------------------------

    def simular(self, payload: dict) -> dict:
        return self._request(
            "POST", "/v1/simular", erro_409=SimulacaoIndisponivel, json=payload
        )
