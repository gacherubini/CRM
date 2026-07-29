"""Seams de permissão entre Revy Control e cargos da Loja.

Control e Loja compartilham a mesma Pessoa, mas os códigos de autorização
vivem em namespaces distintos (`control:` vs `store:`) e nunca se misturam:

- ``ControlPermissions`` deriva somente de ``Actor.role`` (AcessoControl).
- ``StorePermissions`` deriva somente de cargos ativos em *uma* Loja.
- Cargos de uma Loja nunca autorizam outra Loja nem a superfície Control.
- Papel Control nunca autoriza operações de cargo da Loja.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from app.control.types import Actor, ControlAccountRole, StoreRole
from app.models import CargoLoja

CONTROL_PREFIX = "control:"
STORE_PREFIX = "store:"

CONTROL_ADMIN = f"{CONTROL_PREFIX}{ControlAccountRole.ADMIN.value}"
CONTROL_GESTOR = f"{CONTROL_PREFIX}{ControlAccountRole.MANAGER.value}"

STORE_DONO = f"{STORE_PREFIX}{StoreRole.OWNER.value}"
STORE_GERENTE = f"{STORE_PREFIX}{StoreRole.MANAGER.value}"
STORE_VENDEDOR = f"{STORE_PREFIX}{StoreRole.SELLER.value}"

_CONTROL_BY_ROLE = {
    ControlAccountRole.ADMIN.value: CONTROL_ADMIN,
    ControlAccountRole.MANAGER.value: CONTROL_GESTOR,
}

_STORE_BY_CARGO = {
    StoreRole.OWNER.value: STORE_DONO,
    StoreRole.MANAGER.value: STORE_GERENTE,
    StoreRole.SELLER.value: STORE_VENDEDOR,
}


class PermissionBleed(ValueError):
    """Códigos de Control e Loja se sobrepuseram ou usaram namespace errado."""


class ControlPermissions:
    """Permissões da superfície Control a partir do Actor (papel global)."""

    @staticmethod
    def for_actor(actor: Actor) -> frozenset[str]:
        code = _CONTROL_BY_ROLE.get(actor.role)
        if code is None:
            return frozenset()
        return frozenset({code})


class StorePermissions:
    """União de cargos ativos da Pessoa em uma única Loja selecionada."""

    @staticmethod
    def for_person_in_store(
        session_factory: Callable[[], Any],
        person_id: str,
        store_id: str,
    ) -> frozenset[str]:
        with session_factory() as db:
            rows = (
                db.query(CargoLoja.cargo)
                .filter(
                    CargoLoja.pessoa_id == person_id,
                    CargoLoja.loja_id == store_id,
                    CargoLoja.encerrado_em.is_(None),
                )
                .all()
            )
        codes: set[str] = set()
        for (cargo,) in rows:
            code = _STORE_BY_CARGO.get(cargo)
            if code is not None:
                codes.add(code)
        return frozenset(codes)


def assert_no_bleed(
    control_perms: Iterable[str],
    store_perms: Iterable[str],
) -> None:
    """Garante que Control e Loja não compartilham códigos nem prefixos."""
    control = frozenset(control_perms)
    store = frozenset(store_perms)

    bad_control = sorted(
        code for code in control if not code.startswith(CONTROL_PREFIX)
    )
    bad_store = sorted(
        code for code in store if not code.startswith(STORE_PREFIX)
    )
    overlap = sorted(control & store)

    problems: list[str] = []
    if bad_control:
        problems.append(
            f"control_perms fora do namespace {CONTROL_PREFIX!r}: {bad_control}"
        )
    if bad_store:
        problems.append(
            f"store_perms fora do namespace {STORE_PREFIX!r}: {bad_store}"
        )
    if overlap:
        problems.append(f"códigos compartilhados entre superfícies: {overlap}")

    # Controle não pode carregar store:* e vice-versa (mesmo que prefixo "correto"
    # tenha sido adulterado via interseção vazia com códigos invertidos).
    control_store_leak = sorted(
        code for code in control if code.startswith(STORE_PREFIX)
    )
    store_control_leak = sorted(
        code for code in store if code.startswith(CONTROL_PREFIX)
    )
    if control_store_leak:
        problems.append(
            f"control_perms contém códigos de loja: {control_store_leak}"
        )
    if store_control_leak:
        problems.append(
            f"store_perms contém códigos de control: {store_control_leak}"
        )

    if problems:
        raise PermissionBleed("; ".join(problems))
