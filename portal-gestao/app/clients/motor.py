"""Cliente HTTP server-side do Motor de Simulação (credenciais de financeiras).

Nunca loga senha/token. Toda leitura/escrita de credencial passa pelo Motor —
o Portal não guarda senha de portal bancário em banco próprio.
"""
from __future__ import annotations

from typing import Any

import httpx


class MotorIndisponivel(RuntimeError):
    pass


class CredencialNaoEncontrada(RuntimeError):
    pass


class MotorClient:
    def __init__(self, base_url: str, token: str, timeout: float = 5):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self, ator: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if ator:
            headers["X-Ator"] = ator
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        ator: str | None = None,
        erro_404: type[Exception] | None = None,
        timeout: float | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> Any:
        if not self.configurado:
            raise MotorIndisponivel(
                "Integração com o Motor de Simulação ainda não configurada"
            )
        try:
            req_headers = self._headers(ator)
            if headers:
                req_headers.update(headers)
            with httpx.Client(
                base_url=self.base_url,
                headers=req_headers,
                timeout=timeout if timeout is not None else self.timeout,
            ) as client:
                resposta = client.request(method, path, **kwargs)
                if resposta.status_code == 404 and erro_404 is not None:
                    raise erro_404("credencial não configurada")
                if resposta.status_code == 422:
                    try:
                        detalhe = resposta.json()
                        msg = (detalhe.get("erro") or {}).get("message") or str(detalhe)
                    except Exception:
                        msg = "dados de simulação inválidos"
                    raise MotorIndisponivel(msg)
                resposta.raise_for_status()
                if resposta.status_code == 204 or not resposta.content:
                    return {}
                return resposta.json()
        except MotorIndisponivel:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MotorIndisponivel(
                "Não foi possível acessar o Motor de Simulação agora"
            ) from exc

    def listar_provedores(self, ator: str | None = None) -> list[dict]:
        dados = self._request("GET", "/v1/provedores", ator=ator)
        return dados.get("provedores") or []

    def listar_credenciais(self, ator: str | None = None) -> list[dict]:
        dados = self._request("GET", "/v1/provedores/credenciais", ator=ator)
        return dados.get("credenciais") or []

    def obter_credencial(self, nome: str, ator: str | None = None) -> dict:
        return self._request(
            "GET",
            f"/v1/provedores/{nome}/credenciais",
            ator=ator,
            erro_404=CredencialNaoEncontrada,
        )

    def upsert_credencial(
        self,
        nome: str,
        usuario: str,
        senha: str,
        ator: str,
        habilitado: bool = True,
        campos: dict[str, str] | None = None,
    ) -> dict:
        # Body com senha só no servidor → Motor; nunca logar este payload.
        corpo = {"usuario": usuario, "senha": senha, "habilitado": habilitado}
        if campos:
            corpo["campos"] = campos
        return self._request(
            "PUT",
            f"/v1/provedores/{nome}/credenciais",
            ator=ator,
            json=corpo,
        )

    def testar_login(self, nome: str, ator: str) -> dict:
        return self._request(
            "POST",
            f"/v1/provedores/{nome}/testar-login",
            ator=ator,
            erro_404=CredencialNaoEncontrada,
        )

    def criar_simulacao(
        self,
        payload: dict,
        *,
        ator: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """POST /v1/simulacoes — enfileira job (202)."""
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._request(
            "POST",
            "/v1/simulacoes",
            ator=ator,
            json=payload,
            headers=headers if headers else None,
        )

    def obter_simulacao(self, sim_id: str, ator: str | None = None) -> dict:
        return self._request("GET", f"/v1/simulacoes/{sim_id}", ator=ator)

    def listar_eventos(self, sim_id: str, ator: str | None = None) -> dict:
        return self._request(
            "GET", f"/v1/simulacoes/{sim_id}/eventos", ator=ator
        )

    def obter_print_evento(
        self, sim_id: str, evento_id: int, ator: str | None = None
    ) -> tuple[bytes, str]:
        if not self.configurado:
            raise MotorIndisponivel("Integração com o Motor não configurada")
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(ator),
                timeout=max(self.timeout, 15),
            ) as client:
                resposta = client.get(
                    f"/v1/simulacoes/{sim_id}/eventos/{evento_id}/print"
                )
                resposta.raise_for_status()
                return resposta.content, resposta.headers.get("content-type", "image/png")
        except httpx.HTTPError as exc:
            raise MotorIndisponivel("Não foi possível carregar o print") from exc

    def listar_simulacoes(
        self,
        *,
        ator: str | None = None,
        status: str | None = None,
        solicitado_por: str | None = None,
        desde: str | None = None,
        ate: str | None = None,
        limite: int = 20,
        offset: int = 0,
    ) -> dict:
        """GET /v1/simulacoes — histórico do cliente (tenancy no Motor).

        Repassa o token do servidor (BFF) e o ator no header X-Ator. Para "minhas
        sims", o chamador passa solicitado_por=email do usuário logado.
        """
        params: dict[str, object] = {"limite": limite, "offset": offset}
        if status:
            params["status"] = status
        if solicitado_por:
            params["solicitado_por"] = solicitado_por
        if desde:
            params["desde"] = desde
        if ate:
            params["ate"] = ate
        return self._request("GET", "/v1/simulacoes", ator=ator, params=params)

    def simular_e_aguardar(
        self,
        payload: dict,
        *,
        ator: str | None = None,
        poll_timeout: float = 90.0,
        poll_interval: float = 1.0,
    ) -> dict:
        """Cria job no Motor e espera estado terminal (dashboard / teste manual)."""
        import time
        import uuid

        criada = self.criar_simulacao(
            payload, ator=ator, idempotency_key=str(uuid.uuid4())
        )
        sim_id = criada.get("id")
        if not sim_id:
            raise MotorIndisponivel("Motor respondeu sem id de simulação")
        terminais = {
            "concluida",
            "parcial",
            "falhou",
            "aguardando_intervencao",
            "cancelada",
        }
        limite = time.monotonic() + poll_timeout
        while True:
            atual = self.obter_simulacao(sim_id, ator=ator)
            if atual.get("status") in terminais:
                return atual
            if time.monotonic() >= limite:
                atual["mensagem"] = (
                    "Simulação ainda processando no Motor (timeout de espera). "
                    "Tente consultar de novo ou aumente o timeout."
                )
                return atual
            time.sleep(poll_interval)
