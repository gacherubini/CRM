"""Cliente HTTP do Portal → Control para o cofre de tokens do Motor.

O Control guarda um token do Motor por loja (emitido na criação da loja) e
serve ao Portal em ``GET /internal/motor-tokens/{slug}``. Loja nova funciona
sem editar secret no Portal: o cofre é consultado primeiro e o mapa
``MOTOR_TOKENS_JSON`` fica como fallback legado (ver ``get_motor_client``).

Diferença para o ``RevyTrafegoClient``: esta rota autentica com
``Authorization: Bearer <PORTAL_SERVICE_TOKEN>`` (o mesmo segredo do
provisionamento Control → Portal), não com ``X-Service-Token``.

Token em claro nunca em log, erro ou exceção: os logs carregam só o slug e
o tipo do erro. Qualquer falha (sem config, timeout, 4xx/5xx, corpo
inesperado) devolve ``""`` — o chamador cai no fallback sem quebrar a tela.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def buscar_motor_token_no_control(
    loja_slug: str | None,
    *,
    base_url: str | None = None,
    service_token: str | None = None,
    timeout: float | None = None,
) -> str:
    """Token do Motor da loja no cofre do Control, ou ``""`` se indisponível.

    Fail-soft de propósito: o Control fora do ar não pode quebrar a tela —
    quem chama tenta o mapa ``MOTOR_TOKENS_JSON`` em seguida.
    """
    slug = (loja_slug or "").strip()
    if not slug:
        return ""
    url = (base_url if base_url is not None else settings.revy_trafego_url or "")
    url = url.strip().rstrip("/")
    segredo = (
        service_token if service_token is not None else settings.service_token or ""
    ).strip()
    if not url or not segredo:
        return ""
    limite = timeout if timeout is not None else settings.control_motor_token_timeout
    try:
        with httpx.Client(base_url=url, timeout=limite) as client:
            resposta = client.get(
                f"/internal/motor-tokens/{slug}",
                headers={"Authorization": f"Bearer {segredo}"},
            )
        if resposta.status_code != 200:
            logger.warning(
                "control motor-tokens status=%s loja=%s",
                resposta.status_code,
                slug,
            )
            return ""
        try:
            corpo = resposta.json()
        except ValueError:
            return ""
        token = corpo.get("token") if isinstance(corpo, dict) else None
        return str(token).strip() if token else ""
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "control motor-tokens falhou loja=%s err=%s",
            slug,
            type(exc).__name__,
        )
        return ""
