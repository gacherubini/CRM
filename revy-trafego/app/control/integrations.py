"""Central de Integrações Meta — wrapper lean sobre configs existentes.

Não reescreve storage: opera em ``meta_pixel_config`` e ``meta_ads_config``.
CAPI compartilha o token cifrado do Pixel (Conversions API).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
    TrafficRole,
)
from app.cripto import cifrar
from app.meta_ads_spend import normalizar_ad_account_id
from app.meta_pixel import normalizar_pixel_id
from app.models import (
    Loja,
    LojaModulo,
    MetaAdsConfig,
    MetaPixelConfig,
    ModuloRevy,
    VinculoTrafego,
    agora,
)


class IntegrationKind(str, Enum):
    PIXEL = "pixel"
    CAPI = "capi"
    META_ADS = "meta_ads"


class IntegrationStatus(str, Enum):
    CONNECTED = "connected"
    MISSING = "missing"
    ERROR = "error"


class InvalidIntegrationConfig(ControlError):
    pass


@dataclass(frozen=True)
class IntegrationView:
    kind: IntegrationKind
    status: IntegrationStatus
    store_id: str
    store_slug: str
    fields: dict[str, object]
    updated_at: datetime | None
    health_message: str | None = None


@dataclass(frozen=True)
class UpsertPixel:
    store: StoreRef
    pixel_id: str
    token: str | None = None
    test_event_code: str | None = None
    enviar_page_view: bool = True
    enviar_lead: bool = True
    enviar_purchase: bool = True


@dataclass(frozen=True)
class UpsertMetaAds:
    store: StoreRef
    ad_account_id: str
    token: str | None = None
    sync_enabled: bool = True


_TOKEN_MASK = "••••••••"


class IntegrationsControl:
    """Catálogo, conexão e desconexão das integrações Meta da Loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def list(
        self,
        actor: Actor,
        store_ref: StoreRef,
    ) -> tuple[IntegrationView, ...]:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            pixel = _pixel_config(db, store)
            ads = _ads_config(db, store)
            return (
                _pixel_view(store, pixel),
                _capi_view(store, pixel),
                _ads_view(store, ads),
            )

    def upsert_pixel(self, actor: Actor, command: UpsertPixel) -> IntegrationView:
        pixel_id = normalizar_pixel_id(command.pixel_id)
        if not pixel_id:
            raise InvalidIntegrationConfig(
                "Informe um Pixel ID válido, contendo somente números."
            )
        token_novo = (command.token or "").strip() or None
        test_event_code = (command.test_event_code or "").strip() or None

        with self._session_factory() as db:
            store = _authorized_store(db, actor, command.store)
            _require_can_manage(db, actor, store)
            config = _pixel_config(db, store)
            if not token_novo and not (config and config.token_ciphertext):
                raise InvalidIntegrationConfig(
                    "Informe o token de acesso da Conversions API (CAPI)."
                )
            before = _pixel_audit(config)
            if config is None:
                config = MetaPixelConfig(
                    loja_slug=store.slug,
                    loja_id=store.id,
                    pixel_id=pixel_id,
                )
                db.add(config)
            else:
                config.loja_id = store.id
            config.pixel_id = pixel_id
            config.test_event_code = test_event_code
            config.enviar_page_view = bool(command.enviar_page_view)
            config.enviar_lead = bool(command.enviar_lead)
            config.enviar_purchase = bool(command.enviar_purchase)
            config.atualizada_em = agora()
            if token_novo:
                config.token_ciphertext = cifrar(token_novo)
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="integration.pixel.upserted",
                resource_type="meta_pixel_config",
                resource_id=store.slug,
                before=before,
                after=_pixel_audit(config),
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(config)

            from app.control.integrations_health import invalidar

            invalidar(store.id)
            return _pixel_view(store, config)

    def disconnect_pixel(
        self,
        actor: Actor,
        store_ref: StoreRef,
        *,
        reason: str | None = None,
    ) -> IntegrationView:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            _require_can_manage(db, actor, store)
            config = _pixel_config(db, store)
            if config is None:
                return _pixel_view(store, None)
            before = _pixel_audit(config)
            config.pixel_id = ""
            config.token_ciphertext = None
            config.test_event_code = None
            config.enviar_page_view = True
            config.enviar_lead = True
            config.enviar_purchase = True
            config.atualizada_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="integration.pixel.disconnected",
                resource_type="meta_pixel_config",
                resource_id=store.slug,
                before=before,
                after=_pixel_audit(config),
                reason=reason,
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(config)

            from app.control.integrations_health import invalidar

            invalidar(store.id)
            return _pixel_view(store, config)

    def upsert_meta_ads(
        self,
        actor: Actor,
        command: UpsertMetaAds,
    ) -> IntegrationView:
        account = normalizar_ad_account_id(command.ad_account_id)
        if not account:
            raise InvalidIntegrationConfig(
                "Informe o ID da conta de anúncios Meta (act_… ou só números)."
            )
        token_novo = (command.token or "").strip() or None

        with self._session_factory() as db:
            store = _authorized_store(db, actor, command.store)
            _require_can_manage(db, actor, store)
            config = _ads_config(db, store)
            if not token_novo and not (config and config.token_ciphertext):
                raise InvalidIntegrationConfig(
                    "Informe o token com permissão ads_read (Marketing API)."
                )
            before = _ads_audit(config)
            if config is None:
                config = MetaAdsConfig(
                    loja_slug=store.slug,
                    loja_id=store.id,
                    ad_account_id=account,
                )
                db.add(config)
            else:
                config.loja_id = store.id
            config.ad_account_id = account
            config.sync_enabled = bool(command.sync_enabled)
            config.atualizada_em = agora()
            if token_novo:
                config.token_ciphertext = cifrar(token_novo)
            # Config nova é a única evidência de que "não tenho acesso" pode ter
            # virado "tenho": os ads que estouraram o teto de tentativas voltam
            # à fila. Chave é loja_slug, não store.id (ver destravar_*).
            from app.meta_ad_resolver_job import destravar_ads_nao_resolvidos

            destravar_ads_nao_resolvidos(db, store.slug)
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="integration.meta_ads.upserted",
                resource_type="meta_ads_config",
                resource_id=store.slug,
                before=before,
                after=_ads_audit(config),
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(config)

            from app.control.integrations_health import invalidar

            invalidar(store.id)
            return _ads_view(store, config)

    def disconnect_meta_ads(
        self,
        actor: Actor,
        store_ref: StoreRef,
        *,
        reason: str | None = None,
    ) -> IntegrationView:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            _require_can_manage(db, actor, store)
            config = _ads_config(db, store)
            if config is None:
                return _ads_view(store, None)
            before = _ads_audit(config)
            config.ad_account_id = ""
            config.token_ciphertext = None
            config.sync_enabled = True
            config.ultima_sync_em = None
            config.ultima_sync_status = None
            config.ultima_sync_erro = None
            config.ultima_sync_resumo = None
            config.atualizada_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="integration.meta_ads.disconnected",
                resource_type="meta_ads_config",
                resource_id=store.slug,
                before=before,
                after=_ads_audit(config),
                reason=reason,
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(config)

            from app.control.integrations_health import invalidar

            invalidar(store.id)
            return _ads_view(store, config)


