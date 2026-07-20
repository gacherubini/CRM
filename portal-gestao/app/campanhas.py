"""Campanhas de tráfego pago: validação, match UTM e helpers de CRUD."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models import Campanha, CampanhaGasto, agora

CANAIS = frozenset({"meta", "google", "indicacao", "organico", "outro"})
STATUS = frozenset({"ativa", "pausada", "encerrada"})
CANAIS_ROTULO = {
    "meta": "Meta (Instagram/Facebook)",
    "google": "Google Ads",
    "indicacao": "Indicação",
    "organico": "Orgânico",
    "outro": "Outro",
}
STATUS_ROTULO = {
    "ativa": "Ativa",
    "pausada": "Pausada",
    "encerrada": "Encerrada",
}
CENTAVOS = Decimal("0.01")


def normalizar_utm(valor: str | None) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip().casefold()
    return s or None


def parse_brl_valor(texto: str | None) -> Decimal | None:
    t = (texto or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except (InvalidOperation, ValueError):
        return None
    if v < 0:
        return None
    return v.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def validar_campanha_payload(dados: dict) -> list[str]:
    erros: list[str] = []
    nome = (dados.get("nome") or "").strip()
    if not nome:
        erros.append("nome é obrigatório")
    elif len(nome) > 160:
        erros.append("nome muito longo")

    canal = (dados.get("canal") or "").strip().casefold()
    if canal not in CANAIS:
        erros.append("canal inválido")

    status = (dados.get("status") or "ativa").strip().casefold()
    if status not in STATUS:
        erros.append("status inválido")

    utm_c = normalizar_utm(dados.get("utm_campaign"))
    if not utm_c:
        erros.append("utm_campaign é obrigatório")
    elif len(utm_c) > 120:
        erros.append("utm_campaign muito longo")

    return erros


def lead_casa_campanha(lead: dict, campanha: Campanha, *, modo: str) -> bool:
    """modo: 'first' | 'last'."""
    assert modo in ("first", "last")
    if modo == "first":
        camp_key = normalizar_utm(
            lead.get("utm_campaign_first") or lead.get("utm_campaign")
        )
        content_key = normalizar_utm(
            lead.get("utm_content_first") or lead.get("utm_content")
        )
    else:
        camp_key = normalizar_utm(
            lead.get("utm_campaign_last") or lead.get("utm_campaign")
        )
        content_key = normalizar_utm(
            lead.get("utm_content_last") or lead.get("utm_content")
        )
    if not camp_key:
        return False
    if camp_key != normalizar_utm(campanha.utm_campaign):
        return False
    if campanha.utm_content:
        if content_key != normalizar_utm(campanha.utm_content):
            return False
    return True


def campanha_por_utm(
    db: Session, loja_slug: str, utm_campaign: str | None
) -> Campanha | None:
    norm = normalizar_utm(utm_campaign)
    if not norm:
        return None
    return (
        db.query(Campanha)
        .filter(
            Campanha.loja_slug == loja_slug,
            Campanha.utm_campaign_norm == norm,
        )
        .first()
    )


def resolver_campanhas_do_lead(
    db: Session, loja_slug: str, lead: dict
) -> tuple[Campanha | None, Campanha | None]:
    campanhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == loja_slug)
        .all()
    )
    first_c = next(
        (c for c in campanhas if lead_casa_campanha(lead, c, modo="first")),
        None,
    )
    last_c = next(
        (c for c in campanhas if lead_casa_campanha(lead, c, modo="last")),
        None,
    )
    return first_c, last_c


def aplicar_snapshot_venda(venda, lead: dict | None, db: Session, loja_slug: str) -> None:
    if not lead:
        return
    first_c, last_c = resolver_campanhas_do_lead(db, loja_slug, lead)
    venda.campanha_id_first = first_c.id if first_c else None
    venda.campanha_id_last = last_c.id if last_c else None
    venda.utm_campaign_first = (
        lead.get("utm_campaign_first") or lead.get("utm_campaign") or None
    )
    venda.utm_campaign_last = (
        lead.get("utm_campaign_last") or lead.get("utm_campaign") or None
    )


def gasto_no_periodo(
    gastos: list[CampanhaGasto],
    campanha_id: str,
    d_inicio: date,
    d_fim: date,
) -> Decimal:
    total = Decimal("0")
    for g in gastos:
        if g.campanha_id != campanha_id:
            continue
        if d_inicio <= g.referencia <= d_fim:
            total += g.valor
    return total.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def payload_form(form: Any) -> dict[str, str]:
    campos = (
        "nome",
        "canal",
        "status",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "periodo_inicio",
        "periodo_fim",
        "notas",
    )
    return {c: (form.get(c) or "").strip() for c in campos}


def preencher_campanha(campanha: Campanha, dados: dict, *, email: str | None = None) -> None:
    campanha.nome = dados["nome"].strip()
    campanha.canal = dados["canal"].strip().casefold()
    campanha.status = (dados.get("status") or "ativa").strip().casefold()
    campanha.utm_source = (dados.get("utm_source") or "").strip() or None
    campanha.utm_medium = (dados.get("utm_medium") or "").strip() or None
    campanha.utm_campaign = (dados.get("utm_campaign") or "").strip()
    campanha.utm_campaign_norm = normalizar_utm(campanha.utm_campaign) or ""
    campanha.utm_content = (dados.get("utm_content") or "").strip() or None
    campanha.utm_term = (dados.get("utm_term") or "").strip() or None
    campanha.notas = (dados.get("notas") or "").strip() or None
    pi = (dados.get("periodo_inicio") or "").strip()
    pf = (dados.get("periodo_fim") or "").strip()
    try:
        campanha.periodo_inicio = date.fromisoformat(pi) if pi else None
    except ValueError:
        campanha.periodo_inicio = None
    try:
        campanha.periodo_fim = date.fromisoformat(pf) if pf else None
    except ValueError:
        campanha.periodo_fim = None
    campanha.atualizada_em = agora()
    if email and not campanha.criada_por_email:
        campanha.criada_por_email = email
