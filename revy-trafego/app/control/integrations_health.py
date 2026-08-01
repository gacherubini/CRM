"""Health ao vivo das integrações Meta (Pixel/CAPI/Meta Ads) — Task 2.

`check_meta` reaproveita os getters de config já existentes em
`app.control.integrations` (não duplica storage) e usa um `GraphProbe`
injetável para validar o token na Graph API de verdade — sem nunca
retornar ou logar o token cru.

O agregador multi-grupo (Meta + Google + WhatsApp) vem na Task 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.control.graph_probe import GraphProbe
from app.control.integrations import _ads_config, _pixel_config
from app.cripto import decifrar
from app.meta_pixel import normalizar_pixel_id
from app.models import Loja


class HealthStatus(str, Enum):
    CONNECTED = "connected"
    ERROR = "error"
    MISSING = "missing"


@dataclass(frozen=True)
class ItemHealth:
    kind: str
    status: HealthStatus
    message: str | None = None


@dataclass(frozen=True)
class GroupHealth:
    status: HealthStatus
    itens: tuple[ItemHealth, ...]


def _group_status(itens: tuple[ItemHealth, ...]) -> HealthStatus:
    if any(item.status is HealthStatus.ERROR for item in itens):
        return HealthStatus.ERROR
    non_missing = [item for item in itens if item.status is not HealthStatus.MISSING]
    if non_missing:
        return HealthStatus.CONNECTED
    return HealthStatus.MISSING


def check_meta(db: Any, store: Loja, probe: GraphProbe) -> GroupHealth:
    """Consulta Pixel/CAPI/Meta Ads da Loja e valida os tokens no probe."""
    pixel_config = _pixel_config(db, store)
    ads_config = _ads_config(db, store)

    pixel_id = normalizar_pixel_id(pixel_config.pixel_id if pixel_config else None)
    tem_token_pixel = bool(pixel_config and pixel_config.token_ciphertext)

    itens: list[ItemHealth] = []

    if not pixel_id and not tem_token_pixel:
        itens.append(ItemHealth(kind="pixel", status=HealthStatus.MISSING, message=None))
        itens.append(ItemHealth(kind="capi", status=HealthStatus.MISSING, message=None))
    else:
        token_pixel = decifrar(pixel_config.token_ciphertext) if tem_token_pixel else ""
        ok, motivo = probe.validar_token(token_pixel, pixel_id)
        pixel_status = HealthStatus.CONNECTED if ok else HealthStatus.ERROR
        itens.append(
            ItemHealth(kind="pixel", status=pixel_status, message=None if ok else motivo)
        )
        # CAPI compartilha o token do Pixel (Conversions API): mesmo resultado
        # do probe, mas MISSING quando não há token configurado.
        if not tem_token_pixel:
            itens.append(ItemHealth(kind="capi", status=HealthStatus.MISSING, message=None))
        else:
            itens.append(
                ItemHealth(kind="capi", status=pixel_status, message=None if ok else motivo)
            )

    ad_account_id = (ads_config.ad_account_id if ads_config else "") or ""
    tem_token_ads = bool(ads_config and ads_config.token_ciphertext)
    if not ad_account_id and not tem_token_ads:
        itens.append(ItemHealth(kind="meta_ads", status=HealthStatus.MISSING, message=None))
    else:
        token_ads = decifrar(ads_config.token_ciphertext) if tem_token_ads else ""
        # Precisão por ad account (permissões/escopo) fica para fase futura;
        # aqui validamos apenas se o token em si é aceito pela Graph API.
        ok, motivo = probe.validar_token(token_ads, "")
        itens.append(
            ItemHealth(
                kind="meta_ads",
                status=HealthStatus.CONNECTED if ok else HealthStatus.ERROR,
                message=None if ok else motivo,
            )
        )

    itens_tuple = tuple(itens)
    return GroupHealth(status=_group_status(itens_tuple), itens=itens_tuple)
