from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.auth import gestor_atual
from app.config import settings
from app.control.access import AccessControl
from app.control.accounts import ControlAccounts
from app.control.audit import AuditTrail
from app.control.contracts import (
    ContractBillingStatus,
    ContractControl,
    ContractNotFound,
    ContractView,
    UpsertContract,
)
from app.control.integrations import (
    IntegrationView,
    IntegrationsControl,
    InvalidIntegrationConfig,
    UpsertMetaAds,
    UpsertPixel,
)
from app.control.google_ads import (
    FakeGoogleAdsTokenExchanger,
    GoogleAdsConnectionControl,
    GoogleAdsConnectionNotFound,
    GoogleAdsConnectionView,
    GoogleAdsOAuthMisconfigured,
    GoogleAdsOAuthStateInvalid,
    GoogleAdsTokenExchangeError,
    OAuthTokenBundle,
)
from app.control.google_ads_conversions import (
    ConversionBindingView,
    GoogleAdsConversionsControl,
    GoogleAdsConversionBindingNotFound,
    GoogleAdsInvalidConversionBinding,
)
from app.control.google_ads_metrics import (
    GoogleAdsAccountNotFound,
    GoogleAdsAccountView,
    GoogleAdsManagerAccountNotSelectable,
    GoogleAdsMetricsControl,
    GoogleAdsNoSelectedAccount,
    GoogleAdsNotConnected,
    MetricsSummary,
    SyncMetricsResult,
)
from app.control.invitations import ControlInvitations
from app.control.password_recovery import ControlPasswordRecovery
from app.control.people import PeopleDirectory
from app.control.portal_import import (
    PortalImportResult,
    PortalUserImporter,
    PortalUserImportRow,
)
from app.control.portfolio import (
    InvalidModuleSelection,
    ModuleCode,
    ModuleView,
    PortfolioConflict,
    PortfolioControl,
)
from app.control.dashboard import (
    DashboardControl,
    DashboardOverview,
    StoreReadinessSummary,
)
from app.control.readiness import AlertAcceptanceView, ReadinessReport, StoreReadiness
from app.control.roles import StoreRoles
from app.control.stores import StoreControl
from app.control.whatsapp_channels import (
    HttpWhatsAppChannels,
    WhatsAppChannelNotFound,
    WhatsAppChannelView,
    WhatsAppChannelsControl,
    WhatsAppChannelsError,
    WhatsAppChannelsPort,
    WhatsAppChannelsUnavailable,
)
from app.control.types import (
    AccessDenied,
    ActivateControlAccess,
    ActivatedControlAccount,
    InvalidAlertAcceptance,
    AccessibleStore,
    ActiveResponsibleConflict,
    Actor,
    AssignStoreRole,
    AuditEventView,
    AuditQuery,
    ControlError,
    ControlAccountConflict,
    ControlAccountRole,
    ControlAccountView,
    ControlInvitationInvalid,
    ControlRecoveryInvalid,
    ConsumeControlPasswordRecovery,
    CreateStore,
    GrantTrafficAccess,
    InvalidPersonEmail,
    InvalidStoreTransition,
    IssueControlPasswordRecovery,
    IssuedControlPasswordRecovery,
    InviteControlAccess,
    IssuedControlInvitation,
    ManagerNotFound,
    PersonEmailConflict,
    PersonNotFound,
    PersonRef,
    PersonView,
    RegisterPerson,
    RecoveredControlAccount,
    RevokeStoreRole,
    RevokeTrafficAccess,
    StoreNotFound,
    StoreEditConflict,
    StoreReadinessBlocked,
    StoreRef,
    StoreSlugConflict,
    StoreStatus,
    StoreRole,
    StoreRoleConflict,
    StoreRoleNotFound,
    StoreRoleRef,
    StoreRoleView,
    StoreView,
    TrafficLinkView,
    TrafficLinkConflict,
    TrafficLinkNotFound,
    TrafficRole,
    TransitionStore,
    UpdateStore,
    WeakControlPassword,
)
from app.db import SessionLocal, get_db

# Injetável em testes para complete_oauth sem chamar Google.
_google_ads_token_exchanger = FakeGoogleAdsTokenExchanger(
    default_bundle=OAuthTokenBundle(
        refresh_token="test-refresh-token-not-for-prod",
        access_token="test-access-token",
    )
)


def _control_enabled() -> None:
    if not settings.revy_control_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


def _google_ads_enabled() -> None:
    _control_enabled()
    if not settings.google_ads_sync_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


def _google_conversions_enabled() -> None:
    _control_enabled()
    if not settings.google_conversions_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


def _control_dashboard_enabled() -> None:
    _control_enabled()
    if not settings.revy_control_dashboard_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


def _google_ads_control() -> GoogleAdsConnectionControl:
    return GoogleAdsConnectionControl(
        SessionLocal,
        client_id=settings.google_ads_oauth_client_id,
        client_secret=settings.google_ads_oauth_client_secret,
        redirect_uri=settings.google_ads_oauth_redirect_uri,
        token_exchanger=_google_ads_token_exchanger,
    )


def _google_ads_metrics_control() -> GoogleAdsMetricsControl:
    return GoogleAdsMetricsControl(SessionLocal)


def _google_ads_conversions_control() -> GoogleAdsConversionsControl:
    return GoogleAdsConversionsControl(SessionLocal)


