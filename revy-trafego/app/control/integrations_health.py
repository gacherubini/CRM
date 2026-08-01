"""Health ao vivo das integrações Meta e Google Ads — Tasks 2 e 3.

`check_meta` reaproveita os getters de config já existentes em
`app.control.integrations` (não duplica storage) e usa um `GraphProbe`
injetável para validar o token na Graph API de verdade — sem nunca
retornar ou logar o token cru.

`check_google` reaproveita a troca refresh->access token já existente em
`app.control.google_ads_http.HttpGoogleAdsTokenExchanger` através da porta fina
`GoogleAccessTokenPort` (protocolo `obter_access_token(refresh_token) -> str`),
também sem nunca retornar ou logar o token cru.

O agregador multi-grupo (Meta + Google + WhatsApp) vem na Task 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from app.clients.chatbot import ChatbotClient
from app.config import settings
from app.control.graph_probe import GraphProbe
from app.control.health_cache import TTLCache
from app.control.integrations import _ads_config, _pixel_config
from app.control.types import StoreView
from app.cripto import decifrar
from app.meta_pixel import normalizar_pixel_id
from app.models import GoogleAdsConnection, Loja, agora


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


def check_meta(db: Any, store: StoreView | Loja, probe: GraphProbe) -> GroupHealth:
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


class GoogleAccessTokenPort(Protocol):
    """Porta fina e injetável para trocar refresh token por access token.

    Permite mockar `check_google` em teste sem bater na rede. A implementação
    real é um wrapper sobre
    `app.control.google_ads_http.HttpGoogleAdsTokenExchanger._access_token`.
    """

    def obter_access_token(self, refresh_token: str) -> str: ...


@dataclass(frozen=True)
class HttpGoogleAccessTokenPort:
    """Wrapper fino sobre `HttpGoogleAdsTokenExchanger` para uso real."""

    exchanger: Any  # HttpGoogleAdsTokenExchanger, evita import circular

    def obter_access_token(self, refresh_token: str) -> str:
        return self.exchanger._access_token(refresh_token)


def check_google(
    db: Any, store: StoreView | Loja, exchanger: GoogleAccessTokenPort
) -> GroupHealth:
    """Consulta a conexão Google Ads da Loja e valida o refresh token de fato.

    Troca o refresh token cifrado por um access token através de `exchanger`
    (nunca retorna nem loga o token cru, cifrado ou não).
    """
    connection = (
        db.query(GoogleAdsConnection)
        .filter(GoogleAdsConnection.loja_id == store.id)
        .one_or_none()
    )

    if connection is None or not connection.refresh_token_ciphertext:
        itens = (ItemHealth(kind="google_ads", status=HealthStatus.MISSING, message=None),)
        return GroupHealth(status=HealthStatus.MISSING, itens=itens)

    refresh_token = decifrar(connection.refresh_token_ciphertext)
    try:
        access_token = exchanger.obter_access_token(refresh_token)
    except Exception:
        item = ItemHealth(
            kind="google_ads",
            status=HealthStatus.ERROR,
            message="falha ao renovar access token do Google Ads",
        )
        return GroupHealth(status=HealthStatus.ERROR, itens=(item,))

    if not access_token:
        item = ItemHealth(
            kind="google_ads",
            status=HealthStatus.ERROR,
            message="access token vazio ao renovar Google Ads",
        )
        return GroupHealth(status=HealthStatus.ERROR, itens=(item,))

    item = ItemHealth(kind="google_ads", status=HealthStatus.CONNECTED, message=None)
    return GroupHealth(status=HealthStatus.CONNECTED, itens=(item,))


class WhatsappPort(Protocol):
    """Porta fina e injetável para listar canais WhatsApp de uma loja.

    Retorna `None` quando o chatbot não está configurado para a loja (→
    MISSING) e deixa a exceção propagar quando a chamada falha de fato (→
    ERROR, tratado por `check_whatsapp`).
    """

    def listar_canais(self, loja_slug: str) -> list[dict] | None: ...


@dataclass(frozen=True)
class ChatbotWhatsappPort:
    """Implementação real de `WhatsappPort`, sobre `ChatbotClient`."""

    def listar_canais(self, loja_slug: str) -> list[dict] | None:
        client = ChatbotClient(
            settings.chatbot_url,
            settings.chatbot_token_para(loja_slug),
            settings.request_timeout,
        )
        if not client.configurado:
            return None
        return client.listar_canais_whatsapp()


def check_whatsapp(store: StoreView | Loja, port: WhatsappPort) -> GroupHealth:
    """Consulta os canais WhatsApp da Loja no Chatbot e resume a saúde do grupo.

    Nunca loga/retorna segredo do chatbot: o `label` exibido é o
    telefone/rótulo do canal (dado da própria loja), não uma credencial.
    """
    try:
        canais = port.listar_canais(store.slug)
    except Exception:
        item = ItemHealth(
            kind="whatsapp", status=HealthStatus.ERROR, message="falha ao consultar WhatsApp"
        )
        return GroupHealth(status=HealthStatus.ERROR, itens=(item,))

    if canais is None:
        item = ItemHealth(kind="whatsapp", status=HealthStatus.MISSING, message=None)
        return GroupHealth(status=HealthStatus.MISSING, itens=(item,))

    operaveis = [
        canal
        for canal in canais
        if canal.get("ativo") and canal.get("estado") != "inativo"
    ]
    if not operaveis:
        item = ItemHealth(kind="whatsapp", status=HealthStatus.MISSING, message=None)
        return GroupHealth(status=HealthStatus.MISSING, itens=(item,))

    itens: list[ItemHealth] = []
    for canal in operaveis:
        estado = canal.get("estado")
        label = canal.get("e164_or_label")
        if estado == "conectado":
            itens.append(ItemHealth(kind="whatsapp", status=HealthStatus.CONNECTED, message=None))
        else:
            itens.append(
                ItemHealth(
                    kind="whatsapp",
                    status=HealthStatus.ERROR,
                    message=f"{label}: {estado}",
                )
            )

    itens_tuple = tuple(itens)
    return GroupHealth(status=_group_status(itens_tuple), itens=itens_tuple)


def _serializar_grupo(grupo: GroupHealth) -> dict[str, Any]:
    return {
        "status": grupo.status.value,
        "itens": [
            {"kind": item.kind, "status": item.status.value, "message": item.message}
            for item in grupo.itens
        ],
    }


_CACHE = TTLCache(ttl_seg=settings.integracoes_health_ttl_seg)


def health_da_loja(
    db: Any,
    store: StoreView | Loja,
    *,
    probe: GraphProbe,
    exchanger: GoogleAccessTokenPort,
    forcar: bool = False,
    cache: TTLCache | None = None,
    clock: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Agrega `check_meta` + `check_google` no contrato JSON do Revy Control.

    Usa `cache` (Task 1, `TTLCache`) para evitar rechecagem de tokens a cada
    request; `forcar=True` ignora o cache e recheca de fato. WhatsApp entra
    numa fase futura — não incluído aqui.
    """
    active_cache = cache if cache is not None else _CACHE
    key = (store.id,)

    if not forcar:
        cached = active_cache.get(key)
        if cached is not None:
            return cached

    meta = check_meta(db, store, probe)
    google = check_google(db, store, exchanger)

    checked_at = clock() if clock is not None else agora()
    checked_at_iso = checked_at.isoformat() if hasattr(checked_at, "isoformat") else str(checked_at)

    resultado = {
        "meta": _serializar_grupo(meta),
        "google": _serializar_grupo(google),
        "checked_at": checked_at_iso,
        "cache_ttl_seg": settings.integracoes_health_ttl_seg,
    }

    active_cache.set(key, resultado)
    return resultado


def invalidar(store_id: str) -> None:
    """Invalida o cache de health para a loja, forçando recheck na próxima chamada."""
    _CACHE.invalidate((store_id,))
