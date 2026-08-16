"""Resolve módulos Vendas/Estoque habilitados para a loja selecionada."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from app.loja.types import (
    ROLES_OPERACIONAIS,
    EntitlementState,
    Module,
)


class _AllowsProcessing(Protocol):
    def __call__(self, loja_slug: str, module: str | None = None) -> bool: ...


def fail_open(loja_slug: str, roles: frozenset[str] | set[str]) -> EntitlementState:
    """Com flag de entitlements desligada: comportamento atual do portal.

    Todos os módulos operacionais ficam permitidos se a pessoa tiver cargo na loja.
    """
    has_role = bool(set(roles) & ROLES_OPERACIONAIS)
    return EntitlementState(
        loja_slug=loja_slug,
        loja_ativa=True,
        vendas_enabled=has_role,
        estoque_enabled=has_role,
        source="fail_open",
        copiloto_enabled=has_role,
        financeiro_enabled=has_role,
    )


def from_allows_processing(
    loja_slug: str,
    allows: Callable[..., bool],
    *,
    source: str = "projecao",
) -> EntitlementState:
    """Usa o gate ``allows_processing`` (LojaOperacionalProjecao).

    ``allows(slug)`` → loja ativa; ``allows(slug, module=...)`` → módulo ativo.
    """
    loja_ativa = bool(allows(loja_slug))
    if not loja_ativa:
        return EntitlementState(
            loja_slug=loja_slug,
            loja_ativa=False,
            vendas_enabled=False,
            estoque_enabled=False,
            source=source,
        )
    return EntitlementState(
        loja_slug=loja_slug,
        loja_ativa=True,
        vendas_enabled=bool(allows(loja_slug, Module.VENDAS.value)),
        estoque_enabled=bool(allows(loja_slug, Module.ESTOQUE.value)),
        source=source,
        copiloto_enabled=bool(allows(loja_slug, Module.COPILOTO.value)),
        financeiro_enabled=bool(allows(loja_slug, Module.FINANCEIRO.value)),
    )


def from_db_projection(db: Any, loja_slug: str) -> EntitlementState:
    """Lê LojaOperacionalProjecao via ``app.provisioning.allows_processing``."""
    from app import provisioning

    def _allows(slug: str, module: str | None = None) -> bool:
        return provisioning.allows_processing(db, slug, module)

    return from_allows_processing(loja_slug, _allows, source="projecao")


def resolve_entitlements(
    loja_slug: str,
    roles: frozenset[str] | set[str],
    *,
    entitlements_enabled: bool,
    db: Any | None = None,
    control_entitlements: EntitlementState | None = None,
    allows: Callable[..., bool] | None = None,
) -> EntitlementState:
    """Resolve entitlements com degradação segura.

    Ordem quando ``entitlements_enabled``:
    1. Projeção local (db / allows) se disponível
    2. Entitlement do Control port (se passado)
    3. Fail-closed se nada conhecido (loja sem projeção)

    Quando flag off → ``fail_open`` (portal legado).
    """
    if not entitlements_enabled:
        return fail_open(loja_slug, roles)

    if allows is not None:
        return from_allows_processing(loja_slug, allows, source="projecao")

    if db is not None:
        return from_db_projection(db, loja_slug)

    if control_entitlements is not None:
        return control_entitlements

    # Sem projeção e flag on: fail-closed (não inventar contrato).
    return EntitlementState(
        loja_slug=loja_slug,
        loja_ativa=False,
        vendas_enabled=False,
        estoque_enabled=False,
        source="projecao",
    )


def blocks_new_processing(
    entitlements: EntitlementState,
    module: Module | str,
) -> bool:
    """True se novo atendimento/simulação/venda/alteração de estoque deve ser bloqueado."""
    from app.loja.permissions import module_enabled

    return not module_enabled(entitlements, module)
