"""Auth serviço-a-serviço (portal/catálogo → Revy Tráfego)."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app import config as config_mod


def exigir_service_token(
    x_service_token: str = Header(default="", alias="X-Service-Token"),
) -> None:
    esperado = (config_mod.settings.service_token or "").strip()
    if not esperado:
        raise HTTPException(
            status_code=503,
            detail="service token não configurado (REVY_TRAFEGO_SERVICE_TOKEN)",
        )
    if not secrets.compare_digest(x_service_token or "", esperado):
        raise HTTPException(status_code=401, detail="não autorizado")
