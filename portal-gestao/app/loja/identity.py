"""Resolve pessoa, loja ativa e cargos a partir da projeção Usuario / Control."""
from __future__ import annotations

from typing import Any, Mapping

from app.loja.permissions import SemAcessoLoja
from app.loja.types import (
    ROLES_OPERACIONAIS,
    ActorLoja,
    StoreContext,
    StoreMembership,
)

# Chave de sessão para a loja selecionada (multi-loja).
SESSION_LOJA_KEY = "loja_slug"


def _roles_from_papel(papel: str | None) -> frozenset[str]:
    if not papel:
        return frozenset()
    p = str(papel).strip().lower()
    # admin_plataforma não é cargo operacional da Loja; não concede união implícita.
    if p in ROLES_OPERACIONAIS:
        return frozenset({p})
    return frozenset()


def membership_from_usuario(usuario: Any) -> StoreMembership:
    """Uma membership a partir do Usuario legado (cutover)."""
    return StoreMembership(
        loja_slug=str(getattr(usuario, "loja_slug", "") or "").strip(),
        roles=_roles_from_papel(getattr(usuario, "papel", None)),
        ativo=bool(getattr(usuario, "ativo", True)),
    )


def actor_from_usuario(
    usuario: Any,
    memberships: tuple[StoreMembership, ...] | list[StoreMembership] | None = None,
) -> ActorLoja:
    """Constrói ActorLoja a partir do Usuario (projeção) e memberships opcionais do Control.

    Se ``memberships`` for omitido, usa somente ``usuario.loja_slug`` + ``usuario.papel``.
    Acesso gestora no Control **não** entra aqui — só cargos da Loja.
    """
    if memberships is None:
        m = membership_from_usuario(usuario)
        mems: tuple[StoreMembership, ...] = (m,) if m.loja_slug else ()
    else:
        # Memberships do Control aumentam, não substituem: a loja legada
        # (usuario.loja_slug) nunca some da sessão do dono.
        legacy = membership_from_usuario(usuario)
        slugs = {mm.loja_slug for mm in memberships}
        mems = tuple(memberships)
        if legacy.loja_slug and legacy.loja_slug not in slugs:
            mems = mems + (legacy,)
    return ActorLoja(
        pessoa_id=str(getattr(usuario, "id", "") or ""),
        email=str(getattr(usuario, "email", "") or ""),
        nome=str(getattr(usuario, "nome", "") or ""),
        memberships=mems,
    )


def active_memberships(actor: ActorLoja) -> tuple[StoreMembership, ...]:
    return tuple(
        m
        for m in actor.memberships
        if m.ativo and m.loja_slug and m.roles
    )


def available_store_slugs(actor: ActorLoja) -> tuple[str, ...]:
    return tuple(m.loja_slug for m in active_memberships(actor))


def resolve_store_context(
    actor: ActorLoja,
    session_loja_slug: str | None = None,
    *,
    loja_state: str = "ativa",
) -> StoreContext:
    """Seleciona a loja da sessão (se autorizada) e devolve união dos cargos nela.

    Cargo de loja A **nunca** vaza para o contexto de loja B.
    """
    by_slug: dict[str, StoreMembership] = {
        m.loja_slug: m for m in active_memberships(actor)
    }
    if not by_slug:
        raise SemAcessoLoja("convite inativo ou sem loja autorizada")

    chosen = (session_loja_slug or "").strip()
    if chosen and chosen in by_slug:
        membership = by_slug[chosen]
    else:
        # Preferir membership única do usuário; senão a primeira estável por slug.
        membership = by_slug[sorted(by_slug.keys())[0]] if len(by_slug) > 1 else next(
            iter(by_slug.values())
        )
        # Com uma só loja, ordem irrelevante; com várias e sessão inválida, slug ordenado.
        if chosen not in by_slug and len(by_slug) > 1:
            membership = by_slug[sorted(by_slug.keys())[0]]

    return StoreContext(
        loja_slug=membership.loja_slug,
        roles=frozenset(membership.roles),
        loja_state=loja_state,
    )


def select_store_slug(actor: ActorLoja, loja_slug: str) -> str:
    """Valida e devolve o slug se a pessoa tiver membership ativa; senão erro."""
    slug = (loja_slug or "").strip()
    allowed = set(available_store_slugs(actor))
    if slug not in allowed:
        raise SemAcessoLoja(f"loja '{slug}' não autorizada para esta pessoa")
    return slug


def roles_in_store(actor: ActorLoja, loja_slug: str) -> frozenset[str]:
    """Cargos apenas da loja pedida (isolamento multi-loja)."""
    slug = (loja_slug or "").strip()
    for m in active_memberships(actor):
        if m.loja_slug == slug:
            return frozenset(m.roles)
    return frozenset()


def union_roles_for_store(
    memberships: list[StoreMembership] | tuple[StoreMembership, ...],
    loja_slug: str,
) -> frozenset[str]:
    """Une cargos de várias memberships da mesma loja (sem papel global)."""
    slug = (loja_slug or "").strip()
    roles: set[str] = set()
    for m in memberships:
        if m.ativo and m.loja_slug == slug:
            roles |= set(m.roles) & ROLES_OPERACIONAIS
    return frozenset(roles)


def session_loja_slug(session: Mapping[str, Any] | None) -> str | None:
    if not session:
        return None
    raw = session.get(SESSION_LOJA_KEY)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None
