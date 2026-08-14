"""Navegação permitida do shell Revy Loja (Copiloto, Vendas e Estoque).

Copiloto entrou em 2026-08-11 por decisão do dono e é a primeira seção: a
tela de "o que fazer hoje" vem antes das telas de "quanto deu".
"""
from __future__ import annotations

from app.config import revy_loja_copiloto_enabled, revy_loja_whatsapp_enabled
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
    copiloto_enabled: bool | None = None,
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

    if copiloto_enabled is None:
        copiloto_enabled = revy_loja_copiloto_enabled()

    roles = store.roles & ROLES_OPERACIONAIS
    if not roles:
        return ()

    sections: list[NavSection] = []

    # Copiloto: só dono/gerente, só com flag + entitlement do módulo.
    if (
        copiloto_enabled
        and entitlements.copiloto_enabled
        and entitlements.loja_ativa
        and roles & ROLES_GESTAO
    ):
        sections.append(
            NavSection(
                title="Copiloto",
                items=(
                    NavItem(
                        label="Copiloto de Vendas",
                        href="/app/loja/copiloto",
                        section="Copiloto",
                        module=Module.COPILOTO.value,
                        active_prefix="/app/loja/copiloto",
                    ),
                    NavItem(
                        label="Hoje",
                        href="/app/loja/copiloto/hoje",
                        section="Copiloto",
                        module=Module.COPILOTO.value,
                        active_prefix="/app/loja/copiloto/hoje",
                    ),
                ),
            )
        )

    if entitlements.vendas_enabled and entitlements.loja_ativa:
        sections.append(
            NavSection(
                title="Vendas",
                items=(
                    NavItem(
                        label="Resultado",
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
                    # Registrar/confirmar venda vive no shell: antes só existia
                    # no atendimento, caindo na tela legada fora do menu.
                    NavItem(
                        label=(
                            "Vendas da loja"
                            if roles & ROLES_GESTAO
                            else "Minhas vendas"
                        ),
                        href="/app/loja/vendas/lista",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/loja/vendas/lista",
                    ),
                    NavItem(
                        label="Agente do WhatsApp",
                        href="/app/loja/agente",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/loja/agente",
                    ),
                    NavItem(
                        label="Simulações",
                        href="/app/simulacoes",
                        section="Vendas",
                        module=Module.VENDAS.value,
                        active_prefix="/app/simulacoes",
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
                        label="Situação do estoque",
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
                    NavItem(
                        label="Vitrine",
                        href="/app/loja/estoque/vitrine",
                        section="Estoque",
                        module=Module.ESTOQUE.value,
                        active_prefix="/app/loja/estoque/vitrine",
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
        # Grupo WA de fotos/cadastro + números autorizados (aviso simulação/handoff).
        # Rota legada /app/operacao/numeros — precisa aparecer no shell (antes sumia do menu).
        if entitlements.estoque_enabled or entitlements.vendas_enabled:
            ajustes.append(
                NavItem(
                    label="Grupo do estoque",
                    href="/app/operacao/numeros",
                    section="Ajustes",
                    module=None,
                    active_prefix="/app/operacao/numeros",
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
    if path == item.href:
        return True

    # Veículos: entrada shell + lista/CRUD legado em /app/estoque*
    if item.href == "/app/loja/estoque/veiculos":
        if path.startswith("/app/loja/estoque/veiculos"):
            return True
        if path == "/app/estoque" or path.startswith("/app/estoque/"):
            return True
        return False

    prefix = item.active_prefix or item.href
    if prefix and path.startswith(prefix):
        # Evita que Visão geral do estoque marque subpáginas (veículos, vitrine)
        if item.href == "/app/loja/estoque" and path != "/app/loja/estoque":
            return False
        # Mesmo caso em Vendas: Resultado não acende na lista de vendas.
        if item.href == "/app/loja/vendas" and path != "/app/loja/vendas":
            return False
        # Chat do Copiloto não acende em /hoje (mesmo prefixo /app/loja/copiloto).
        if item.href == "/app/loja/copiloto" and path != "/app/loja/copiloto":
            return False
        return True
    return False
