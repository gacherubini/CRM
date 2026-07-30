"""Auditoria formal de operações da Loja (F5 residual).

Append-only. Domínios:
- atendimento: assumir | devolver | reatribuir (telefone só via HMAC)
- financeira: upsert | testar | revogar (nunca grava senha/token)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import LojaOperacaoAuditoria, agora, novo_id

logger = logging.getLogger("portal.loja_operacao_auditoria")

DOMINIO_ATENDIMENTO = "atendimento"
DOMINIO_FINANCEIRA = "financeira"

ACOES_ATENDIMENTO = frozenset({"assumir", "devolver", "reatribuir"})
ACOES_FINANCEIRA = frozenset({"upsert", "testar", "revogar"})


def registrar_auditoria_operacao(
    db: Session,
    *,
    loja_slug: str,
    dominio: str,
    acao: str,
    ator_email: str,
    telefone_hmac: Optional[str] = None,
    de_email: Optional[str] = None,
    para_email: Optional[str] = None,
    origem: Optional[str] = None,
    provedor: Optional[str] = None,
    success: Optional[bool] = None,
    error_code: Optional[str] = None,
    commit: bool = False,
) -> LojaOperacaoAuditoria:
    """Persiste uma linha de auditoria. Não aceita telefone em claro."""
    if dominio not in {DOMINIO_ATENDIMENTO, DOMINIO_FINANCEIRA}:
        raise ValueError(f"dominio inválido: {dominio}")
    if dominio == DOMINIO_ATENDIMENTO and acao not in ACOES_ATENDIMENTO:
        raise ValueError(f"acao de atendimento inválida: {acao}")
    if dominio == DOMINIO_FINANCEIRA and acao not in ACOES_FINANCEIRA:
        raise ValueError(f"acao financeira inválida: {acao}")

    # Defesa: se alguém passar dígitos longos no lugar do hmac, recusa.
    if telefone_hmac and telefone_hmac.isdigit() and len(telefone_hmac) >= 10:
        raise ValueError("telefone em claro não é permitido em auditoria")

    row = LojaOperacaoAuditoria(
        id=novo_id(),
        loja_slug=loja_slug,
        dominio=dominio,
        acao=acao,
        ator_email=ator_email,
        telefone_hmac=telefone_hmac,
        de_email=de_email,
        para_email=para_email,
        origem=origem,
        provedor=provedor,
        success=success,
        error_code=(error_code[:80] if error_code else None),
        criado_em=agora(),
    )
    db.add(row)
    logger.info(
        "loja_operacao_auditoria dominio=%s acao=%s loja=%s ator=%s provedor=%s "
        "success=%s error=%s hmac=%s",
        dominio,
        acao,
        loja_slug,
        ator_email,
        provedor or "-",
        success if success is not None else "-",
        error_code or "-",
        "sim" if telefone_hmac else "nao",
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def registrar_auditoria_atendimento(
    db: Session,
    *,
    loja_slug: str,
    acao: str,
    ator_email: str,
    telefone_hmac: str,
    de_email: Optional[str] = None,
    para_email: Optional[str] = None,
    origem: str = "handoff_portal",
    commit: bool = False,
) -> LojaOperacaoAuditoria:
    return registrar_auditoria_operacao(
        db,
        loja_slug=loja_slug,
        dominio=DOMINIO_ATENDIMENTO,
        acao=acao,
        ator_email=ator_email,
        telefone_hmac=telefone_hmac,
        de_email=de_email,
        para_email=para_email,
        origem=origem,
        success=True,
        commit=commit,
    )


def registrar_auditoria_financeira(
    db: Session,
    *,
    loja_slug: str,
    acao: str,
    ator_email: str,
    provedor: str,
    success: bool,
    error_code: Optional[str] = None,
    commit: bool = False,
) -> LojaOperacaoAuditoria:
    return registrar_auditoria_operacao(
        db,
        loja_slug=loja_slug,
        dominio=DOMINIO_FINANCEIRA,
        acao=acao,
        ator_email=ator_email,
        provedor=provedor,
        success=success,
        error_code=error_code,
        commit=commit,
    )


def listar_auditoria_operacao(
    db: Session,
    loja_slug: str,
    *,
    dominio: Optional[str] = None,
    limit: int = 80,
) -> list[LojaOperacaoAuditoria]:
    q = db.query(LojaOperacaoAuditoria).filter(
        LojaOperacaoAuditoria.loja_slug == loja_slug
    )
    if dominio:
        q = q.filter(LojaOperacaoAuditoria.dominio == dominio)
    return (
        q.order_by(LojaOperacaoAuditoria.criado_em.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
