from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import GestorAuditLog, novo_id


def registrar_audit(
    db: Session,
    *,
    gestor_email: str,
    loja_slug: str,
    acao: str,
    recurso_id: str | None = None,
) -> None:
    db.add(
        GestorAuditLog(
            id=novo_id(),
            gestor_email=gestor_email,
            loja_slug=loja_slug or "",
            acao=acao[:64],
            recurso_id=(recurso_id or None),
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
