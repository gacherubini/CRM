"""Navegação permitida do shell Revy Loja (somente Vendas e Estoque)."""
from __future__ import annotations

from app.loja.types import (
    ROLES_GESTAO,
    ROLES_OPERACIONAIS,
    EntitlementState,
    Module,
    NavItem,
    NavSection,
    StoreContext,
)


def build_nav(
    store: StoreContext,
    entitlements: EntitlementState,
    *,
    shell_enabled: bool = True,
) -> tuple[NavSection, ...]:
    """Produz seções de navegação conforme contrato e cargos.

    Com shell desligado o chamador não deve usar este resultado (UI legada).
    Não inclui Meta/Google/WhatsApp nem configurações técnicas.
    """
    if not shell_enabled:
        return ()

    roles = store.roles & ROLES_OPERACIONAIS
    if not roles:
        return ()

    sections: list[NavSection] = []

    if entitlements.vendas_enabled and entitlements.loja_ativa:
        sections.append(
            NavSection(
                title="Vendas",
                items=(
                    NavItem(
                        label="Visão geral",
                        href="/app/loja/vendas",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/loja/vendas",
                    ),
                    NavItem(
                        label="Atendimento",
                        href="/app/loja/atendimento",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/loja/atendimento",
                    ),
                ),
            )
        )

    if entitlements.estoque_enabled and entitlements.loja_ativa:
        sections.append(
            NavSection(
                title="Estoque",
                items=(
                    NavItem(
                        label="Visão geral",
                        href="/app/loja/estoque",
                        section="Estoque",
                        module=Module.ESTOQUE.value,
                        active_prefix="/app/loja/estoque",
                    ),
                    NavItem(
                        label="Veículos",
                        href="/app/loja/estoque/veiculos",
                        section="Estoque",
                        module=Module.ESTOQUE.value,
                        active_prefix="/app/loja/estoque/veiculos",
                    ),
                ),
            )
        )

    # Contextual: acessos bancários (dono/gerente) — não é módulo principal.
    if roles & ROLES_GESTAO and entitlements.vendas_enabled and entitlements.loja_ativa:
        sections.append(
            NavSection(
                title="Ajustes",
                items=(
                    NavItem(
                        label="Acessos bancários",
                        href="/app/financeiras",
                        section="Ajustes",
                        module=None,
                        active_prefix="/app/financeiras",
                    ),
                ),
            )
        )

    return tuple(sections)


def flatten_nav(sections: tuple[NavSection, ...] | list[NavSection]) -> list[NavItem]:
    items: list[NavItem] = []
    for section in sections:
        items.extend(section.items)
    return items


def nav_item_is_active(item: NavItem, path: str) -> bool:
    prefix = item.active_prefix or item.href
    if path == item.href:
        return True
    if prefix and path.startswith(prefix):
        # Evita que /app/loja/estoque marque /app/loja/estoque/veiculos como "Visão geral"
        if item.href == "/app/loja/estoque" and path.startswith(
            "/app/loja/estoque/veiculos"
        ):
            return False
        return True
    return False
