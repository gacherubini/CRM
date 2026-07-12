from typing import Any

import httpx


class ChatbotIndisponivel(RuntimeError):
    pass


class LeadNaoEncontrado(RuntimeError):
    pass


class ChatbotClient:
    def __init__(self, base_url: str, token: str, timeout: float = 5):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.token)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self.configurado:
            raise ChatbotIndisponivel("Integração de leads ainda não configurada")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout) as client:
                resposta = client.request(method, path, **kwargs)
                if resposta.status_code == 404:
                    raise LeadNaoEncontrado("Lead não encontrado")
                resposta.raise_for_status()
                return resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChatbotIndisponivel("Não foi possível acessar os leads agora") from exc

    def listar_leads(self, etapa: str | None = None) -> list[dict]:
        params = {"etapa": etapa} if etapa else {}
        return self._request("GET", "/v1/leads", params=params)["leads"]

    def obter_lead(self, lead_id: str) -> dict:
        return self._request("GET", f"/v1/leads/{lead_id}")
