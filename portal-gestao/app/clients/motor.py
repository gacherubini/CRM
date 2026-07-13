"""Cliente HTTP server-side do Motor de Simulação (credenciais de financeiras).

Nunca loga senha/token. Toda leitura/escrita de credencial passa pelo Motor —
o Portal não guarda senha de portal bancário em banco próprio.
"""
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
        **kwargs,
    ) -> Any:
        if not self.configurado:
            raise MotorIndisponivel(
                "Integração com o Motor de Simulação ainda não configurada"
            )
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(ator),
                timeout=self.timeout,
            ) as client:
                resposta = client.request(method, path, **kwargs)
                if resposta.status_code == 404 and erro_404 is not None:
                    raise erro_404("credencial não configurada")
                resposta.raise_for_status()
                if resposta.status_code == 204 or not resposta.content:
                    return {}
                return resposta.json()
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
    ) -> dict:
        # Body com senha só no servidor → Motor; nunca logar este payload.
        return self._request(
            "PUT",
            f"/v1/provedores/{nome}/credenciais",
            ator=ator,
            json={"usuario": usuario, "senha": senha, "habilitado": habilitado},
        )

    def testar_login(self, nome: str, ator: str) -> dict:
        return self._request(
            "POST",
            f"/v1/provedores/{nome}/testar-login",
            ator=ator,
            erro_404=CredencialNaoEncontrada,
        )