def pixel_configured(db: Any, store: Loja) -> bool:
    """Pixel + CAPI token presentes (requisito de medição para módulo vendas)."""
    config = _pixel_config(db, store)
    if config is None:
        return False
    return bool(normalizar_pixel_id(config.pixel_id) and config.token_ciphertext)


def vendas_module_active(db: Any, store_id: str) -> bool:
    return (
        db.query(LojaModulo.id)
        .join(ModuloRevy, ModuloRevy.id == LojaModulo.modulo_id)
        .filter(
            LojaModulo.loja_id == store_id,
            LojaModulo.estado == "ativo",
            ModuloRevy.codigo == "vendas",
        )
        .first()
        is not None
    )


def _lookup_store(db: Any, store_ref: StoreRef) -> Loja | None:
    # Local lookup evita import circular com stores ↔ readiness ↔ integrations.
    query = db.query(Loja)
    if store_ref.id:
        return query.filter(Loja.id == store_ref.id).first()
    return query.filter(Loja.slug == store_ref.slug.strip().lower()).first()


def _authorized_store(db: Any, actor: Actor, store_ref: StoreRef) -> Loja:
    store = _lookup_store(db, store_ref)
    if store is None:
        raise StoreNotFound("Loja não encontrada")
    if actor.is_admin:
        return store
    link = (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == store.id,
            VinculoTrafego.gestor_id == actor.id,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )
    if link is None:
        raise StoreNotFound("Loja não encontrada")
    return store


