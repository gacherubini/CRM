from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.control.audit import _append_event
from app.control.provisioning_hooks import safe_enqueue_store_snapshot
from app.control.stores import _find_store
from app.control.types import (
    AccessDenied,
    Actor,
    ControlError,
    StoreNotFound,
    StoreRef,
)
from app.models import LojaModulo, ModuloRevy, VinculoTrafego, agora


class ModuleCode(str, Enum):
    INVENTORY = "estoque"
    SALES = "vendas"
    COPILOTO = "copiloto"


class ModuleStatus(str, Enum):
    ACTIVE = "ativo"
    SUSPENDED = "suspenso"


class InvalidModuleSelection(ControlError):
    pass


class PortfolioConflict(ControlError):
    pass


@dataclass(frozen=True)
class ModuleView:
    code: ModuleCode
    name: str
    status: ModuleStatus
    version: int


_CATALOG = frozenset(ModuleCode)


class PortfolioControl:
    """Configuração dos módulos contratados por Loja."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def list_modules(
        self,
        actor: Actor,
        store_ref: StoreRef,
    ) -> tuple[ModuleView, ...]:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            return _list_views(db, store.id)

    def configure(
        self,
        actor: Actor,
        store_ref: StoreRef,
        module_codes: set[str] | tuple[str, ...],
    ) -> tuple[ModuleView, ...]:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode configurar módulos")
        selected = _normalize_selection(module_codes)

        with self._session_factory() as db:
            store = _find_store(db, store_ref, for_update=True)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            modules = {
                ModuleCode(row.codigo): row
                for row in db.query(ModuloRevy)
                .filter(ModuloRevy.codigo.in_(code.value for code in _CATALOG))
                .all()
            }
            if set(modules) != _CATALOG:
                raise PortfolioConflict("catálogo de módulos Revy incompleto")

            assignments = {
                row.modulo_id: row
                for row in db.query(LojaModulo)
                .filter(LojaModulo.loja_id == store.id)
                .with_for_update()
                .all()
            }
            now = agora()
            for code in sorted(_CATALOG, key=lambda item: item.value):
                module = modules[code]
                assignment = assignments.get(module.id)
                if code in selected and assignment is None:
                    assignment = LojaModulo(
                        loja_id=store.id,
                        modulo_id=module.id,
                        estado=ModuleStatus.ACTIVE.value,
                        versao=1,
                        contratado_em=now,
                        atualizado_em=now,
                    )
                    db.add(assignment)
                    db.flush()
                    assignments[module.id] = assignment
                    _append_event(
                        db,
                        actor=actor,
                        store_id=store.id,
                        action="store_module.contracted",
                        resource_type="loja_modulo",
                        resource_id=assignment.id,
                        after={
                            "code": code.value,
                            "status": assignment.estado,
                            "version": assignment.versao,
                        },
                    )
                elif (
                    code in selected
                    and assignment is not None
                    and assignment.estado == ModuleStatus.SUSPENDED.value
                ):
                    before = {
                        "code": code.value,
                        "status": assignment.estado,
                        "version": assignment.versao,
                    }
                    assignment.estado = ModuleStatus.ACTIVE.value
                    assignment.versao += 1
                    assignment.suspenso_em = None
                    assignment.atualizado_em = now
                    _append_event(
                        db,
                        actor=actor,
                        store_id=store.id,
                        action="store_module.activated",
                        resource_type="loja_modulo",
                        resource_id=assignment.id,
                        before=before,
                        after={
                            "code": code.value,
                            "status": assignment.estado,
                            "version": assignment.versao,
                        },
                    )
                elif (
                    code not in selected
                    and assignment is not None
                    and assignment.estado == ModuleStatus.ACTIVE.value
                ):
                    before = {
                        "code": code.value,
                        "status": assignment.estado,
                        "version": assignment.versao,
                    }
                    assignment.estado = ModuleStatus.SUSPENDED.value
                    assignment.versao += 1
                    assignment.suspenso_em = now
                    assignment.atualizado_em = now
                    _append_event(
                        db,
                        actor=actor,
                        store_id=store.id,
                        action="store_module.suspended",
                        resource_type="loja_modulo",
                        resource_id=assignment.id,
                        before=before,
                        after={
                            "code": code.value,
                            "status": assignment.estado,
                            "version": assignment.versao,
                        },
                    )

            db.commit()
            views = _list_views(db, store.id)
            safe_enqueue_store_snapshot(
                self._session_factory, StoreRef(id=store.id)
            )
            return views

    def suspend(
        self,
        actor: Actor,
        store_ref: StoreRef,
        module_code: str,
        reason: str | None = None,
    ) -> ModuleView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode suspender módulos")
        return self._transition(
            actor,
            store_ref,
            module_code,
            current=ModuleStatus.ACTIVE,
            target=ModuleStatus.SUSPENDED,
            action="store_module.suspended",
            reason=reason,
        )

    def activate(
        self,
        actor: Actor,
        store_ref: StoreRef,
        module_code: str,
        reason: str | None = None,
    ) -> ModuleView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode reativar módulos")
        return self._transition(
            actor,
            store_ref,
            module_code,
            current=ModuleStatus.SUSPENDED,
            target=ModuleStatus.ACTIVE,
            action="store_module.activated",
            reason=reason,
        )

    def _transition(
        self,
        actor: Actor,
        store_ref: StoreRef,
        module_code: str,
        *,
        current: ModuleStatus,
        target: ModuleStatus,
        action: str,
        reason: str | None,
    ) -> ModuleView:
        code = _normalize_code(module_code)
        with self._session_factory() as db:
            store = _find_store(db, store_ref, for_update=True)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            module = (
                db.query(ModuloRevy)
                .filter(ModuloRevy.codigo == code.value)
                .first()
            )
            if module is None:
                raise PortfolioConflict("módulo ausente do catálogo Revy")
            assignment = (
                db.query(LojaModulo)
                .filter(
                    LojaModulo.loja_id == store.id,
                    LojaModulo.modulo_id == module.id,
                )
                .with_for_update()
                .first()
            )
            if assignment is None:
                raise PortfolioConflict("módulo não contratado pela Loja")
            if assignment.estado != current.value:
                raise PortfolioConflict(
                    f"módulo precisa estar {current.value} para esta transição"
                )

            before = {
                "code": code.value,
                "status": assignment.estado,
                "version": assignment.versao,
            }
            now = agora()
            assignment.estado = target.value
            assignment.versao += 1
            assignment.suspenso_em = (
                now if target is ModuleStatus.SUSPENDED else None
            )
            assignment.atualizado_em = now
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action=action,
                resource_type="loja_modulo",
                resource_id=assignment.id,
                before=before,
                after={
                    "code": code.value,
                    "status": assignment.estado,
                    "version": assignment.versao,
                },
                reason=reason,
            )
            db.commit()
            db.refresh(assignment)
            safe_enqueue_store_snapshot(
                self._session_factory, StoreRef(id=store.id)
            )
            return ModuleView(
                code=code,
                name=module.nome,
                status=ModuleStatus(assignment.estado),
                version=assignment.versao,
            )


def _authorized_store(db: Any, actor: Actor, store_ref: StoreRef) -> Any:
    store = _find_store(db, store_ref)
    if store is None:
        raise StoreNotFound("Loja não encontrada")
    if actor.is_admin:
        return store
    link = (
        db.query(VinculoTrafego.id)
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


def _normalize_selection(
    module_codes: set[str] | tuple[str, ...],
) -> frozenset[ModuleCode]:
    normalized: set[ModuleCode] = set()
    for raw_code in module_codes:
        normalized.add(_normalize_code(raw_code))
    if not normalized:
        raise InvalidModuleSelection("selecione ao menos um módulo Revy")
    return frozenset(normalized)


def _normalize_code(module_code: str) -> ModuleCode:
    try:
        return ModuleCode(module_code.strip().lower())
    except (AttributeError, ValueError) as exc:
        raise InvalidModuleSelection("módulo Revy inválido") from exc


def _list_views(db: Any, store_id: str) -> tuple[ModuleView, ...]:
    rows = (
        db.query(LojaModulo, ModuloRevy)
        .join(ModuloRevy, ModuloRevy.id == LojaModulo.modulo_id)
        .filter(LojaModulo.loja_id == store_id)
        .order_by(ModuloRevy.codigo)
        .all()
    )
    return tuple(
        ModuleView(
            code=ModuleCode(module.codigo),
            name=module.nome,
            status=ModuleStatus(assignment.estado),
            version=assignment.versao,
        )
        for assignment, module in rows
    )
