"""Auditoria de chaves Pixel / CAPI — flags de Event Match Quality sem PII."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import PixelCapiAuditoria, agora, novo_id

logger = logging.getLogger("portal.pixel_capi")


def _sufixo(valor: str | None, n: int = 6) -> str | None:
    s = (valor or "").strip()
    if not s:
        return None
    return s[-n:] if len(s) > n else s


def registrar_auditoria_pixel(
    db: Session,
    *,
    loja_slug: str,
    origem: str,
    event_name: str | None = None,
    event_id: str | None = None,
    pixel_id: str | None = None,
    modo: str | None = None,
    tem_ph: bool = False,
    tem_em: bool = False,
    tem_fbclid: bool = False,
    tem_fbc: bool = False,
    tem_ctwa_clid: bool = False,
    tem_external_id: bool = False,
    tem_test_event_code: bool = False,
    enviar_page_view: bool | None = None,
    enviar_lead: bool | None = None,
    enviar_purchase: bool | None = None,
    status: str | None = None,
    http_status: int | None = None,
    venda_id: str | None = None,
    detalhe: str | None = None,
    commit: bool = False,
) -> PixelCapiAuditoria:
    row = PixelCapiAuditoria(
        id=novo_id(),
        loja_slug=loja_slug,
        origem=origem,
        event_name=event_name,
        event_id=(event_id or None),
        pixel_id_sufixo=_sufixo(pixel_id, 6),
        modo=modo,
        tem_ph=bool(tem_ph),
        tem_em=bool(tem_em),
        tem_fbclid=bool(tem_fbclid),
        tem_fbc=bool(tem_fbc),
        tem_ctwa_clid=bool(tem_ctwa_clid),
        tem_external_id=bool(tem_external_id),
        tem_test_event_code=bool(tem_test_event_code),
        enviar_page_view=enviar_page_view,
        enviar_lead=enviar_lead,
        enviar_purchase=enviar_purchase,
        status=status,
        http_status=http_status,
        venda_id=venda_id,
        detalhe=(detalhe[:240] if detalhe else None),
        criada_em=agora(),
    )
    db.add(row)
    logger.info(
        "pixel_capi_auditoria origem=%s loja=%s event=%s modo=%s ph=%s fbclid=%s fbc=%s "
        "ctwa=%s em=%s ext=%s status=%s pixel=…%s",
        origem,
        loja_slug,
        event_name or "-",
        modo or "-",
        "sim" if tem_ph else "nao",
        "sim" if tem_fbclid else "nao",
        "sim" if tem_fbc else "nao",
        "sim" if tem_ctwa_clid else "nao",
        "sim" if tem_em else "nao",
        "sim" if tem_external_id else "nao",
        status or "-",
        row.pixel_id_sufixo or "-",
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def flags_do_payload_capi(body: dict[str, Any] | None) -> dict[str, bool]:
    """Lê user_data do body Graph e devolve flags de chaves presentes."""
    data = (body or {}).get("data") or []
    user: dict[str, Any] = {}
    if data and isinstance(data[0], dict):
        user = data[0].get("user_data") or {}
    return {
        "tem_ph": bool(user.get("ph")),
        "tem_em": bool(user.get("em")),
        "tem_fbc": bool(user.get("fbc")),
        "tem_ctwa_clid": bool(user.get("ctwa_clid")),
        "tem_external_id": bool(user.get("external_id")),
        "tem_fbclid": False,  # fbclid vira fbc no payload; flag separado no caller
    }


def listar_auditoria_pixel(
    db: Session,
    loja_slug: str,
    *,
    limit: int = 80,
    origem: str | None = None,
) -> list[PixelCapiAuditoria]:
    q = db.query(PixelCapiAuditoria).filter(PixelCapiAuditoria.loja_slug == loja_slug)
    if origem:
        q = q.filter(PixelCapiAuditoria.origem == origem)
    return (
        q.order_by(PixelCapiAuditoria.criada_em.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
