"""Redirects graduais de rotas legadas → shell Revy Loja (Fase 8).

Ativados somente quando:
  ``REVY_LOJA_SHELL_ENABLED=1`` **e** ``REVY_LOJA_REDIRECT_LEGACY=1``

Default de ambos: OFF → zero redirects (comportamento atual).

Mapeamento (GET HTML, paths exatos — não afeta CRUD/subrotas):

| Legado              | Destino Loja              | Condição extra              |
|---------------------|---------------------------|-----------------------------|
| ``/app``            | ``/app/loja/vendas``      | —                           |
| ``/app/funil``      | ``/app/loja/vendas``      | —                           |
| ``/app/financeiro`` | ``/app/loja/vendas``      | —                           |
| ``/app/relatorios`` | ``/app/loja/vendas``      | —                           |
| ``/app/estoque``    | ``/app/loja/estoque``     | lista only; CRUD permanece  |
| ``/app/leads``      | ``/app/loja/atendimento`` | ``ATENDIMENTO_ENABLED``     |
| ``/app/conversas``  | ``/app/loja/atendimento`` | ``ATENDIMENTO_ENABLED``     |

Não redireciona: ``/app/loja/*``, ``/app/estoque/novo``, ``/app/estoque/{id}``,
``/app/leads/{id}``, ``/app/conversas/{tel}``, exports CSV, POST, JSON.
"""
from __future__ import annotations

from app.config import (
    revy_loja_atendimento_enabled,
    revy_loja_redirect_legacy_enabled,
    revy_loja_shell_enabled,
)

# Paths exatos (sem trailing slash) → destino Loja.
_VENDAS_OVERVIEW = "/app/loja/vendas"
_ESTOQUE_OVERVIEW = "/app/loja/estoque"
_ATENDIMENTO = "/app/loja/atendimento"

# Sempre (com shell + redirect on).
LEGACY_ALWAYS: dict[str, str] = {
    "/app": _VENDAS_OVERVIEW,
    "/app/funil": _VENDAS_OVERVIEW,
    "/app/financeiro": _VENDAS_OVERVIEW,
    "/app/relatorios": _VENDAS_OVERVIEW,
    "/app/estoque": _ESTOQUE_OVERVIEW,
}

# Exigem REVY_LOJA_ATENDIMENTO_ENABLED=1.
LEGACY_ATENDIMENTO: dict[str, str] = {
    "/app/leads": _ATENDIMENTO,
    "/app/conversas": _ATENDIMENTO,
}


def normalize_path(path: str) -> str:
    """Normaliza path para lookup (remove trailing slash, exceto ``/``)."""
    if not path:
        return "/"
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/")
    return path


def resolve_legacy_redirect(
    path: str,
    *,
    shell_enabled: bool | None = None,
    redirect_enabled: bool | None = None,
    atendimento_enabled: bool | None = None,
) -> str | None:
    """Retorna destino 303 se o path legado deve ser redirecionado; senão None.

    Flags default: leem env em runtime (testáveis via monkeypatch).
    """
    if shell_enabled is None:
        shell_enabled = revy_loja_shell_enabled()
    if redirect_enabled is None:
        redirect_enabled = revy_loja_redirect_legacy_enabled()
    if atendimento_enabled is None:
        atendimento_enabled = revy_loja_atendimento_enabled()

    if not shell_enabled or not redirect_enabled:
        return None

    norm = normalize_path(path)
    if norm.startswith("/app/loja"):
        return None

    if norm in LEGACY_ALWAYS:
        return LEGACY_ALWAYS[norm]

    if norm in LEGACY_ATENDIMENTO:
        if atendimento_enabled:
            return LEGACY_ATENDIMENTO[norm]
        return None

    return None


def should_consider_request(method: str, accept: str | None) -> bool:
    """Só GET "HTML" — evita interceptar CSV, JSON API e mutações."""
    if (method or "").upper() != "GET":
        return False
    acc = (accept or "*/*").lower()
    # Pedido claramente JSON/API sem HTML → não redirecionar.
    if "application/json" in acc and "text/html" not in acc:
        return False
    # Downloads CSV explícitos.
    if "text/csv" in acc and "text/html" not in acc:
        return False
    return True
