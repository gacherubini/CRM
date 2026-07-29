from __future__ import annotations

import re
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import gestor_atual
from app.config import settings
from app.control.access import AccessControl
from app.control.audit import AuditTrail
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    AccessibleStore,
    ActiveResponsibleConflict,
    Actor,
    AuditEventView,
    AuditQuery,
    ControlError,
    CreateStore,
    GrantTrafficAccess,
    InvalidStoreTransition,
    ManagerNotFound,
    RevokeTrafficAccess,
    StoreNotFound,
    StoreRef,
    StoreSlugConflict,
    StoreStatus,
    StoreView,
    TrafficLinkView,
    TrafficLinkConflict,
    TrafficLinkNotFound,
    TrafficRole,
    TransitionStore,
)
from app.db import SessionLocal, get_db


def _control_enabled() -> None:
    if not settings.revy_control_enabled:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "recurso não encontrado"},
        )


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


class StoreTransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: StoreStatus
    motivo: str | None = Field(default=None, max_length=1000)


class TrafficGrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gestor_id: str = Field(min_length=1, max_length=36)
    tipo: TrafficRole


class TrafficRevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=1000)


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


def _store_json(store: StoreView) -> dict[str, str]:
    return {
        "id": store.id,
        "nome": store.name,
        "slug": store.slug,
        "estado": store.status.value,
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
    elif isinstance(exc, StoreNotFound):
        status_code, code = 404, "store_not_found"
    elif isinstance(exc, ManagerNotFound):
        status_code, code = 404, "manager_not_found"
    elif isinstance(exc, TrafficLinkNotFound):
        status_code, code = 404, "traffic_link_not_found"
    elif isinstance(exc, StoreSlugConflict):
        status_code, code = 409, "store_slug_conflict"
    elif isinstance(exc, InvalidStoreTransition):
        status_code, code = 409, "invalid_store_transition"
    elif isinstance(exc, ActiveResponsibleConflict):
        status_code, code = 409, "active_responsible_conflict"
    elif isinstance(exc, TrafficLinkConflict):
        status_code, code = 409, "traffic_link_conflict"
    else:
        status_code, code = 409, "control_conflict"
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc
