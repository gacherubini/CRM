from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.control.readiness import StoreReadiness
from app.control.stores import StoreControl
from app.control.types import Actor, StoreRef, StoreStatus


@dataclass(frozen=True)
class StoreReadinessSummary:
    store_id: str
    slug: str
    name: str
    status: StoreStatus
    ready: bool


class DashboardControl:
    """Resumo lean de prontidão por loja no escopo do ator."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory
        self._stores = StoreControl(session_factory)
        self._readiness = StoreReadiness(session_factory)

    def summary(self, actor: Actor) -> tuple[StoreReadinessSummary, ...]:
        stores = self._stores.list(actor)
        items: list[StoreReadinessSummary] = []
        for store in stores:
            report = self._readiness.evaluate(actor, StoreRef(id=store.id))
            items.append(
                StoreReadinessSummary(
                    store_id=store.id,
                    slug=store.slug,
                    name=store.name,
                    status=store.status,
                    ready=report.ready,
                )
            )
        return tuple(items)
