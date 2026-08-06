"""Cliente mínimo da Meta Graph API (Marketing / Ads).

Usado para resolver ``ad_id → campaign_id`` (Fase 2 de atribuição CTWA).
Nunca inclui o token em logs ou mensagens de erro.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from app.meta_graph_config import GRAPH_BASE

logger = logging.getLogger(__name__)

# Teto de espera em um único backoff (segundos)
_MAX_BACKOFF_SLEEP = 30.0


@dataclass(frozen=True)
class ResolveResult:
    """Resultado de uma resolução ad→campanha (nunca carrega o token)."""

    campaign_id: str | None = None
    campaign_nome: str | None = None
    status_code: int | None = None
    erro: str | None = None  # rate_limit | http_4xx | http_5xx | rede | vazio | sem_campanha
    retryable: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.campaign_id)


def _parse_retry_after(header: str | None, attempt: int) -> float:
    """Segundos de espera: Retry-After numérico ou backoff exponencial."""
    if header:
        try:
            return min(float(header.strip()), _MAX_BACKOFF_SLEEP)
        except (TypeError, ValueError):
            pass
    # 0.5, 1.0, 2.0…
    return min(0.5 * (2**attempt), _MAX_BACKOFF_SLEEP)


def resolver_campanha_do_anuncio(
    ad_id: str,
    token: str,
    *,
    timeout: float = 5.0,
    transport=None,
    max_retries: int = 2,
    sleeper: Callable[[float], None] = time.sleep,
) -> ResolveResult:
    """Resolve ``ad_id`` → campanha Meta.

    Em 429/5xx tenta de novo com backoff (até ``max_retries``).
    Nunca lança. Nunca inclui o token em mensagem de log.
    """
    ad_id = (ad_id or "").strip()
    if not ad_id or not token:
        return ResolveResult(erro="vazio")

    url = f"{GRAPH_BASE}/{ad_id}"
    params = {"fields": "campaign{id,name}", "access_token": token}
    attempts = max(0, int(max_retries)) + 1

    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                resp = client.get(url, params=params)
        except (httpx.HTTPError, ValueError, TypeError):
            logger.warning("meta_graph: falha de rede ad %s", ad_id)
            if attempt + 1 < attempts:
                sleeper(_parse_retry_after(None, attempt))
                continue
            return ResolveResult(erro="rede", retryable=True)

        code = resp.status_code
        if code == 200:
            try:
                camp = (resp.json() or {}).get("campaign") or {}
            except ValueError:
                return ResolveResult(status_code=code, erro="http_4xx")
            cid = camp.get("id")
            nome = camp.get("name")
            if not cid:
                return ResolveResult(
                    status_code=code,
                    erro="sem_campanha",
                )
            return ResolveResult(
                campaign_id=str(cid),
                campaign_nome=str(nome) if nome else None,
                status_code=code,
            )

        if code == 429 or code >= 500:
            logger.warning("meta_graph: ad %s status %s (retryable)", ad_id, code)
            if attempt + 1 < attempts:
                sleeper(_parse_retry_after(resp.headers.get("Retry-After"), attempt))
                continue
            erro = "rate_limit" if code == 429 else "http_5xx"
            return ResolveResult(
                status_code=code, erro=erro, retryable=True
            )

        logger.warning("meta_graph: ad %s status %s", ad_id, code)
        return ResolveResult(status_code=code, erro="http_4xx", retryable=False)

    return ResolveResult(erro="rede", retryable=True)


def as_tuple(result: ResolveResult) -> tuple[str | None, str | None]:
    """Compat: ``(campaign_id, campaign_nome)``."""
    return (result.campaign_id, result.campaign_nome)
