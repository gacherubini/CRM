"""Revy Loja — shell, identidade, entitlements e read models operacionais."""

from app.loja.estoque_overview import EstoqueOverview, montar_estoque_overview
from app.loja.types import (
    ActorLoja,
    EntitlementState,
    Module,
    NavItem,
    NavSection,
    Role,
    StatusReadModel,
    StoreContext,
    StoreMembership,
)

__all__ = [
    "ActorLoja",
    "EntitlementState",
    "EstoqueOverview",
    "Module",
    "NavItem",
    "NavSection",
    "Role",
    "StatusReadModel",
    "StoreContext",
    "StoreMembership",
    "montar_estoque_overview",
]
