from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.control.provisioning import (
    OperationalStateEnvelope,
    ProvisionedPerson,
    ProvisionedRole,
    ProvisioningControl,
    StoreProvisioningSnapshot,
)
from app.control.types import StoreRef


class ProvisioningDeliveryPort(Protocol):
    """Porta de transporte do snapshot operacional para serviços de destino."""

    def deliver(self, target: str, snapshot: StoreProvisioningSnapshot) -> None:
        """Entrega o snapshot ao destino identificado (chatbot, estoque, ...)."""


@dataclass
class InMemoryProvisioningDelivery:
    """Adapter de teste: registra entregas sem HTTP."""

    deliveries: list[tuple[str, StoreProvisioningSnapshot]] = field(
        default_factory=list
    )

    def deliver(self, target: str, snapshot: StoreProvisioningSnapshot) -> None:
        self.deliveries.append((target, snapshot))


class ProvisioningPublisher:
    """Monta o snapshot e publica para todos os destinos configurados."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        delivery: ProvisioningDeliveryPort,
        targets: Sequence[str] = (),
    ) -> None:
        self._provisioning = ProvisioningControl(session_factory)
        self._delivery = delivery
        self._targets = tuple(targets)

    def publish(self, store_ref: StoreRef) -> StoreProvisioningSnapshot:
        snapshot = self._provisioning.snapshot(store_ref)
        for target in self._targets:
            self._delivery.deliver(target, snapshot)
        return snapshot


@dataclass(frozen=True)
class AggregateProjection:
    version: int
    state: str
    event_id: str


@dataclass(frozen=True)
class DestinationProjection:
    """Projeção local de um destino (simulador de consumo monotônico)."""

    loja_id: str
    aggregates: dict[str, AggregateProjection]
    people: tuple[ProvisionedPerson, ...]
    roles: tuple[ProvisionedRole, ...]


def apply_snapshot(
    current: DestinationProjection | None,
    snapshot: StoreProvisioningSnapshot,
) -> tuple[DestinationProjection, list[str]]:
    """Aplica envelopes operacionais de forma monotônica e idempotente.

    Regras por aggregate:
    - versão menor que a local → ``stale`` (não reativa)
    - mesma versão e mesmo estado → ``idempotent``
    - demais casos → ``applied``
    """
    loja_id = _snapshot_loja_id(snapshot)
    aggregates: dict[str, AggregateProjection] = dict(
        current.aggregates if current is not None else {}
    )
    reasons: list[str] = []
    for envelope in snapshot.operational:
        reasons.append(_apply_envelope(aggregates, envelope))
    return (
        DestinationProjection(
            loja_id=loja_id,
            aggregates=aggregates,
            people=snapshot.people,
            roles=snapshot.roles,
        ),
        reasons,
    )


def allows_processing(
    projection: DestinationProjection | None,
    *,
    module: str | None = None,
) -> bool:
    """Gate mínimo: Loja ativa e, se pedido, módulo contratado e ativo."""
    if projection is None:
        return False
    loja = projection.aggregates.get("loja")
    if loja is None or loja.state != "ativa":
        return False
    if module is None:
        return True
    assigned = projection.aggregates.get(module)
    return assigned is not None and assigned.state == "ativo"


def _snapshot_loja_id(snapshot: StoreProvisioningSnapshot) -> str:
    if snapshot.operational:
        return snapshot.operational[0].loja_id
    if snapshot.roles:
        # fallback defensivo; snapshot real sempre traz loja
        return ""
    return ""


def _apply_envelope(
    aggregates: dict[str, AggregateProjection],
    envelope: OperationalStateEnvelope,
) -> str:
    existing = aggregates.get(envelope.aggregate)
    if existing is not None:
        if existing.version > envelope.version:
            return "stale"
        if (
            existing.version == envelope.version
            and existing.state == envelope.state
        ):
            return "idempotent"
    aggregates[envelope.aggregate] = AggregateProjection(
        version=envelope.version,
        state=envelope.state,
        event_id=envelope.event_id,
    )
    return "applied"
