from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.control.types import (
    AccessDenied,
    Actor,
    ControlAccountRole,
    ControlAccountStatus,
    ControlAccountView,
)
from app.models import AcessoControl, Pessoa


class ControlAccounts:
    """Leitura administrativa dos acessos globais ao Revy Control."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def list(self, actor: Actor) -> tuple[ControlAccountView, ...]:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode consultar acessos do Control")

        with self._session_factory() as db:
            rows = (
                db.query(AcessoControl, Pessoa)
                .join(Pessoa, Pessoa.id == AcessoControl.pessoa_id)
                .order_by(Pessoa.email, AcessoControl.id)
                .all()
            )
            return tuple(
                ControlAccountView(
                    id=access.id,
                    person_id=person.id,
                    person_name=person.nome,
                    person_email=person.email,
                    role=ControlAccountRole(access.papel),
                    status=ControlAccountStatus(access.estado),
                    created_at=access.criada_em,
                    updated_at=access.atualizada_em,
                )
                for access, person in rows
            )