def _current_actor(
    request: Request,
    db: Session = Depends(get_db),
) -> Actor:
    manager = gestor_atual(request, db)
    if manager is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": "autenticação necessária",
            },
        )
    return Actor(
        id=manager.id,
        email=manager.email,
        name=manager.nome,
        role=manager.papel,
    )


router = APIRouter(
    prefix="/control/v1",
    tags=["control"],
    dependencies=[Depends(_control_enabled)],
)


class StoreCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=120)

    @field_validator("nome")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("nome é obrigatório")
        return normalized

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
            raise ValueError("slug deve ser canônico")
        return normalized


class StoreUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=160)

    @field_validator("nome")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("nome é obrigatório")
        return normalized


class PersonCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("nome")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("nome é obrigatório")
        return normalized


class ControlInvitationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pessoa_id: str = Field(min_length=1, max_length=36)
    papel: ControlAccountRole


class ActivateControlInvitationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)
    senha: str = Field(min_length=1, max_length=256)


class ControlPasswordRecoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acesso_id: str = Field(min_length=1, max_length=36)


class ConsumeControlPasswordRecoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)
    senha: str = Field(min_length=1, max_length=256)


class ModuleConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modulos: list[ModuleCode] = Field(min_length=1, max_length=2)


class ModuleTransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=1000)


class ContractUpsertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor_mensal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    vigencia_inicio: date
    vigencia_fim: date | None = None
    vencimento_dia: int = Field(ge=1, le=31)
    situacao_cobranca: ContractBillingStatus

    @model_validator(mode="after")
    def validate_term(self):
        if (
            self.vigencia_fim is not None
            and self.vigencia_fim < self.vigencia_inicio
        ):
            raise ValueError("vigência do contrato inválida")
        return self


class StoreTransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: StoreStatus
    motivo: str | None = Field(default=None, max_length=1000)


class AlertAcceptanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=1, max_length=1000)


class TrafficGrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gestor_id: str = Field(min_length=1, max_length=36)
    tipo: TrafficRole


class StoreRoleAssignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pessoa_id: str = Field(min_length=1, max_length=36)
    cargo: StoreRole


class StoreRoleRevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=1000)


class PortalUserImportItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    nome: str = Field(default="", max_length=160)
    loja_slug: str = Field(min_length=1, max_length=120)
    cargo: str = Field(min_length=1, max_length=20)
    origem_id: str = Field(min_length=1, max_length=160)
    ativo: bool = True


class PortalUsersImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuarios: list[PortalUserImportItemBody] = Field(default_factory=list)


class TrafficRevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=1000)


class PixelUpsertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pixel_id: str = Field(min_length=1, max_length=64)
    token: str | None = Field(default=None, max_length=512)
    test_event_code: str | None = Field(default=None, max_length=64)
    enviar_page_view: bool = True
    enviar_lead: bool = True
    enviar_purchase: bool = True


class MetaAdsUpsertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ad_account_id: str = Field(min_length=1, max_length=64)
    token: str | None = Field(default=None, max_length=512)
    sync_enabled: bool = True


class IntegrationDisconnectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=1000)


@router.get("/acessos")
def list_control_accounts(actor: Actor = Depends(_current_actor)):
    try:
        accounts = ControlAccounts(SessionLocal).list(actor)
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_control_account_json(account) for account in accounts]}


