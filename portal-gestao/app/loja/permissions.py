"""Autorização de domínio — menu oculto não substitui estas checagens."""
from __future__ import annotations

from app.loja.types import EntitlementState, Module, StoreContext


class LojaPermissionError(Exception):
    """Base para recusas de autorização no Revy Loja."""

    def __init__(self, message: str = "acesso negado"):
        super().__init__(message)
        self.message = message


class ModuloNaoContratado(LojaPermissionError):
    """Módulo não contratado, suspenso ou loja inativa."""

    def __init__(self, module: Module | str, message: str | None = None):
        mod = module.value if isinstance(module, Module) else str(module)
        super().__init__(message or f"módulo '{mod}' indisponível nesta loja")
        self.module = mod


class PapelInsuficiente(LojaPermissionError):
    """Cargo da loja selecionada não autoriza a ação."""

    def __init__(self, message: str = "papel insuficiente para esta ação"):
        super().__init__(message)


class SemAcessoLoja(LojaPermissionError):
    """Pessoa sem membership ativo ou convite ainda não ativado."""

    def __init__(self, message: str = "sem acesso a loja operacional"):
        super().__init__(message)


def module_enabled(entitlements: EntitlementState, module: Module | str) -> bool:
    mod = module.value if isinstance(module, Module) else str(module)
    if not entitlements.loja_ativa:
        return False
    if mod == Module.VENDAS.value:
        return entitlements.vendas_enabled
    if mod == Module.ESTOQUE.value:
        return entitlements.estoque_enabled
    return False


def require_module(entitlements: EntitlementState, module: Module | str) -> None:
    if not module_enabled(entitlements, module):
        raise ModuloNaoContratado(module)


def require_roles(store: StoreContext, *roles: str) -> None:
    if not roles:
        return
    permitidos = frozenset(roles)
    if store.roles.isdisjoint(permitidos):
        raise PapelInsuficiente(
            f"requer um dos cargos: {', '.join(sorted(permitidos))}"
        )


def pode_escrever_operacional(entitlements: EntitlementState, module: Module | str) -> bool:
    """Novo processamento (venda, estoque, atendimento) exige módulo ativo e loja ativa."""
    return module_enabled(entitlements, module)
