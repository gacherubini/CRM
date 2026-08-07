"""Cliente HTTP do Portal → Revy Tráfego (resultados + eventos de venda)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RevyTrafegoClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (base_url if base_url is not None else settings.revy_trafego_url).rstrip(
            "/"
        )
        self.token = token if token is not None else settings.revy_trafego_service_token
        self.timeout = (
            timeout if timeout is not None else settings.revy_trafego_timeout
        )

    @property
    def configurado(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self) -> dict[str, str]:
        return {"X-Service-Token": self.token}

    def fetch_resultados(
        self,
        *,
        loja_slug: str,
        periodo: str = "7d",
        modo: str = "last",
        inicio: str | None = None,
        fim: str | None = None,
    ) -> dict[str, Any] | None:
        """GET /v1/lojas/{slug}/resultados. None se offline/erro/não configurado.

        Com ``inicio``/``fim`` a API usa a janela exata; sem eles, o seletor
        ``periodo``.
        """
        if not self.configurado:
            return None
        params: dict[str, Any] = {"periodo": periodo, "modo": modo}
        if inicio:
            params["inicio"] = inicio
        if fim:
            params["fim"] = fim
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                r = client.get(
                    f"/v1/lojas/{loja_slug}/resultados",
                    params=params,
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    logger.warning(
                        "revy_trafego resultados status=%s loja=%s",
                        r.status_code,
                        loja_slug,
                    )
                    return None
                return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "revy_trafego resultados falhou loja=%s err=%s",
                loja_slug,
                type(exc).__name__,
            )
            return None

    def fetch_integracoes_health(
        self,
        *,
        loja_slug: str,
        forcar: bool = False,
    ) -> dict[str, Any] | None:
        """GET /v1/lojas/{slug}/integracoes/health. None se offline/erro/não configurado.

        Consumido server-side pelo endpoint local do shell da Loja (badge de
        status Meta/Google/WhatsApp): o token de serviço nunca sai daqui; o
        navegador do dono/gerente fala só com o Portal. None (offline/não
        configurado) é distinto de um 200 com `status=missing` (configuração
        ausente, mas Control no ar) — o chamador decide como sinalizar cada caso.
        """
        if not self.configurado:
            return None
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                r = client.get(
                    f"/v1/lojas/{loja_slug}/integracoes/health",
                    params={"forcar": 1} if forcar else None,
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    logger.warning(
                        "revy_trafego integracoes_health status=%s loja=%s",
                        r.status_code,
                        loja_slug,
                    )
                    return None
                return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "revy_trafego integracoes_health falhou loja=%s err=%s",
                loja_slug,
                type(exc).__name__,
            )
            return None

    def notificar_venda_confirmada(
        self,
        *,
        loja_slug: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """POST evento venda-confirmada. Best-effort; None em falha."""
        if not self.configurado:
            return None
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                r = client.post(
                    f"/v1/lojas/{loja_slug}/eventos/venda-confirmada",
                    json=payload,
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    logger.warning(
                        "revy_trafego venda-confirmada status=%s loja=%s",
                        r.status_code,
                        loja_slug,
                    )
                    return None
                return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "revy_trafego venda-confirmada falhou loja=%s err=%s",
                loja_slug,
                type(exc).__name__,
            )
            return None

    def notificar_venda_atualizada(
        self,
        *,
        loja_slug: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """POST snapshot de estado; None em falha ou configuracao ausente."""
        if not self.configurado:
            return None
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                r = client.post(
                    f"/v1/lojas/{loja_slug}/eventos/venda-atualizada",
                    json=payload,
                    headers=self._headers(),
                )
                if r.status_code != 200:
                    logger.warning(
                        "revy_trafego venda-atualizada status=%s loja=%s",
                        r.status_code,
                        loja_slug,
                    )
                    return None
                return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "revy_trafego venda-atualizada falhou loja=%s err=%s",
                loja_slug,
                type(exc).__name__,
            )
            return None


def fetch_resultados(
    *,
    loja_slug: str,
    periodo: str = "7d",
    modo: str = "last",
    timeout: float | None = None,
) -> dict | None:
    return RevyTrafegoClient(timeout=timeout).fetch_resultados(
        loja_slug=loja_slug, periodo=periodo, modo=modo
    )
