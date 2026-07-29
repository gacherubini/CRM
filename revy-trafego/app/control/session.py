from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request

from app.control.access import AccessControl
from app.control.types import AccessibleStore, Actor, StoreRef


def actor_from_user(user: Any) -> Actor:
    return Actor(
        id=user.id,
        email=user.email,
        name=user.nome,
        role=user.papel,
    )


def visible_stores(
    session_factory: Callable[[], Any],
    user: Any,
) -> tuple[AccessibleStore, ...]:
    return AccessControl(session_factory).scope(actor_from_user(user))


def select_store(
    request: Request,
    session_factory: Callable[[], Any],
    user: Any,
    store_id: str,
) -> AccessibleStore:
    authorized = AccessControl(session_factory).authorize(
        actor_from_user(user),
        StoreRef(id=store_id),
    )
    request.session["loja_id"] = authorized.store.id
    request.session["loja_slug"] = authorized.store.slug
    return authorized


def current_store(
    request: Request,
    session_factory: Callable[[], Any],
    user: Any,
) -> AccessibleStore | None:
    store_id = (request.session.get("loja_id") or "").strip()
    if not store_id:
        return None
    authorized = AccessControl(session_factory).authorize(
        actor_from_user(user),
        StoreRef(id=store_id),
    )
    request.session["loja_slug"] = authorized.store.slug
    return authorized