@router.post("/acessos/{acesso_id}/desativar")
def disable_control_account(
    acesso_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        account = ControlAccounts(SessionLocal).disable(actor, acesso_id)
    except ControlError as exc:
        _raise_domain_error(exc)
    return _control_account_json(account)


@router.post("/acessos/{acesso_id}/reativar")
def enable_control_account(
    acesso_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        account = ControlAccounts(SessionLocal).enable(actor, acesso_id)
    except ControlError as exc:
        _raise_domain_error(exc)
    return _control_account_json(account)


@router.post("/convites", status_code=201)
def issue_control_invitation(
    body: ControlInvitationBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        invitation = ControlInvitations(SessionLocal).issue(
            actor,
            InviteControlAccess(
                person=PersonRef(id=body.pessoa_id),
                role=body.papel,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _issued_invitation_json(invitation)


@router.post("/convites/ativar")
def activate_control_invitation(body: ActivateControlInvitationBody):
    try:
        account = ControlInvitations(SessionLocal).activate(
            ActivateControlAccess(token=body.token, password=body.senha)
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _activated_account_json(account)


@router.post("/recuperacoes", status_code=201)
def issue_control_password_recovery(
    body: ControlPasswordRecoveryBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        recovery = ControlPasswordRecovery(SessionLocal).issue(
            actor,
            IssueControlPasswordRecovery(access_id=body.acesso_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _issued_recovery_json(recovery)


@router.post("/recuperacoes/consumir")
def consume_control_password_recovery(
    body: ConsumeControlPasswordRecoveryBody,
):
    try:
        account = ControlPasswordRecovery(SessionLocal).consume(
            ConsumeControlPasswordRecovery(
                token=body.token,
                password=body.senha,
            )
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _recovered_account_json(account)


@router.post("/pessoas", status_code=201)
def create_person(
    body: PersonCreateBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        person = PeopleDirectory(SessionLocal).register(
            actor,
            RegisterPerson(name=body.nome, email=body.email),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _person_json(person)


@router.get("/pessoas")
def find_person_by_email(
    email: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        person = PeopleDirectory(SessionLocal).find_by_email(actor, email)
        if person is None:
            raise PersonNotFound("Pessoa Revy não encontrada")
    except ControlError as exc:
        _raise_domain_error(exc)
    return _person_json(person)


@router.get("/pessoas/{pessoa_id}")
def get_person(
    pessoa_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        person = PeopleDirectory(SessionLocal).get(
            actor,
            PersonRef(id=pessoa_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _person_json(person)


@router.get("/lojas")
def list_stores(actor: Actor = Depends(_current_actor)):
    items = AccessControl(SessionLocal).scope(actor)
    return {"items": [_accessible_store_json(item) for item in items]}


@router.post("/lojas", status_code=201)
def create_store(
    body: StoreCreateBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        store = StoreControl(SessionLocal).create(
            actor,
            CreateStore(name=body.nome, slug=body.slug),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_json(store)


@router.get("/lojas/{loja_id}")
def get_store(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        store = StoreControl(SessionLocal).get(actor, StoreRef(id=loja_id))
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_json(store)


@router.get("/dashboard", dependencies=[Depends(_control_dashboard_enabled)])
def get_dashboard_summary(actor: Actor = Depends(_current_actor)):
    overview = DashboardControl(SessionLocal).overview(actor)
    return _dashboard_overview_json(overview)


@router.get("/lojas/{loja_id}/prontidao")
def get_store_readiness(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        report = StoreReadiness(SessionLocal).evaluate(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _readiness_json(report)


@router.post("/lojas/{loja_id}/prontidao/alertas/{check_code}/aceitar")
def accept_store_readiness_alert(
    loja_id: str,
    check_code: str,
    body: AlertAcceptanceBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        acceptance = StoreReadiness(SessionLocal).accept_alert(
            actor,
            StoreRef(id=loja_id),
            check_code,
            body.motivo,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _alert_acceptance_json(acceptance)


@router.get("/lojas/{loja_id}/integracoes")
def list_store_integrations(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        items = IntegrationsControl(SessionLocal).list(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_integration_json(item) for item in items]}


@router.put("/lojas/{loja_id}/integracoes/pixel")
def upsert_store_pixel(
    loja_id: str,
    body: PixelUpsertBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        view = IntegrationsControl(SessionLocal).upsert_pixel(
            actor,
            UpsertPixel(
                store=StoreRef(id=loja_id),
                pixel_id=body.pixel_id,
                token=body.token,
                test_event_code=body.test_event_code,
                enviar_page_view=body.enviar_page_view,
                enviar_lead=body.enviar_lead,
                enviar_purchase=body.enviar_purchase,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _integration_json(view)


@router.post("/lojas/{loja_id}/integracoes/pixel/desconectar")
def disconnect_store_pixel(
    loja_id: str,
    body: IntegrationDisconnectBody | None = None,
    actor: Actor = Depends(_current_actor),
):
    payload = body or IntegrationDisconnectBody()
    try:
        view = IntegrationsControl(SessionLocal).disconnect_pixel(
            actor,
            StoreRef(id=loja_id),
            reason=payload.motivo,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _integration_json(view)


@router.put("/lojas/{loja_id}/integracoes/meta-ads")
def upsert_store_meta_ads(
    loja_id: str,
    body: MetaAdsUpsertBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        view = IntegrationsControl(SessionLocal).upsert_meta_ads(
            actor,
            UpsertMetaAds(
                store=StoreRef(id=loja_id),
                ad_account_id=body.ad_account_id,
                token=body.token,
                sync_enabled=body.sync_enabled,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _integration_json(view)


@router.post("/lojas/{loja_id}/integracoes/meta-ads/desconectar")
def disconnect_store_meta_ads(
    loja_id: str,
    body: IntegrationDisconnectBody | None = None,
    actor: Actor = Depends(_current_actor),
):
    payload = body or IntegrationDisconnectBody()
    try:
        view = IntegrationsControl(SessionLocal).disconnect_meta_ads(
            actor,
            StoreRef(id=loja_id),
            reason=payload.motivo,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _integration_json(view)


# Port injetável em testes (InMemory); None → adapter HTTP do Chatbot.
_whatsapp_channels_port: WhatsAppChannelsPort | None = None


def set_whatsapp_channels_port(port: WhatsAppChannelsPort | None) -> None:
    """Sobrescreve o adapter de canais (testes). None restaura o HTTP padrão."""
    global _whatsapp_channels_port
    _whatsapp_channels_port = port


def _whatsapp_channels_port_or_default() -> WhatsAppChannelsPort:
    if _whatsapp_channels_port is not None:
        return _whatsapp_channels_port
    return HttpWhatsAppChannels(
        base_url=settings.chatbot_url,
        token_for_slug=settings.chatbot_token_para,
        session_factory=SessionLocal,
    )


class WhatsAppCanalRegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evolution_instance: str = Field(min_length=1, max_length=120)
    e164_or_label: str = Field(min_length=1, max_length=80)


def _whatsapp_control() -> WhatsAppChannelsControl:
    return WhatsAppChannelsControl(
        SessionLocal,
        _whatsapp_channels_port_or_default(),
    )


def _require_multi_whatsapp() -> None:
    if not settings.multi_whatsapp_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


@router.get("/lojas/{loja_id}/whatsapp-canais")
def list_store_whatsapp_channels(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    """Lista canais WhatsApp da loja (proxy Chatbot). Exige MULTI_WHATSAPP."""
    _require_multi_whatsapp()
    try:
        channels = _whatsapp_control().list_channels(actor, StoreRef(id=loja_id))
    except ControlError as exc:
        _raise_domain_error(exc)
    return {
        "items": [_whatsapp_channel_json(c) for c in channels],
    }


@router.post("/lojas/{loja_id}/whatsapp-canais", status_code=201)
def register_store_whatsapp_channel(
    loja_id: str,
    body: WhatsAppCanalRegisterBody,
    actor: Actor = Depends(_current_actor),
):
    """Cadastra canal (proxy). Admin/Responsável; colaborador → 403."""
    _require_multi_whatsapp()
    try:
        channel = _whatsapp_control().register(
            actor,
            StoreRef(id=loja_id),
            instance=body.evolution_instance,
            label=body.e164_or_label,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _whatsapp_channel_json(channel)


@router.post("/lojas/{loja_id}/whatsapp-canais/{canal_id}/connect")
def connect_store_whatsapp_channel(
    loja_id: str,
    canal_id: str,
    actor: Actor = Depends(_current_actor),
):
    """Conecta/pareia canal; QR com Cache-Control: no-store."""
    _require_multi_whatsapp()
    try:
        channel = _whatsapp_control().connect(
            actor, StoreRef(id=loja_id), canal_id
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return JSONResponse(
        content=_whatsapp_channel_json(channel),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
        },
    )


@router.post("/lojas/{loja_id}/whatsapp-canais/{canal_id}/disconnect")
def disconnect_store_whatsapp_channel(
    loja_id: str,
    canal_id: str,
    actor: Actor = Depends(_current_actor),
):
    """Desconecta canal. Admin/Responsável; colaborador → 403."""
    _require_multi_whatsapp()
    try:
        channel = _whatsapp_control().disconnect(
            actor, StoreRef(id=loja_id), canal_id
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _whatsapp_channel_json(channel)


@router.post("/lojas/{loja_id}/whatsapp-canais/{canal_id}/inativar")
def inactivate_store_whatsapp_channel(
    loja_id: str,
    canal_id: str,
    actor: Actor = Depends(_current_actor),
):
    """Inativa canal. Admin/Responsável; colaborador → 403."""
    _require_multi_whatsapp()
    try:
        channel = _whatsapp_control().inactivate(
            actor, StoreRef(id=loja_id), canal_id
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _whatsapp_channel_json(channel)


def _whatsapp_channel_json(channel: WhatsAppChannelView) -> dict[str, object]:
    out: dict[str, object] = {
        "id": channel.id,
        "loja_id": channel.loja_id,
        "e164_or_label": channel.e164_or_label,
        "evolution_instance": channel.evolution_instance,
        "ativo": channel.ativo,
        "estado": channel.estado,
        "criado_em": channel.criado_em,
    }
    if channel.qr_payload is not None:
        out["qr_payload"] = channel.qr_payload
    if channel.expires_in_seconds is not None:
        out["expires_in_seconds"] = channel.expires_in_seconds
    return out


@router.patch("/lojas/{loja_id}")
def update_store(
    loja_id: str,
    body: StoreUpdateBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        store = StoreControl(SessionLocal).update(
            actor,
            UpdateStore(
                store=StoreRef(id=loja_id),
                name=body.nome,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_json(store)


@router.get("/lojas/{loja_id}/modulos")
def list_store_modules(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        modules = PortfolioControl(SessionLocal).list_modules(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_module_json(module) for module in modules]}


@router.put("/lojas/{loja_id}/modulos")
def configure_store_modules(
    loja_id: str,
    body: ModuleConfigurationBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        modules = PortfolioControl(SessionLocal).configure(
            actor,
            StoreRef(id=loja_id),
            tuple(module.value for module in body.modulos),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_module_json(module) for module in modules]}


@router.post("/lojas/{loja_id}/modulos/{modulo}/suspender")
def suspend_store_module(
    loja_id: str,
    modulo: str,
    body: ModuleTransitionBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        module = PortfolioControl(SessionLocal).suspend(
            actor,
            StoreRef(id=loja_id),
            modulo,
            reason=body.motivo,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _module_json(module)


@router.post("/lojas/{loja_id}/modulos/{modulo}/reativar")
def activate_store_module(
    loja_id: str,
    modulo: str,
    body: ModuleTransitionBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        module = PortfolioControl(SessionLocal).activate(
            actor,
            StoreRef(id=loja_id),
            modulo,
            reason=body.motivo,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _module_json(module)


@router.get("/lojas/{loja_id}/contrato")
def get_store_contract(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        contract = ContractControl(SessionLocal).get(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _contract_json(contract)


@router.put("/lojas/{loja_id}/contrato")
def upsert_store_contract(
    loja_id: str,
    body: ContractUpsertBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        contract = ContractControl(SessionLocal).upsert(
            actor,
            UpsertContract(
                store=StoreRef(id=loja_id),
                monthly_amount=body.valor_mensal,
                starts_on=body.vigencia_inicio,
                ends_on=body.vigencia_fim,
                due_day=body.vencimento_dia,
                billing_status=body.situacao_cobranca,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _contract_json(contract)


@router.post("/imports/portal-usuarios")
def import_portal_users(
    body: PortalUsersImportBody,
    actor: Actor = Depends(_current_actor),
):
    """Importa usuários do Portal como Pessoa + CargoLoja (push, Admin)."""
    rows = tuple(
        PortalUserImportRow(
            email=item.email,
            name=item.nome,
            store_slug=item.loja_slug,
            role=item.cargo,
            origem_id=item.origem_id,
            active=item.ativo,
        )
        for item in body.usuarios
    )
    try:
        result = PortalUserImporter(SessionLocal).import_rows(actor, rows)
    except ControlError as exc:
        _raise_domain_error(exc)
    return _portal_import_json(result)


@router.post("/lojas/{loja_id}/cargos", status_code=201)
def assign_store_role(
    loja_id: str,
    body: StoreRoleAssignBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        role = StoreRoles(SessionLocal).assign(
            actor,
            AssignStoreRole(
                store=StoreRef(id=loja_id),
                person=PersonRef(id=body.pessoa_id),
                role=body.cargo,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_role_json(role)


@router.get("/lojas/{loja_id}/cargos")
def list_store_roles(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        roles = StoreRoles(SessionLocal).list_for_store(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_store_role_json(role) for role in roles]}


@router.post("/lojas/{loja_id}/cargos/{cargo_id}/revogar")
def revoke_store_role(
    loja_id: str,
    cargo_id: str,
    body: StoreRoleRevokeBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        role = StoreRoles(SessionLocal).revoke(
            actor,
            RevokeStoreRole(
                store=StoreRef(id=loja_id),
                assignment=StoreRoleRef(id=cargo_id),
                reason=body.motivo,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_role_json(role)


@router.post("/lojas/{loja_id}/estado")
def transition_store(
    loja_id: str,
    body: StoreTransitionBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        store = StoreControl(SessionLocal).transition(
            actor,
            TransitionStore(
                store=StoreRef(id=loja_id),
                target=body.estado,
                reason=body.motivo,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _store_json(store)


@router.post("/lojas/{loja_id}/gestores", status_code=201)
def grant_traffic_access(
    loja_id: str,
    body: TrafficGrantBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        link = AccessControl(SessionLocal).grant(
            actor,
            GrantTrafficAccess(
                store=StoreRef(id=loja_id),
                manager_id=body.gestor_id,
                role=body.tipo,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _traffic_link_json(link)


@router.post("/lojas/{loja_id}/gestores/{gestor_id}/revogar")
def revoke_traffic_access(
    loja_id: str,
    gestor_id: str,
    body: TrafficRevokeBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        link = AccessControl(SessionLocal).revoke(
            actor,
            RevokeTrafficAccess(
                store=StoreRef(id=loja_id),
                manager_id=gestor_id,
                reason=body.motivo,
            ),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _traffic_link_json(link)


@router.get("/lojas/{loja_id}/auditoria")
def list_store_audit(
    loja_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    actor: Actor = Depends(_current_actor),
):
    try:
        page = AuditTrail(SessionLocal).list(
            actor,
            AuditQuery(store_id=loja_id, limit=limit),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_audit_event_json(event) for event in page.items]}


@router.post(
    "/lojas/{loja_id}/google-ads/oauth/start",
    dependencies=[Depends(_google_ads_enabled)],
)
def start_google_ads_oauth(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        result = _google_ads_control().start_oauth(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {
        "auth_url": result.auth_url,
        "state": result.state,
        "expira_em": result.expires_at.isoformat(),
    }


@router.get(
    "/google-ads/oauth/callback",
    dependencies=[Depends(_google_ads_enabled)],
)
def google_ads_oauth_callback(
    state: str = Query(min_length=1, max_length=128),
    code: str = Query(min_length=1, max_length=512),
):
    """Callback OAuth do Google — valida state e troca code (sem expor token)."""
    try:
        connection = _google_ads_control().complete_oauth(
            state=state,
            code=code,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_connection_json(connection)


@router.get(
    "/lojas/{loja_id}/google-ads/connection",
    dependencies=[Depends(_google_ads_enabled)],
)
def get_google_ads_connection(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        connection = _google_ads_control().get(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_connection_json(connection)


@router.delete(
    "/lojas/{loja_id}/google-ads/connection",
    dependencies=[Depends(_google_ads_enabled)],
)
def disconnect_google_ads_connection(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        connection = _google_ads_control().disconnect(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_connection_json(connection)


def _google_ads_connection_json(
    connection: GoogleAdsConnectionView,
) -> dict[str, object]:
    # Nunca incluir refresh token (nem ciphertext) na resposta HTTP.
    return {
        "id": connection.id,
        "loja_id": connection.loja_id,
        "status": connection.status,
        "customer_id": connection.customer_id,
        "login_customer_id": connection.login_customer_id,
        "scopes": connection.scopes,
        "has_refresh_token": connection.has_refresh_token,
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }


class GoogleAdsSyncMetricsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: str = Field(min_length=10, max_length=10)
    date_to: str = Field(min_length=10, max_length=10)


class GoogleAdsBindConversionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revy_event_type: str = Field(min_length=1, max_length=80)
    conversion_action_resource_name: str = Field(min_length=1, max_length=240)
    customer_id: str = Field(min_length=1, max_length=20)
    active: bool = True


@router.get(
    "/lojas/{loja_id}/google-ads/accounts",
    dependencies=[Depends(_google_ads_enabled)],
)
def list_google_ads_accounts(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        items = _google_ads_metrics_control().list_accounts(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_google_ads_account_json(a) for a in items]}


@router.post(
    "/lojas/{loja_id}/google-ads/accounts/sync",
    dependencies=[Depends(_google_ads_enabled)],
)
def sync_google_ads_accounts(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        items = _google_ads_metrics_control().sync_accounts(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_google_ads_account_json(a) for a in items]}


@router.post(
    "/lojas/{loja_id}/google-ads/accounts/{customer_id}/select",
    dependencies=[Depends(_google_ads_enabled)],
)
def select_google_ads_account(
    loja_id: str,
    customer_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        account = _google_ads_metrics_control().select_account(
            actor,
            StoreRef(id=loja_id),
            customer_id,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_account_json(account)


@router.post(
    "/lojas/{loja_id}/google-ads/metrics/sync",
    dependencies=[Depends(_google_ads_enabled)],
)
def sync_google_ads_metrics(
    loja_id: str,
    body: GoogleAdsSyncMetricsBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        result = _google_ads_metrics_control().sync_metrics(
            actor,
            StoreRef(id=loja_id),
            date_from=body.date_from,
            date_to=body.date_to,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_sync_metrics_json(result)


@router.get(
    "/lojas/{loja_id}/google-ads/metrics/summary",
    dependencies=[Depends(_google_ads_enabled)],
)
def get_google_ads_metrics_summary(
    loja_id: str,
    date_from: str = Query(min_length=10, max_length=10),
    date_to: str = Query(min_length=10, max_length=10),
    actor: Actor = Depends(_current_actor),
):
    try:
        summary = _google_ads_metrics_control().metrics_summary(
            actor,
            StoreRef(id=loja_id),
            date_from=date_from,
            date_to=date_to,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_metrics_summary_json(summary)


@router.get(
    "/lojas/{loja_id}/google-ads/conversion-bindings",
    dependencies=[Depends(_google_conversions_enabled)],
)
def list_google_ads_conversion_bindings(
    loja_id: str,
    actor: Actor = Depends(_current_actor),
):
    try:
        items = _google_ads_conversions_control().list_bindings(
            actor,
            StoreRef(id=loja_id),
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return {"items": [_google_ads_binding_json(b) for b in items]}


@router.post(
    "/lojas/{loja_id}/google-ads/conversion-bindings",
    dependencies=[Depends(_google_conversions_enabled)],
)
def bind_google_ads_conversion_action(
    loja_id: str,
    body: GoogleAdsBindConversionBody,
    actor: Actor = Depends(_current_actor),
):
    try:
        binding = _google_ads_conversions_control().bind_conversion_action(
            actor,
            StoreRef(id=loja_id),
            revy_event_type=body.revy_event_type,
            conversion_action_resource_name=body.conversion_action_resource_name,
            customer_id=body.customer_id,
            active=body.active,
        )
    except ControlError as exc:
        _raise_domain_error(exc)
    return _google_ads_binding_json(binding)


def _google_ads_account_json(account: GoogleAdsAccountView) -> dict[str, object]:
    return {
        "id": account.id,
        "loja_id": account.loja_id,
        "customer_id": account.customer_id,
        "login_customer_id": account.login_customer_id,
        "is_manager": account.is_manager,
        "currency_code": account.currency_code,
        "time_zone": account.time_zone,
        "descriptive_name": account.descriptive_name,
        "selected": account.selected,
        "status": account.status,
    }


def _google_ads_sync_metrics_json(result: SyncMetricsResult) -> dict[str, object]:
    return {
        "loja_id": result.loja_id,
        "customer_id": result.customer_id,
        "rows_upserted": result.rows_upserted,
        "date_from": result.date_from,
        "date_to": result.date_to,
    }


def _google_ads_metrics_summary_json(summary: MetricsSummary) -> dict[str, object]:
    # Sem tokens/segredos; apenas agregados de medição.
    return {
        "loja_id": summary.loja_id,
        "customer_id": summary.customer_id,
        "date_from": summary.date_from,
        "date_to": summary.date_to,
        "impressions": summary.impressions,
        "clicks": summary.clicks,
        "cost_micros": summary.cost_micros,
        "cost": str(summary.cost),
        "conversions": str(summary.conversions),
        "conversions_value": str(summary.conversions_value),
        "currency_code": summary.currency_code,
        "ctr": str(summary.ctr) if summary.ctr is not None else None,
        "cpc": str(summary.cpc) if summary.cpc is not None else None,
    }


def _google_ads_binding_json(binding: ConversionBindingView) -> dict[str, object]:
    return {
        "id": binding.id,
        "loja_id": binding.loja_id,
        "revy_event_type": binding.revy_event_type,
        "conversion_action_resource_name": binding.conversion_action_resource_name,
        "customer_id": binding.customer_id,
        "active": binding.active,
    }


def _store_json(store: StoreView) -> dict[str, str]:
    return {
        "id": store.id,
        "nome": store.name,
        "slug": store.slug,
        "estado": store.status.value,
    }


def _readiness_json(report: ReadinessReport) -> dict[str, object]:
    return {
        "loja_id": report.store_id,
        "estado": report.status.value,
        "pronta": report.ready,
        "checks": [
            {
                "codigo": check.code,
                "ok": check.ok,
                "severidade": check.severity,
                "mensagem": check.message,
                "aceito": check.accepted,
            }
            for check in report.checks
        ],
    }


def _alert_acceptance_json(view: AlertAcceptanceView) -> dict[str, object]:
    accepted_at = view.accepted_at
    return {
        "loja_id": view.store_id,
        "check_code": view.check_code,
        "aceito_por": view.accepted_by,
        "motivo": view.reason,
        "aceito_em": (
            accepted_at.isoformat()
            if hasattr(accepted_at, "isoformat")
            else str(accepted_at)
        ),
    }


def _integration_json(view: IntegrationView) -> dict[str, object]:
    return {
        "tipo": view.kind.value,
        "status": view.status.value,
        "loja_id": view.store_id,
        "loja_slug": view.store_slug,
        "campos": view.fields,
        "atualizada_em": (
            view.updated_at.isoformat() if view.updated_at is not None else None
        ),
        "saude": view.health_message,
    }


def _dashboard_item_json(item: StoreReadinessSummary) -> dict[str, object]:
    return {
        "store_id": item.store_id,
        "slug": item.slug,
        "name": item.name,
        "status": item.status.value,
        "ready": item.ready,
    }


def _dashboard_overview_json(overview: DashboardOverview) -> dict[str, object]:
    return {
        "counts": {
            "ativas": overview.counts.ativas,
            "em_configuracao": overview.counts.em_configuracao,
            "suspensas": overview.counts.suspensas,
            "erro": overview.counts.erro,
        },
        "items": [_dashboard_item_json(item) for item in overview.items],
        "pending_readiness": [
            {
                "store_id": item.store_id,
                "slug": item.slug,
                "name": item.name,
                "status": item.status.value,
                "failing_codes": list(item.failing_codes),
            }
            for item in overview.pending_readiness
        ],
        "integrations": [
            {
                "store_id": item.store_id,
                "slug": item.slug,
                "pixel_connected": item.pixel_connected,
                "meta_ads_connected": item.meta_ads_connected,
                "google_status": item.google_status,
                "whatsapp_channels": item.whatsapp_channels,
            }
            for item in overview.integrations
        ],
    }


def _person_json(person: PersonView) -> dict[str, str]:
    return {
        "id": person.id,
        "nome": person.name,
        "email": person.email,
        "criado_em": person.created_at.isoformat(),
        "atualizado_em": person.updated_at.isoformat(),
    }


def _control_account_json(account: ControlAccountView) -> dict[str, object]:
    return {
        "id": account.id,
        "pessoa": {
            "id": account.person_id,
            "nome": account.person_name,
            "email": account.person_email,
        },
        "papel": account.role.value,
        "estado": account.status.value,
        "criado_em": account.created_at.isoformat(),
        "atualizado_em": account.updated_at.isoformat(),
    }


def _module_json(module: ModuleView) -> dict[str, object]:
    return {
        "codigo": module.code.value,
        "nome": module.name,
        "estado": module.status.value,
        "versao": module.version,
    }


def _contract_json(contract: ContractView) -> dict[str, object]:
    return {
        "id": contract.id,
        "loja_id": contract.store_id,
        "valor_mensal": f"{contract.monthly_amount:.2f}",
        "moeda": contract.currency,
        "vigencia_inicio": contract.starts_on.isoformat(),
        "vigencia_fim": (
            contract.ends_on.isoformat()
            if contract.ends_on is not None
            else None
        ),
        "vencimento_dia": contract.due_day,
        "situacao_cobranca": contract.billing_status.value,
    }


def _issued_invitation_json(
    invitation: IssuedControlInvitation,
) -> dict[str, str]:
    return {
        "acesso_id": invitation.access_id,
        "pessoa_email": invitation.person_email,
        "token": invitation.token,
        "expira_em": invitation.expires_at.isoformat(),
    }


def _activated_account_json(
    account: ActivatedControlAccount,
) -> dict[str, str]:
    return {
        "acesso_id": account.access_id,
        "pessoa_email": account.person_email,
        "papel": account.role.value,
        "estado": account.status.value,
    }


def _issued_recovery_json(
    recovery: IssuedControlPasswordRecovery,
) -> dict[str, str]:
    return {
        "acesso_id": recovery.access_id,
        "pessoa_email": recovery.person_email,
        "token": recovery.token,
        "expira_em": recovery.expires_at.isoformat(),
    }


def _recovered_account_json(
    account: RecoveredControlAccount,
) -> dict[str, str]:
    return {
        "acesso_id": account.access_id,
        "pessoa_email": account.person_email,
        "estado": account.status.value,
    }


def _store_role_json(role: StoreRoleView) -> dict[str, object]:
    return {
        "id": role.id,
        "loja_id": role.store_id,
        "pessoa_id": role.person_id,
        "cargo": role.role.value,
        "ativo": role.active,
        "iniciado_em": role.started_at.isoformat(),
        "encerrado_em": role.ended_at.isoformat() if role.ended_at else None,
    }


def _portal_import_json(result: PortalImportResult) -> dict[str, object]:
    return {
        "importados": result.imported,
        "ignorados": result.skipped,
        "conflitos": [
            {
                "email": conflict.email,
                "loja_slug": conflict.store_slug,
                "code": conflict.code,
                "message": conflict.message,
            }
            for conflict in result.conflicts
        ],
    }


def _traffic_link_json(link: TrafficLinkView) -> dict[str, object]:
    return {
        "id": link.id,
        "loja_id": link.store_id,
        "gestor_id": link.manager_id,
        "tipo": link.role.value,
        "ativo": link.active,
        "iniciado_em": link.started_at.isoformat(),
        "encerrado_em": link.ended_at.isoformat() if link.ended_at else None,
    }


def _audit_event_json(event: AuditEventView) -> dict[str, object]:
    return {
        "id": event.id,
        "loja_id": event.store_id,
        "ator_id": event.actor_id,
        "ator_email": event.actor_email,
        "acao": event.action,
        "recurso_tipo": event.resource_type,
        "recurso_id": event.resource_id,
        "resultado": event.result.value,
        "antes": event.before,
        "depois": event.after,
        "motivo": event.reason,
        "criado_em": event.created_at.isoformat(),
    }


def _accessible_store_json(item: AccessibleStore) -> dict[str, str | None]:
    return {
        **_store_json(item.store),
        "vinculo": item.role.value if item.role else None,
    }


def _raise_domain_error(exc: ControlError) -> NoReturn:
    if isinstance(exc, AccessDenied):
        status_code, code = 403, "access_denied"
    elif isinstance(exc, InvalidPersonEmail):
        status_code, code = 400, "invalid_person_email"
    elif isinstance(exc, InvalidIntegrationConfig):
        status_code, code = 400, "invalid_integration_config"
    elif isinstance(exc, PersonNotFound):
        status_code, code = 404, "person_not_found"
    elif isinstance(exc, StoreNotFound):
        status_code, code = 404, "store_not_found"
    elif isinstance(exc, ContractNotFound):
        status_code, code = 404, "contract_not_found"
    elif isinstance(exc, ManagerNotFound):
        status_code, code = 404, "manager_not_found"
    elif isinstance(exc, TrafficLinkNotFound):
        status_code, code = 404, "traffic_link_not_found"
    elif isinstance(exc, GoogleAdsConnectionNotFound):
        status_code, code = 404, "google_ads_connection_not_found"
    elif isinstance(exc, GoogleAdsOAuthStateInvalid):
        status_code, code = 400, "google_ads_oauth_state_invalid"
    elif isinstance(exc, GoogleAdsOAuthMisconfigured):
        status_code, code = 503, "google_ads_oauth_misconfigured"
    elif isinstance(exc, GoogleAdsTokenExchangeError):
        status_code, code = 502, "google_ads_token_exchange_error"
    elif isinstance(exc, GoogleAdsManagerAccountNotSelectable):
        status_code, code = 400, "google_ads_manager_not_selectable"
    elif isinstance(exc, GoogleAdsAccountNotFound):
        status_code, code = 404, "google_ads_account_not_found"
    elif isinstance(exc, GoogleAdsNotConnected):
        status_code, code = 409, "google_ads_not_connected"
    elif isinstance(exc, GoogleAdsNoSelectedAccount):
        status_code, code = 409, "google_ads_no_selected_account"
    elif isinstance(exc, GoogleAdsConversionBindingNotFound):
        status_code, code = 404, "google_ads_conversion_binding_not_found"
    elif isinstance(exc, GoogleAdsInvalidConversionBinding):
        status_code, code = 400, "google_ads_invalid_conversion_binding"
    elif isinstance(exc, StoreSlugConflict):
        status_code, code = 409, "store_slug_conflict"
    elif isinstance(exc, StoreEditConflict):
        status_code, code = 409, "store_edit_conflict"
    elif isinstance(exc, PersonEmailConflict):
        status_code, code = 409, "person_email_conflict"
    elif isinstance(exc, ControlAccountConflict):
        status_code, code = 409, "control_account_conflict"
    elif isinstance(exc, ControlInvitationInvalid):
        status_code, code = 409, "control_invitation_invalid"
    elif isinstance(exc, ControlRecoveryInvalid):
        status_code, code = 409, "control_recovery_invalid"
    elif isinstance(exc, WeakControlPassword):
        status_code, code = 400, "weak_control_password"
    elif isinstance(exc, InvalidModuleSelection):
        status_code, code = 400, "invalid_module_selection"
    elif isinstance(exc, PortfolioConflict):
        status_code, code = 409, "portfolio_conflict"
    elif isinstance(exc, StoreRoleNotFound):
        status_code, code = 404, "store_role_not_found"
    elif isinstance(exc, StoreRoleConflict):
        status_code, code = 409, "store_role_conflict"
    elif isinstance(exc, StoreReadinessBlocked):
        status_code, code = 409, "store_readiness_blocked"
    elif isinstance(exc, InvalidAlertAcceptance):
        status_code, code = 400, "invalid_alert_acceptance"
    elif isinstance(exc, InvalidStoreTransition):
        status_code, code = 409, "invalid_store_transition"
    elif isinstance(exc, ActiveResponsibleConflict):
        status_code, code = 409, "active_responsible_conflict"
    elif isinstance(exc, TrafficLinkConflict):
        status_code, code = 409, "traffic_link_conflict"
    elif isinstance(exc, WhatsAppChannelNotFound):
        status_code, code = 404, "whatsapp_channel_not_found"
    elif isinstance(exc, WhatsAppChannelsUnavailable):
        status_code, code = 503, "whatsapp_channels_unavailable"
    elif isinstance(exc, WhatsAppChannelsError):
        status_code, code = 502, "whatsapp_channels_error"
    else:
        status_code, code = 409, "control_conflict"
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc
