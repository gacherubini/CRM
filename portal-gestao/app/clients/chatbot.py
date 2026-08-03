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

    def listar_conversas(
        self,
        busca: str | None = None,
        limit: int = 50,
        offset: int = 0,
        *,
        canal_id: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if busca:
            params["busca"] = busca
        if canal_id:
            params["canal_id"] = canal_id
        conversas = self._request("GET", "/v1/conversas", params=params)["conversas"]
        return [self._mapear_conversa(c) for c in conversas]

    def listar_mensagens(
        self,
        telefone: str,
        limit: int = 200,
        offset: int = 0,
        *,
        canal_id: str | None = None,
        instance: str | None = None,
        after_id: str | None = None,
        after_criada_em: str | None = None,
    ) -> list[dict]:
        """Histórico da conversa. Multi-WA: informe ``canal_id`` ou ``instance``.

        Polling: ``after_id`` (preferido) ou ``after_criada_em`` pede só
        mensagens posteriores ao cursor no Chatbot.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if canal_id:
            params["canal_id"] = canal_id
        if instance:
            params["instance"] = instance
        if after_id:
            params["after_id"] = after_id
        if after_criada_em:
            params["after_criada_em"] = after_criada_em
        dados = self._request(
            "GET",
            f"/v1/conversas/{telefone}/mensagens",
            erro_404=ConversaNaoEncontrada,
            params=params,
        )
        return dados["mensagens"]

    def listar_mensagens_envelope(
        self,
        telefone: str,
        limit: int = 200,
        offset: int = 0,
        *,
        canal_id: str | None = None,
        instance: str | None = None,
        after_id: str | None = None,
        after_criada_em: str | None = None,
    ) -> dict:
        """Como ``listar_mensagens``, mas devolve o envelope completo do Chatbot."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if canal_id:
            params["canal_id"] = canal_id
        if instance:
            params["instance"] = instance
        if after_id:
            params["after_id"] = after_id
        if after_criada_em:
            params["after_criada_em"] = after_criada_em
        return self._request(
            "GET",
            f"/v1/conversas/{telefone}/mensagens",
            erro_404=ConversaNaoEncontrada,
            params=params,
        )

    def obter_estado(
        self,
        telefone: str,
        *,
        canal_id: str | None = None,
        instance: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {}
        if canal_id:
            params["canal_id"] = canal_id
        if instance:
            params["instance"] = instance
        return self._request(
            "GET",
            f"/v1/conversas/{telefone}/estado",
            params=params or None,
        )

    def definir_bot_ativo(
        self,
        telefone: str,
        bot_ativo: bool,
        *,
        instance: str | None = None,
    ) -> dict:
        """Pausa/reativa o bot. ``instance`` vem do resumo da conversa (multi-WA)."""
        payload: dict[str, Any] = {"bot_ativo": bot_ativo}
        if instance:
            payload["instance"] = instance
        return self._request(
            "PATCH", f"/v1/conversas/{telefone}/estado", json=payload
        )

    def listar_canais_whatsapp(self) -> list[dict]:
        """Lista canais da loja. A Loja também opera canais (ver métodos abaixo)."""
        dados = self._request("GET", "/v1/whatsapp/canais")
        return list(dados.get("canais") or [])

    def registrar_canal_whatsapp(self, label: str) -> dict:
        """Cadastra canal. Não envia ``evolution_instance``: o Chatbot gera o nome."""
        return self._request(
            "POST",
            "/v1/whatsapp/canais",
            json={"e164_or_label": label},
        )

    def conectar_canal_whatsapp(self, canal_id: str) -> dict:
        """Inicia pareamento. A resposta traz ``qr_payload`` efêmero — nunca logar."""
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/connect"
        )

    def desconectar_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/disconnect"
        )

    def inativar_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "POST", f"/v1/whatsapp/canais/{canal_id}/inativar"
        )

    def obter_status_canal_whatsapp(self, canal_id: str) -> dict:
        return self._request(
            "GET", f"/v1/whatsapp/canais/{canal_id}/status"
        )

    def enviar_mensagem_humana(
        self,
        telefone: str,
        texto: str,
        *,
        idempotency_key: str,
        instance: str | None = None,
        ator: str | None = None,
    ) -> dict:
        """Envia texto humano via Chatbot (persistência + canal da conversa).

        ``instance`` só deve vir do resumo da conversa já aberta — nunca de
        seletor arbitrário no UI da Loja.
        """
        payload: dict[str, Any] = {
            "texto": texto,
            "idempotency_key": idempotency_key,
        }
        if instance:
            payload["instance"] = instance
        if ator:
            payload["ator"] = ator
        return self._request(
            "POST",
            f"/v1/conversas/{telefone}/mensagens",
            erro_404=ConversaNaoEncontrada,
            json=payload,
        )

    @staticmethod
    def _mapear_conversa(raw: dict) -> dict:
        """Normaliza campos multi-WA se a API os devolver (expand-only)."""
        if not isinstance(raw, dict):
            return raw
        out = dict(raw)
        # Aliases estáveis para o read-model de Atendimento.
        if out.get("canal_label") is None and out.get("numero_mascarado"):
            out["canal_label"] = out["numero_mascarado"]
        if out.get("instance") is None and out.get("evolution_instance"):
            out["instance"] = out["evolution_instance"]
        return out

    # --- Simulação -------------------------------------------------------------

    def simular(self, payload: dict) -> dict:
        return self._request(
            "POST", "/v1/simular", erro_409=SimulacaoIndisponivel, json=payload
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
