from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.control.types import Actor, StoreNotFound, StoreRef, StoreRole, StoreStatus
from app.models import (
    AcessoControl,
    CargoLoja,
    ContratoLoja,
    Loja,
    LojaModulo,
    ModuloRevy,
    VinculoTrafego,
)

# Ordem determinística estável (não alfabética pura: active_owner precede
# activatable_owner por dependência lógica).
_CHECK_ORDER = (
    "active_owner",
    "activatable_owner",
    "module_selected",
    "contract_present",
)

_REQUIRED_CODES = frozenset(
    {
        "active_owner",
        "activatable_owner",
        "module_selected",
    }
)


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    ok: bool
    severity: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in {"required", "alert"}:
            raise ValueError(f"severity inválida: {self.severity}")


@dataclass(frozen=True)
class ReadinessReport:
    store_id: str
    status: StoreStatus
    ready: bool
    checks: tuple[ReadinessCheck, ...]


class StoreReadiness:
    """Calcula por que a Loja está ou não pronta (interface determinística)."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def evaluate(self, actor: Actor, store_ref: StoreRef) -> ReadinessReport:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            return build_readiness_report(db, store)


def build_readiness_report(db: Any, store: Any) -> ReadinessReport:
    """Monta o relatório de prontidão a partir de uma sessão/loja já carregadas."""
    owner_person_ids = [
        row[0]
        for row in db.query(CargoLoja.pessoa_id)
        .filter(
            CargoLoja.loja_id == store.id,
            CargoLoja.cargo == StoreRole.OWNER.value,
            CargoLoja.encerrado_em.is_(None),
        )
        .all()
    ]
    has_active_owner = bool(owner_person_ids)
    has_activatable_owner = False
    if owner_person_ids:
        has_activatable_owner = (
            db.query(AcessoControl.id)
            .filter(
                AcessoControl.pessoa_id.in_(owner_person_ids),
                AcessoControl.estado.in_(("pendente", "ativo")),
            )
            .first()
            is not None
        )
    has_module = (
        db.query(LojaModulo.id)
        .join(ModuloRevy, ModuloRevy.id == LojaModulo.modulo_id)
        .filter(
            LojaModulo.loja_id == store.id,
            LojaModulo.estado == "ativo",
            ModuloRevy.codigo.in_(("vendas", "estoque")),
        )
        .first()
        is not None
    )
    has_contract = (
        db.query(ContratoLoja.id)
        .filter(
            ContratoLoja.loja_id == store.id,
            ContratoLoja.estado == "ativo",
        )
        .first()
        is not None
    )

    facts = {
        "active_owner": has_active_owner,
        "activatable_owner": has_activatable_owner,
        "module_selected": has_module,
        "contract_present": has_contract,
    }
    checks = tuple(_check_for(code, facts[code]) for code in _CHECK_ORDER)
    ready = all(check.ok for check in checks if check.severity == "required")
    return ReadinessReport(
        store_id=store.id,
        status=StoreStatus(store.status),
        ready=ready,
        checks=checks,
    )


def first_failed_required(report: ReadinessReport) -> ReadinessCheck | None:
    for check in report.checks:
        if check.severity == "required" and not check.ok:
            return check
    return None


def _check_for(code: str, ok: bool) -> ReadinessCheck:
    severity = "required" if code in _REQUIRED_CODES else "alert"
    return ReadinessCheck(
        code=code,
        ok=ok,
        severity=severity,
        message=_message_for(code, ok),
    )


def _message_for(code: str, ok: bool) -> str:
    messages = {
        "active_owner": (
            "Loja possui ao menos um Dono ativo"
            if ok
            else "Loja precisa de ao menos um Dono ativo"
        ),
        "activatable_owner": (
            "Dono possui acesso Control ativável (pendente ou ativo)"
            if ok
            else "Dono precisa de acesso Control pendente ou ativo"
        ),
        "module_selected": (
            "Loja possui módulo vendas ou estoque ativo"
            if ok
            else "Loja precisa de ao menos um módulo vendas ou estoque ativo"
        ),
        "contract_present": (
            "Loja possui contrato ativo"
            if ok
            else "Loja sem contrato ativo (alerta)"
        ),
    }
    return messages[code]


def _authorized_store(db: Any, actor: Actor, store_ref: StoreRef) -> Any:
    store = _lookup_store(db, store_ref)
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


def _lookup_store(db: Any, store_ref: StoreRef) -> Loja | None:
    query = db.query(Loja)
    if store_ref.id:
        return query.filter(Loja.id == store_ref.id).first()
    return query.filter(Loja.slug == store_ref.slug.strip().lower()).first()
