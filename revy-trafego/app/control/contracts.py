from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.control.audit import _append_event
from app.control.stores import _find_store
from app.control.types import AccessDenied, Actor, ControlError, StoreNotFound, StoreRef
from app.models import ContratoLoja, VinculoTrafego, agora


class ContractBillingStatus(str, Enum):
    CURRENT = "em_dia"
    OVERDUE = "atrasada"
    EXEMPT = "isenta"


class ContractNotFound(ControlError):
    pass


@dataclass(frozen=True)
class UpsertContract:
    store: StoreRef
    monthly_amount: Decimal
    starts_on: date
    ends_on: date | None
    due_day: int
    billing_status: ContractBillingStatus


@dataclass(frozen=True)
class ContractView:
    id: str
    store_id: str
    monthly_amount: Decimal
    currency: str
    starts_on: date
    ends_on: date | None
    due_day: int
    billing_status: ContractBillingStatus
    created_at: datetime
    updated_at: datetime


class ContractControl:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def upsert(self, actor: Actor, command: UpsertContract) -> ContractView:
        if not actor.is_admin:
            raise AccessDenied("somente Admin Revy pode administrar contrato da Loja")
        _validate_contract(command)
        with self._session_factory() as db:
            store = _find_store(db, command.store, for_update=True)
            if store is None:
                raise StoreNotFound("Loja não encontrada")
            contract = (
                db.query(ContratoLoja)
                .filter(
                    ContratoLoja.loja_id == store.id,
                    ContratoLoja.estado == "ativo",
                )
                .first()
            )
            before = _audit_values(contract) if contract is not None else None
            if contract is None:
                contract = ContratoLoja(
                    loja_id=store.id,
                    valor_mensal=command.monthly_amount,
                    moeda="BRL",
                    vigencia_inicio=command.starts_on,
                    vigencia_fim=command.ends_on,
                    vencimento_dia=command.due_day,
                    situacao_cobranca=command.billing_status.value,
                    estado="ativo",
                )
                db.add(contract)
                db.flush()
            else:
                contract.valor_mensal = command.monthly_amount
                contract.vigencia_inicio = command.starts_on
                contract.vigencia_fim = command.ends_on
                contract.vencimento_dia = command.due_day
                contract.situacao_cobranca = command.billing_status.value
                contract.atualizado_em = agora()
            _append_event(
                db,
                actor=actor,
                store_id=store.id,
                action="store_contract.upserted",
                resource_type="contrato_loja",
                resource_id=contract.id,
                before=before,
                after=_audit_values(contract),
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(contract)
            return _contract_view(contract)

    def get(self, actor: Actor, store: StoreRef) -> ContractView:
        with self._session_factory() as db:
            store_row = _find_store(db, store)
            if store_row is None:
                raise StoreNotFound("Loja não encontrada")
            if (
                not actor.is_admin
                and db.query(VinculoTrafego.id)
                .filter(
                    VinculoTrafego.loja_id == store_row.id,
                    VinculoTrafego.gestor_id == actor.id,
                    VinculoTrafego.encerrado_em.is_(None),
                )
                .first()
                is None
            ):
                raise StoreNotFound("Loja não encontrada")
            contract = (
                db.query(ContratoLoja)
                .filter(
                    ContratoLoja.loja_id == store_row.id,
                    ContratoLoja.estado == "ativo",
                )
                .first()
            )
            if contract is None:
                raise ContractNotFound("contrato ativo não encontrado para a Loja")
            return _contract_view(contract)


def _audit_values(contract: ContratoLoja) -> dict[str, object]:
    return {
        "billing_status": contract.situacao_cobranca,
        "currency": contract.moeda,
        "due_day": contract.vencimento_dia,
        "ends_on": (
            contract.vigencia_fim.isoformat()
            if contract.vigencia_fim is not None
            else None
        ),
        "monthly_amount": f"{contract.valor_mensal:.2f}",
        "starts_on": contract.vigencia_inicio.isoformat(),
    }


def _validate_contract(command: UpsertContract) -> None:
    if (
        not isinstance(command.monthly_amount, Decimal)
        or not command.monthly_amount.is_finite()
        or command.monthly_amount < 0
    ):
        raise ValueError("valor mensal deve ser maior ou igual a zero")
    if (
        not isinstance(command.starts_on, date)
        or (
            command.ends_on is not None
            and (
                not isinstance(command.ends_on, date)
                or command.ends_on < command.starts_on
            )
        )
    ):
        raise ValueError("vigência do contrato inválida")
    if (
        isinstance(command.due_day, bool)
        or not isinstance(command.due_day, int)
        or not 1 <= command.due_day <= 31
    ):
        raise ValueError("dia de vencimento deve estar entre 1 e 31")


def _contract_view(contract: ContratoLoja) -> ContractView:
    return ContractView(
        id=contract.id,
        store_id=contract.loja_id,
        monthly_amount=contract.valor_mensal,
        currency=contract.moeda,
        starts_on=contract.vigencia_inicio,
        ends_on=contract.vigencia_fim,
        due_day=contract.vencimento_dia,
        billing_status=ContractBillingStatus(contract.situacao_cobranca),
        created_at=contract.criado_em,
        updated_at=contract.atualizado_em,
    )
