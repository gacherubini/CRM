"""Importa usuários do Portal como Pessoa + CargoLoja (push, idempotente).

Não conecta ao banco do Portal: o Admin envia o payload. Usuários do
portal-gestao.usuarios permanecem como projeção/legado — este import
apenas materializa identidade e cargo no Control.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.control.people import PeopleDirectory
from app.control.roles import StoreRoles
from app.control.types import (
    AccessDenied,
    Actor,
    AssignStoreRole,
    InvalidPersonEmail,
    PersonEmailConflict,
    PersonRef,
    RegisterPerson,
    StoreRef,
    StoreRole,
    StoreRoleConflict,
)
from app.models import CargoLoja, Loja

_ROLE_BY_VALUE = {role.value: role for role in StoreRole}
_PORTAL_ORIGEM = "portal"


@dataclass(frozen=True)
class PortalUserImportRow:
    """Comando versionável de provisionamento pessoa/cargo a partir do Portal."""

    email: str
    name: str
    store_slug: str
    role: str
    origem_id: str
    active: bool = True


@dataclass(frozen=True)
class PortalImportConflict:
    email: str
    store_slug: str
    code: str
    message: str


@dataclass(frozen=True)
class PortalImportResult:
    imported: int
    skipped: int
    conflicts: tuple[PortalImportConflict, ...]


class PortalUserImporter:
    """Import push-style de usuários do Portal → Pessoa + CargoLoja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory
        self._people = PeopleDirectory(session_factory)
        self._roles = StoreRoles(session_factory)

    def import_rows(
        self,
        actor: Actor,
        rows: Sequence[PortalUserImportRow] | Iterable[PortalUserImportRow],
    ) -> PortalImportResult:
        if not actor.is_admin:
            raise AccessDenied(
                "somente Admin Revy pode importar usuários do Portal"
            )

        imported = 0
        skipped = 0
        conflicts: list[PortalImportConflict] = []

        for row in rows:
            outcome = self._import_one(actor, row)
            if outcome == "imported":
                imported += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                conflicts.append(outcome)

        return PortalImportResult(
            imported=imported,
            skipped=skipped,
            conflicts=tuple(conflicts),
        )

    def _import_one(
        self,
        actor: Actor,
        row: PortalUserImportRow,
    ) -> str | PortalImportConflict:
        if not row.active:
            return "skipped"

        store_slug = (row.store_slug or "").strip().lower()
        email_raw = row.email or ""
        origem_id = (row.origem_id or "").strip()
        if not origem_id:
            return PortalImportConflict(
                email=email_raw,
                store_slug=store_slug,
                code="invalid_origem_id",
                message="origem_id do usuário do Portal é obrigatório",
            )

        try:
            person = self._people.find_by_email(actor, email_raw)
        except InvalidPersonEmail:
            return PortalImportConflict(
                email=email_raw,
                store_slug=store_slug,
                code="invalid_person_email",
                message="e-mail da Pessoa Revy inválido",
            )

        role_key = (row.role or "").strip().lower()
        store_role = _ROLE_BY_VALUE.get(role_key)
        if store_role is None:
            return PortalImportConflict(
                email=email_raw.strip().lower(),
                store_slug=store_slug,
                code="invalid_role",
                message="cargo deve ser dono, gerente ou vendedor",
            )

        store_id = self._resolve_store_id(store_slug)
        if store_id is None:
            return PortalImportConflict(
                email=email_raw.strip().lower(),
                store_slug=store_slug,
                code="store_not_found",
                message="Loja não encontrada",
            )

        if self._active_portal_cargo(origem_id) is not None:
            return "skipped"

        if person is None:
            name = (row.name or "").strip()
            if not name:
                local = email_raw.strip().split("@", 1)[0].strip()
                name = local or email_raw.strip().lower()
            try:
                person = self._people.register(
                    actor,
                    RegisterPerson(name=name, email=email_raw),
                )
            except PersonEmailConflict:
                person = self._people.find_by_email(actor, email_raw)
                if person is None:
                    return PortalImportConflict(
                        email=email_raw.strip().lower(),
                        store_slug=store_slug,
                        code="person_email_conflict",
                        message="já existe Pessoa Revy com este e-mail",
                    )

        if self._person_has_role(store_id, person.id, store_role):
            return "skipped"

        try:
            self._roles.assign(
                actor,
                AssignStoreRole(
                    store=StoreRef(id=store_id),
                    person=PersonRef(id=person.id),
                    role=store_role,
                    origem=_PORTAL_ORIGEM,
                    origem_id=origem_id,
                ),
            )
        except StoreRoleConflict:
            return "skipped"

        return "imported"

    def _resolve_store_id(self, store_slug: str) -> str | None:
        if not store_slug:
            return None
        with self._session_factory() as db:
            store = (
                db.query(Loja)
                .filter(Loja.slug == store_slug)
                .first()
            )
            return store.id if store is not None else None

    def _active_portal_cargo(self, origem_id: str) -> CargoLoja | None:
        with self._session_factory() as db:
            return (
                db.query(CargoLoja)
                .filter(
                    CargoLoja.origem == _PORTAL_ORIGEM,
                    CargoLoja.origem_id == origem_id,
                    CargoLoja.encerrado_em.is_(None),
                )
                .first()
            )

    def _person_has_role(
        self,
        store_id: str,
        person_id: str,
        role: StoreRole,
    ) -> bool:
        with self._session_factory() as db:
            return (
                db.query(CargoLoja.id)
                .filter(
                    CargoLoja.loja_id == store_id,
                    CargoLoja.pessoa_id == person_id,
                    CargoLoja.cargo == role.value,
                    CargoLoja.encerrado_em.is_(None),
                )
                .first()
                is not None
            )
