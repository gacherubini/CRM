"""Contratos do domínio Revy Loja — independentes de FastAPI/SQLAlchemy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

# Estados de um read model de tela: nunca inventar métrica quando a fonte falha.
StatusReadModel = Literal["ok", "vazio", "erro", "parcial"]


class Role(str, Enum):
    """Cargos operacionais da Loja (não inclui papéis do Control)."""

    DONO = "dono"
    GERENTE = "gerente"
    VENDEDOR = "vendedor"


class Module(str, Enum):
    """Módulos principais visíveis no shell Revy Loja."""

    VENDAS = "vendas"
    ESTOQUE = "estoque"
    COPILOTO = "copiloto"
    FINANCEIRO = "financeiro"


ROLES_OPERACIONAIS: frozenset[str] = frozenset(
    {Role.DONO.value, Role.GERENTE.value, Role.VENDEDOR.value}
)

ROLES_GESTAO: frozenset[str] = frozenset({Role.DONO.value, Role.GERENTE.value})


@dataclass(frozen=True)
class StoreMembership:
    """Vínculo de uma pessoa com uma loja e os cargos ativos nela."""

    loja_slug: str
    roles: frozenset[str]
    ativo: bool = True


@dataclass(frozen=True)
class ActorLoja:
    """Pessoa autenticada no Revy Loja (projeção; não é o ORM Usuario)."""

    pessoa_id: str
    email: str
    nome: str
    memberships: tuple[StoreMembership, ...]


@dataclass(frozen=True)
class StoreContext:
    """Loja selecionada na sessão e união dos cargos ativos nela."""

    loja_slug: str
    roles: frozenset[str]
    loja_state: str = "ativa"


@dataclass(frozen=True)
class EntitlementState:
    """Estado contratual/operacional dos módulos da loja selecionada."""

    loja_slug: str
    loja_ativa: bool
    vendas_enabled: bool
    estoque_enabled: bool
    source: str  # fail_open | projecao | control | cache
    copiloto_enabled: bool = False
    financeiro_enabled: bool = False


@dataclass(frozen=True)
class NavItem:
    """Item de navegação permitido pelo shell."""

    label: str
    href: str
    section: str
    module: str | None = None
    active_prefix: str | None = None


@dataclass(frozen=True)
class NavSection:
    title: str
    items: tuple[NavItem, ...]
