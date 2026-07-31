from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from app.auth import hash_senha
from app.control.audit import _append_event
from app.control.invitations import _token_hash
from app.control.stores import _find_store
from app.control.types import (
    AccessDenied,
    ActiveResponsibleConflict,
    Actor,
    InvalidPersonEmail,
    InviteTrafficManager,
    StoreNotFound,
    TrafficInviteResult,
    TrafficLinkConflict,
    TrafficRole,
)
from app.models import (
    AcessoControl,
    ConviteAcessoControl,
    GestorRevy,
    Pessoa,
    VinculoTrafego,
    agora,
    novo_id,
)

_INVITATION_LIFETIME = timedelta(hours=24)
_EMAIL_OK = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class TrafficManagerOnboarding:
    """Convida um gestor de tráfego por e-mail e o vincula a uma loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def invite_or_bind(self, actor: Actor, command: InviteTrafficManager) -> TrafficInviteResult:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode convidar gestores de tráfego")
        email = (command.email or "").strip().lower()
        if len(email) > 320 or not _EMAIL_OK.fullmatch(email):
            raise InvalidPersonEmail(email)
        now = agora()
        with self._session_factory() as db:
            store = _find_store(db, command.store)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            person = db.query(Pessoa).filter(Pessoa.email == email).first()
            if person is None:
                name = (command.name or "").strip()
                if not name:
                    raise InvalidPersonEmail(email)
                person = Pessoa(email=email, nome=name[:160], criada_em=now, atualizada_em=now)
                db.add(person)
                db.flush()
            access = db.query(AcessoControl).filter(AcessoControl.pessoa_id == person.id).first()
            token: str | None = None
            already_active = False
            if access is None:
                manager_id = novo_id()
                db.add(GestorRevy(id=manager_id, email=email, nome=person.nome,
                    senha_hash=hash_senha(secrets.token_urlsafe(32)), papel="gestor", ativo=True, criado_em=now))
                access = AcessoControl(id=manager_id, pessoa_id=person.id, papel="gestor",
                    estado="pendente", senha_hash=None, sessao_versao=1, gestor_legado_id=manager_id,
                    criada_em=now, atualizada_em=now)
                db.add(access)
                db.flush()
                token = self._issue_invite(db, access.id, actor.id, now)
            else:
                manager_id = access.gestor_legado_id or access.id
                manager = db.get(GestorRevy, manager_id)
                if manager is None:
                    manager_id = access.id
                    db.add(GestorRevy(id=manager_id, email=email, nome=person.nome,
                        senha_hash=access.senha_hash or hash_senha(secrets.token_urlsafe(32)),
                        papel="gestor", ativo=True, criado_em=now))
                    access.gestor_legado_id = manager_id
                    db.flush()
                if access.estado == "ativo":
                    already_active = True
                else:
                    token = self._issue_invite(db, access.id, actor.id, now)

            self._bind_link(db, store.id, manager_id, command.role, now)
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="traffic_manager.invited",
                resource_type="vinculo_trafego",
                resource_id=manager_id,
                after={
                    "manager_id": manager_id,
                    "role": command.role.value,
                    "already_active": already_active,
                },
            )
            db.commit()
            return TrafficInviteResult(
                store_id=store.id,
                manager_id=manager_id,
                email=email,
                role=command.role,
                token=token,
                already_active=already_active,
            )

    @staticmethod
    def _issue_invite(db: Any, access_id: str, actor_id: str, now) -> str:
        raw_token = secrets.token_urlsafe(32)
        (
            db.query(ConviteAcessoControl)
            .filter(
                ConviteAcessoControl.acesso_id == access_id,
                ConviteAcessoControl.usado_em.is_(None),
                ConviteAcessoControl.revogado_em.is_(None),
            )
            .update({ConviteAcessoControl.revogado_em: now}, synchronize_session=False)
        )
        db.add(
            ConviteAcessoControl(
                acesso_id=access_id,
                token_hash=_token_hash(raw_token),
                expira_em=now + _INVITATION_LIFETIME,
                criado_por_gestor_id=actor_id,
                criado_em=now,
            )
        )
        return raw_token

    @staticmethod
    def _bind_link(
        db: Any,
        store_id: str,
        manager_id: str,
        role: TrafficRole,
        now,
    ) -> None:
        existing = (
            db.query(VinculoTrafego)
            .filter(
                VinculoTrafego.loja_id == store_id,
                VinculoTrafego.gestor_id == manager_id,
                VinculoTrafego.encerrado_em.is_(None),
            )
            .first()
        )
        if existing is not None:
            raise TrafficLinkConflict("o gestor já possui vínculo ativo com a Loja")
        if role is TrafficRole.RESPONSIBLE:
            responsible = (
                db.query(VinculoTrafego)
                .filter(
                    VinculoTrafego.loja_id == store_id,
                    VinculoTrafego.tipo == TrafficRole.RESPONSIBLE.value,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
            )
            if responsible is not None:
                raise ActiveResponsibleConflict(store_id, responsible.gestor_id)
        db.add(
            VinculoTrafego(
                loja_id=store_id,
                gestor_id=manager_id,
                tipo=role.value,
                iniciado_em=now,
            )
        )