def _require_can_manage(db: Any, actor: Actor, store: Loja) -> None:
    """Admin ou Gestor Responsável; colaborador → AccessDenied."""
    if actor.is_admin:
        return
    link = (
        db.query(VinculoTrafego)
        .filter(
            VinculoTrafego.loja_id == store.id,
            VinculoTrafego.gestor_id == actor.id,
            VinculoTrafego.encerrado_em.is_(None),
        )
        .first()
    )
    if link is None:
        raise StoreNotFound("Loja não encontrada")
    if link.tipo != TrafficRole.RESPONSIBLE.value:
        raise AccessDenied(
            "somente Admin Revy ou Gestor Responsável pode alterar integrações"
        )


def _pixel_config(db: Any, store: Loja) -> MetaPixelConfig | None:
    by_id = None
    if store.id:
        by_id = (
            db.query(MetaPixelConfig)
            .filter(MetaPixelConfig.loja_id == store.id)
            .first()
        )
    if by_id is not None:
        return by_id
    return (
        db.query(MetaPixelConfig)
        .filter(MetaPixelConfig.loja_slug == store.slug)
        .first()
    )


def _ads_config(db: Any, store: Loja) -> MetaAdsConfig | None:
    by_id = None
    if store.id:
        by_id = (
            db.query(MetaAdsConfig)
            .filter(MetaAdsConfig.loja_id == store.id)
            .first()
        )
    if by_id is not None:
        return by_id
    return (
        db.query(MetaAdsConfig)
        .filter(MetaAdsConfig.loja_slug == store.slug)
        .first()
    )


def _mask_id(value: str, *, keep: int = 4) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= keep:
        return "•" * len(raw)
    return ("•" * max(4, len(raw) - keep)) + raw[-keep:]


def _pixel_view(store: Loja, config: MetaPixelConfig | None) -> IntegrationView:
    pixel_id = normalizar_pixel_id(config.pixel_id if config else None)
    has_token = bool(config and config.token_ciphertext)
    if not pixel_id and not has_token:
        status = IntegrationStatus.MISSING
        message = "Pixel Meta não configurado"
    elif pixel_id and has_token:
        status = IntegrationStatus.CONNECTED
        message = "Pixel conectado"
    else:
        status = IntegrationStatus.ERROR
        message = (
            "Pixel incompleto: informe ID e token CAPI"
            if not has_token
            else "Pixel incompleto: informe o Pixel ID"
        )
    return IntegrationView(
        kind=IntegrationKind.PIXEL,
        status=status,
        store_id=store.id,
        store_slug=store.slug,
        fields={
            "pixel_id": pixel_id or None,
            "pixel_id_masked": _mask_id(pixel_id) if pixel_id else None,
            "token_configured": has_token,
            "token_masked": _TOKEN_MASK if has_token else None,
            "test_event_code": (
                (config.test_event_code or None) if config else None
            ),
            "enviar_page_view": (
                bool(config.enviar_page_view) if config else True
            ),
            "enviar_lead": bool(config.enviar_lead) if config else True,
            "enviar_purchase": (
                bool(config.enviar_purchase) if config else True
            ),
        },
        updated_at=config.atualizada_em if config else None,
        health_message=message,
    )


