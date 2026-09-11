"""Identidade de operação das vendas, resolvida para a loja ativa da sessão."""
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.config import revy_loja_entitlements_enabled
from app.loja import identity
from app.loja.permissions import LojaPermissionError, require_module
from app.loja.types import Module
from app.web.loja_shell import ensure_session_loja, resolve_store_and_entitlements


@dataclass(frozen=True)
class UsuarioVendas:
    """Visão por requisição; nunca altera a linha Usuario durante um commit."""

    id: str
    email: str
    nome: str
    papel: str
    loja_slug: str
    ativo: bool


def usuario_vendas_atual(request: Request, db: Session):
    usuario = usuario_atual(request, db)
    if usuario is None:
        return None
    ensure_session_loja(request, usuario)
    slug = identity.session_loja_slug(request.session) or usuario.loja_slug
    try:
        _store, ents, actor = resolve_store_and_entitlements(request, usuario, db)
        # O resolver do shell admite fallback para desenhar o seletor. Uma
        # operação de venda nunca troca de loja silenciosamente.
        identity.select_store_slug(actor, slug)
        roles = identity.roles_in_store(actor, slug)
        if revy_loja_entitlements_enabled():
            require_module(ents, Module.VENDAS)
    except LojaPermissionError as exc:
        raise HTTPException(status_code=403, detail="Sem acesso às vendas desta loja.") from exc
    papel = next(p for p in ("dono", "gerente", "vendedor") if p in roles)
    return UsuarioVendas(
        id=usuario.id, email=usuario.email, nome=usuario.nome,
        papel=papel, loja_slug=slug, ativo=usuario.ativo,
    )
