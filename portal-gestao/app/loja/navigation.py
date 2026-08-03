"""Navegação permitida do shell Revy Loja (somente Vendas e Estoque)."""
from __future__ import annotations

from app.config import revy_loja_whatsapp_enabled
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
    whatsapp_enabled: bool | None = None,
) -> tuple[NavSection, ...]:
    """Produz seções de navegação conforme contrato e cargos.

    Com shell desligado o chamador não deve usar este resultado (UI legada).
    Inclui os números de WhatsApp em Ajustes (dono/gerente) quando a flag está
    ligada. Não inclui Meta nem Google — configuração de tráfego é do Control.

    ``whatsapp_enabled=None`` consulta a flag em runtime; passar o booleano
    explicitamente mantém a função pura (usado nos testes de navegação).
    """
    if not shell_enabled:
        return ()

    if whatsapp_enabled is None:
        whatsapp_enabled = revy_loja_whatsapp_enabled()

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

    # Contextual (dono/gerente): não é módulo principal.
    # Acessos bancários e lista operacional da equipe (estrutura no Control).
    if roles & ROLES_GESTAO and entitlements.loja_ativa:
        ajustes: list[NavItem] = []
        if entitlements.vendas_enabled:
            ajustes.append(
                NavItem(
                    label="Acessos bancários",
                    href="/app/financeiras",
                    section="Ajustes",
                    module=None,
                    active_prefix="/app/financeiras",
                )
            )
        if whatsapp_enabled:
            ajustes.append(
                NavItem(
                    label="Números de WhatsApp",
                    href="/app/loja/whatsapp",
                    section="Ajustes",
                    module=None,
                    active_prefix="/app/loja/whatsapp",
                )
            )
        # Só status (Meta/Google/WhatsApp), não configuração: o Portal consome o
        # agregador do Revy Control por HTTP. Visível a dono/gerente.
        ajustes.append(
            NavItem(
                label="Integrações",
                href="/app/loja/integracoes",
                section="Ajustes",
                module=None,
                active_prefix="/app/loja/integracoes",
            )
        )
        ajustes.append(
            NavItem(
                label="Equipe",
                href="/app/loja/equipe",
                section="Ajustes",
                module=None,
                active_prefix="/app/loja/equipe",
            )
        )
        sections.append(NavSection(title="Ajustes", items=tuple(ajustes)))

    # Conta: perfil e troca de senha da própria conta — todos os papéis operacionais.
    sections.append(
        NavSection(
            title="Conta",
            items=(
                NavItem(
                    label="Perfil",
                    href="/app/loja/perfil",
                    section="Conta",
                    module=None,
                    active_prefix="/app/loja/perfil",
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
