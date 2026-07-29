from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.control.audit import _append_event
from app.control.types import (
    AccessDenied,
    Actor,
    InvalidPersonEmail,
    PersonEmailConflict,
    PersonNotFound,
    PersonRef,
    PersonView,
    RegisterPerson,
)
from app.models import Pessoa

_VALID_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class PeopleDirectory:
    """Cadastro canônico de Pessoas Revy, sem credenciais ou permissões."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def register(self, actor: Actor, command: RegisterPerson) -> PersonView:
        _require_admin(actor)
        name = command.name.strip()
        email = _normalize_email(command.email)
        if not name or len(name) > 160:
            raise ValueError("nome da Pessoa Revy é obrigatório e deve ter até 160 caracteres")

        with self._session_factory() as db:
            if db.query(Pessoa).filter(Pessoa.email == email).first() is not None:
                raise PersonEmailConflict(email)
            person = Pessoa(nome=name, email=email)
            db.add(person)
            try:
                db.flush()
                _append_event(
                    db,
                    actor=actor,
                    store_id=None,
                    action="person.registered",
                    resource_type="pessoa",
                    resource_id=person.id,
                    after={"name": person.nome, "email": person.email},
                )
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise PersonEmailConflict(email) from exc
            db.refresh(person)
            return _person_view(person)

    def get(self, actor: Actor, person: PersonRef) -> PersonView:
        _require_admin(actor)
        with self._session_factory() as db:
            row = db.get(Pessoa, person.id)
            if row is None:
                raise PersonNotFound("Pessoa Revy não encontrada")
            return _person_view(row)

    def find_by_email(self, actor: Actor, email: str) -> PersonView | None:
        _require_admin(actor)
        normalized = _normalize_email(email)
        with self._session_factory() as db:
            row = db.query(Pessoa).filter(Pessoa.email == normalized).first()
            return _person_view(row) if row is not None else None


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise AccessDenied("somente Admin Revy pode administrar Pessoas Revy")


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if (
        len(normalized) > 320
        or not _VALID_EMAIL.fullmatch(normalized)
    ):
        raise InvalidPersonEmail(email)
    return normalized


def _person_view(person: Pessoa) -> PersonView:
    return PersonView(
        id=person.id,
        name=person.nome,
        email=person.email,
        created_at=person.criada_em,
        updated_at=person.atualizada_em,
    )
