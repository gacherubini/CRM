from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.control.audit import _append_event
from app.control.integrations import pixel_configured, vendas_module_active
from app.control.types import (
    AccessDenied,
    Actor,
    InvalidAlertAcceptance,
    StoreNotFound,
    StoreRef,
    StoreRole,
    StoreStatus,
    TrafficRole,
)
from app.models import (
    AcessoControl,
    CargoLoja,
    ContratoLoja,
    Loja,
    LojaModulo,
    ModuloRevy,
    ReadinessAlertAcceptance,
    VinculoTrafego,
    agora,
)

# Ordem determinística estável (não alfabética pura: active_owner precede
# activatable_owner por dependência lógica). meta_pixel só entra quando o
# módulo vendas está ativo (alerta, não bloqueia prontidão).
# whatsapp_channel: alerta opcional multi-WA (contagem injetada).
_CHECK_ORDER = (
    "active_owner",
    "activatable_owner",
    "module_selected",
    "contract_present",
    "meta_pixel",
    "whatsapp_channel",
)

_REQUIRED_CODES = frozenset(
    {
        "active_owner",
        "module_selected",
    }
)

# Alias público: a UI precisa distinguir bloqueio de alerta nos chips de
# prontidão — antes tudo saía com o mesmo "status warn".
REQUIRED_CODES = _REQUIRED_CODES


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    ok: bool
    severity: str
    message: str
    accepted: bool = False

    def __post_init__(self) -> None:
        if self.severity not in {"required", "alert"}:
            raise ValueError(f"severity inválida: {self.severity}")


@dataclass(frozen=True)
class ReadinessReport:
    store_id: str
    status: StoreStatus
    ready: bool
    checks: tuple[ReadinessCheck, ...]


@dataclass(frozen=True)
class AlertAcceptanceView:
    store_id: str
    check_code: str
    accepted_by: str
    reason: str
    accepted_at: object


class StoreReadiness:
    """Calcula por que a Loja está ou não pronta (interface determinística)."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def evaluate(self, actor: Actor, store_ref: StoreRef) -> ReadinessReport:
        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            return build_readiness_report(db, store)

    def accept_alert(
        self,
        actor: Actor,
        store_ref: StoreRef,
        check_code: str,
        reason: str,
    ) -> AlertAcceptanceView:
        """Aceita alerta não bloqueante com motivo obrigatório (auditado).

        Não contorna checks ``required`` nem marca a loja como pronta.
        """
        code = (check_code or "").strip()
        motivo = (reason or "").strip()
        if not code:
            raise InvalidAlertAcceptance("informe o código do alerta")
        if not motivo:
            raise InvalidAlertAcceptance(
                "informe o motivo do aceite do alerta"
            )

        with self._session_factory() as db:
            store = _authorized_store(db, actor, store_ref)
            _require_can_manage_readiness(db, actor, store)
            report = build_readiness_report(db, store)
            target = next(
                (check for check in report.checks if check.code == code),
                None,
            )
            if target is None:
                raise InvalidAlertAcceptance(
                    f"check de prontidão desconhecido: {code}"
                )
            if target.severity != "alert":
                raise InvalidAlertAcceptance(
                    "somente alertas não bloqueantes podem ser aceitos; "
                    "requisitos obrigatórios não são contornáveis"
                )
            if target.ok:
                raise InvalidAlertAcceptance(
                    "check já está ok; não há alerta para aceitar"
                )

            row = (
                db.query(ReadinessAlertAcceptance)
                .filter(
                    ReadinessAlertAcceptance.loja_id == store.id,
                    ReadinessAlertAcceptance.check_code == code,
                )
                .first()
            )
            before = (
                {
                    "check_code": row.check_code,
                    "reason": row.reason,
                    "accepted_by": row.accepted_by,
                }
                if row is not None
                else None
            )
            now = agora()
            if row is None:
                row = ReadinessAlertAcceptance(
                    loja_id=store.id,
                    check_code=code,
                    accepted_by=actor.id,
                    reason=motivo,
                    accepted_at=now,
                )
                db.add(row)
            else:
                row.accepted_by = actor.id
                row.reason = motivo
                row.accepted_at = now
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="readiness.alert.accepted",
                resource_type="readiness_alert",
                resource_id=code,
                before=before,
                after={
                    "check_code": code,
                    "reason": motivo,
                    "accepted_by": actor.id,
                },
                reason=motivo,
            )
            db.commit()
            db.refresh(row)
            return AlertAcceptanceView(
                store_id=store.id,
                check_code=row.check_code,
                accepted_by=row.accepted_by,
                reason=row.reason,
                accepted_at=row.accepted_at,
            )


def build_readiness_report(
    db: Any,
    store: Any,
    *,
    multi_whatsapp_enabled: bool = False,
    active_whatsapp_channels: int | None = None,
) -> ReadinessReport:
    """Monta o relatório de prontidão a partir de uma sessão/loja já carregadas.

    ``active_whatsapp_channels``: quando multi-WA está ligado e o valor é
    conhecido, inclui alerta whatsapp_channel. Se None, o check é omitido.
    """
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
    has_vendas = vendas_module_active(db, store.id)
    has_pixel = pixel_configured(db, store) if has_vendas else True
    has_whatsapp = (
        (active_whatsapp_channels or 0) > 0
        if multi_whatsapp_enabled and active_whatsapp_channels is not None
        else True
    )

    facts = {
        "active_owner": has_active_owner,
        "activatable_owner": has_activatable_owner,
        "module_selected": has_module,
        "contract_present": has_contract,
        "meta_pixel": has_pixel,
        "whatsapp_channel": has_whatsapp,
    }
    # meta_pixel só com módulo vendas; whatsapp_channel só com multi-WA + contagem.
    skip: set[str] = set()
    if not has_vendas:
        skip.add("meta_pixel")
    if not multi_whatsapp_enabled or active_whatsapp_channels is None:
        skip.add("whatsapp_channel")
    order = tuple(code for code in _CHECK_ORDER if code not in skip)
    accepted_codes = {
        row[0]
        for row in db.query(ReadinessAlertAcceptance.check_code)
        .filter(ReadinessAlertAcceptance.loja_id == store.id)
        .all()
    }
    checks = tuple(
        _check_for(code, facts[code], accepted=code in accepted_codes)
        for code in order
    )
    # Aceite de alerta NUNCA inventa ready=True se required falhar.
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


def _check_for(code: str, ok: bool, *, accepted: bool = False) -> ReadinessCheck:
    severity = "required" if code in _REQUIRED_CODES else "alert"
    return ReadinessCheck(
        code=code,
        ok=ok,
        severity=severity,
        message=_message_for(code, ok),
        accepted=bool(accepted) if severity == "alert" and not ok else False,
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
        "meta_pixel": (
            "Pixel Meta e CAPI configurados"
            if ok
            else "Módulo vendas ativo sem Pixel/CAPI (alerta de medição)"
        ),
        "whatsapp_channel": (
            "Loja possui canal WhatsApp ativo"
            if ok
            else "Multi-WhatsApp ativo sem canal configurado (alerta)"
        ),
    }
    return messages[code]


def _require_can_manage_readiness(db: Any, actor: Actor, store: Loja) -> None:
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
            "somente Admin Revy ou Gestor Responsável pode aceitar alertas"
        )


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
