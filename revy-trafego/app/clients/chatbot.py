from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.clients._retry import requisicao_com_retry
from app.config import settings


class ChatbotIndisponivel(RuntimeError):
    pass


class LeadNaoEncontrado(RuntimeError):
    pass


class ConversaNaoEncontrada(RuntimeError):
    pass


class SimulacaoIndisponivel(RuntimeError):
    pass


class ChatbotClient:
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
            raise ChatbotIndisponivel("Integração do chatbot ainda não configurada")
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
                    raise erro_404("recurso não encontrado")
                if resposta.status_code == 409 and erro_409 is not None:
                    raise erro_409("recurso não habilitado")
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError):
            raise ChatbotIndisponivel(
                "Não foi possível acessar o chatbot agora"
            ) from None

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

    def listar_eventos_funil(self, limit: int = 500, offset: int = 0) -> list[dict]:
        dados = self._request(
            "GET",
            "/v1/funil/eventos",
            params={"limit": limit, "offset": offset},
        )
        return dados["eventos"]

    def listar_auditoria_ctwa(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        so_com_clid: bool = False,
    ) -> dict:
        return self._request(
            "GET",
            "/v1/auditoria/ctwa",
            params={
                "limit": limit,
                "offset": offset,
                "so_com_clid": so_com_clid,
            },
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

    # --- Provisionamento operacional (Control → Chatbot) -----------------------

    def aplicar_estado_operacional(self, payload: dict) -> dict:
        """POST do snapshot de provisionamento do Control."""
        return self._request(
            "POST",
            "/v1/internal/provisioning/state",
            json=payload,
        )

    # --- Operação: números autorizados a cadastrar ----------------------------

    def obter_grupo_estoque(self) -> dict:
        return self._request("GET", "/v1/operacao/grupo-estoque")

    def definir_grupo_estoque(self, grupo_jid: str) -> dict:
        return self._request(
            "PUT",
            "/v1/operacao/grupo-estoque",
            json={"grupo_jid": grupo_jid},
        )

    def remover_grupo_estoque(self) -> dict:
        return self._request("DELETE", "/v1/operacao/grupo-estoque")

    def listar_numeros_cadastro(self) -> list[dict]:
        return self._request("GET", "/v1/operacao/numeros-autorizados")["numeros"]

    def adicionar_numero_cadastro(self, telefone: str, nome: str | None = None) -> dict:
        return self._request(
            "POST",
            "/v1/operacao/numeros-autorizados",
            json={"telefone": telefone, "nome": nome, "ativo": True},
        )

    def remover_numero_cadastro(self, telefone: str) -> dict:
        return self._request("DELETE", f"/v1/operacao/numeros-autorizados/{telefone}")