def _capi_view(store: Loja, config: MetaPixelConfig | None) -> IntegrationView:
    """CAPI é a presença do token cifrado no mesmo registro do Pixel."""
    pixel_id = normalizar_pixel_id(config.pixel_id if config else None)
    has_token = bool(config and config.token_ciphertext)
    if has_token and pixel_id:
        status = IntegrationStatus.CONNECTED
        message = "CAPI conectada (token presente)"
    elif has_token and not pixel_id:
        status = IntegrationStatus.ERROR
        message = "CAPI com token mas sem Pixel ID"
    else:
        status = IntegrationStatus.MISSING
        message = "CAPI não configurada"
    return IntegrationView(
        kind=IntegrationKind.CAPI,
        status=status,
        store_id=store.id,
        store_slug=store.slug,
        fields={
            "pixel_id": pixel_id or None,
            "token_configured": has_token,
            "token_masked": _TOKEN_MASK if has_token else None,
            "enviar_purchase": (
                bool(config.enviar_purchase) if config else True
            ),
        },
        updated_at=config.atualizada_em if config else None,
        health_message=message,
    )


def _ads_view(store: Loja, config: MetaAdsConfig | None) -> IntegrationView:
    account = (config.ad_account_id if config else "") or ""
    has_token = bool(config and config.token_ciphertext)
    sync_status = (config.ultima_sync_status if config else None) or None
    if not account and not has_token:
        status = IntegrationStatus.MISSING
        message = "Meta Ads não configurado"
    elif account and has_token and sync_status == "erro":
        status = IntegrationStatus.ERROR
        message = (config.ultima_sync_erro if config else None) or (
            "Última sincronização Meta Ads falhou"
        )
    elif account and has_token:
        status = IntegrationStatus.CONNECTED
        message = "Meta Ads conectado"
    else:
        status = IntegrationStatus.ERROR
        message = "Meta Ads incompleto: informe conta e token"
    return IntegrationView(
        kind=IntegrationKind.META_ADS,
        status=status,
        store_id=store.id,
        store_slug=store.slug,
        fields={
            "ad_account_id": account or None,
            "ad_account_id_masked": _mask_id(account) if account else None,
            "token_configured": has_token,
            "token_masked": _TOKEN_MASK if has_token else None,
            "sync_enabled": bool(config.sync_enabled) if config else True,
            "ultima_sync_status": sync_status,
            "ultima_sync_em": (
                config.ultima_sync_em.isoformat()
                if config and config.ultima_sync_em is not None
                else None
            ),
            "ultima_sync_resumo": (
                (config.ultima_sync_resumo or None) if config else None
            ),
        },
        updated_at=config.atualizada_em if config else None,
        health_message=message,
    )


def _pixel_audit(config: MetaPixelConfig | None) -> dict[str, object] | None:
    if config is None:
        return None
    return {
        "pixel_id": normalizar_pixel_id(config.pixel_id) or "",
        "token_configured": bool(config.token_ciphertext),
        "test_event_code": config.test_event_code or None,
        "enviar_page_view": bool(config.enviar_page_view),
        "enviar_lead": bool(config.enviar_lead),
        "enviar_purchase": bool(config.enviar_purchase),
    }


def _ads_audit(config: MetaAdsConfig | None) -> dict[str, object] | None:
    if config is None:
        return None
    return {
        "ad_account_id": config.ad_account_id or "",
        "token_configured": bool(config.token_ciphertext),
        "sync_enabled": bool(config.sync_enabled),
        "ultima_sync_status": config.ultima_sync_status or None,
    }
