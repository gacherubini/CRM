"""Campanhas de tráfego pago: validação, match UTM e helpers de CRUD."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models import Campanha, CampanhaGasto, agora, novo_id

CANAIS = frozenset(
    {
        "meta",
        "google",
        "tiktok",
        "olx",
        "marketplace",
        "facebook_marketplace",
        "indicacao",
        "organico",
        "outro",
    }
)
STATUS = frozenset({"ativa", "pausada", "encerrada"})
CANAIS_ROTULO = {
    "meta": "Meta (Instagram/Facebook)",
    "google": "Google Ads",
    "tiktok": "TikTok",
    "olx": "OLX",
    "marketplace": "Marketplace",
    "facebook_marketplace": "Facebook Marketplace",
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


@dataclass(frozen=True)
class LinhaGastoCsv:
    numero: int
    campanha: Campanha
    valor: Decimal
    referencia: date
    nota: str | None


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


def parse_gastos_csv(
    conteudo: bytes,
    campanhas: list[Campanha],
) -> tuple[list[LinhaGastoCsv], list[str]]:
    """Lê o template Revy sem abortar linhas válidas por causa de uma inválida."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["O arquivo precisa estar em UTF-8."]
    if not texto.strip():
        return [], ["O arquivo CSV está vazio."]
    try:
        dialect = csv.Sniffer().sniff(texto[:4096], delimiters=";,")
        reader = csv.DictReader(io.StringIO(texto), dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(io.StringIO(texto), delimiter=";")
    headers = {normalizar_utm(h) for h in (reader.fieldnames or [])}
    obrigatorios = {"utm_campaign", "valor", "referencia"}
    if not obrigatorios.issubset(headers):
        return [], ["Cabeçalho inválido. Use: utm_campaign;valor;referencia;nota."]

    por_utm = {c.utm_campaign_norm: c for c in campanhas}
    linhas: list[LinhaGastoCsv] = []
    erros: list[str] = []
    for numero, raw in enumerate(reader, start=2):
        if not any((v or "").strip() for v in raw.values()):
            continue
        utm = normalizar_utm(raw.get("utm_campaign"))
        campanha = por_utm.get(utm or "")
        valor = parse_brl_valor(raw.get("valor"))
        try:
            referencia = date.fromisoformat((raw.get("referencia") or "").strip())
        except ValueError:
            referencia = None
        motivos: list[str] = []
        if campanha is None:
            motivos.append(
                f"campanha '{(raw.get('utm_campaign') or '').strip()}' não cadastrada"
            )
        if valor is None or valor <= 0:
            motivos.append("valor inválido")
        if referencia is None:
            motivos.append("data de referência inválida")
        if motivos:
            erros.append(f"Linha {numero}: " + "; ".join(motivos) + ".")
            continue
        nota = (raw.get("nota") or "").strip()[:240] or None
        linhas.append(
            LinhaGastoCsv(
                numero=numero,
                campanha=campanha,
                valor=valor,
                referencia=referencia,
                nota=nota,
            )
        )
    return linhas, erros


def salvar_gasto_manual(
    db: Session,
    *,
    campanha: Campanha,
    loja_slug: str,
    valor: Decimal,
    referencia: date,
    nota: str | None,
    criada_por: str,
) -> CampanhaGasto:
    """Mantém um total diário por campanha, com o manual prevalecendo sobre a API."""
    if campanha.loja_slug != loja_slug:
        raise ValueError("campanha não pertence à loja")

    existentes = (
        db.query(CampanhaGasto)
        .filter(
            CampanhaGasto.campanha_id == campanha.id,
            CampanhaGasto.loja_slug == loja_slug,
            CampanhaGasto.referencia == referencia,
        )
        .order_by(CampanhaGasto.criada_em.asc())
        .all()
    )
    manual = next((g for g in existentes if g.origem == "manual"), None)
    if manual is None:
        manual = CampanhaGasto(
            id=novo_id(),
            campanha_id=campanha.id,
            loja_slug=loja_slug,
            valor=valor,
            referencia=referencia,
            nota=nota,
            origem="manual",
            criada_por=criada_por,
        )
        db.add(manual)
    else:
        manual.valor = valor
        manual.nota = nota
        manual.criada_por = criada_por

    # Um lançamento manual é a fonte da verdade daquele dia. Remove tanto o
    # registro automático anterior quanto duplicatas manuais legadas.
    for gasto in existentes:
        if gasto is not manual:
            db.delete(gasto)
    return manual


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
    """modo: 'first' | 'last'. UTM, meta_campaign_id (CTWA) ou codigo_ctwa."""
    assert modo in ("first", "last")
    if modo == "first":
        camp_key = normalizar_utm(
            lead.get("utm_campaign_first") or lead.get("utm_campaign")
        )
        content_key = normalizar_utm(
            lead.get("utm_content_first") or lead.get("utm_content")
        )
        meta_id = (
            lead.get("meta_campaign_id_first") or lead.get("meta_campaign_id") or ""
        )
        codigo = normalizar_utm(
            lead.get("ctwa_codigo_first")
            or lead.get("ctwa_codigo")
            or lead.get("utm_campaign_first")
            or lead.get("utm_campaign")
        )
    else:
        camp_key = normalizar_utm(
            lead.get("utm_campaign_last") or lead.get("utm_campaign")
        )
        content_key = normalizar_utm(
            lead.get("utm_content_last") or lead.get("utm_content")
        )
        meta_id = lead.get("meta_campaign_id_last") or lead.get("meta_campaign_id") or ""
        codigo = normalizar_utm(
            lead.get("ctwa_codigo")
            or lead.get("ctwa_codigo_last")
            or lead.get("utm_campaign_last")
            or lead.get("utm_campaign")
        )

    # 1) UTM clássico (catálogo)
    if camp_key and camp_key == normalizar_utm(campanha.utm_campaign):
        if campanha.utm_content:
            if content_key != normalizar_utm(campanha.utm_content):
                return False
        return True

    # 2) ID de campanha Meta (CTWA / Ads)
    from app.meta_ads_spend import normalizar_meta_campaign_id

    camp_meta = normalizar_meta_campaign_id(getattr(campanha, "meta_campaign_id", None))
    lead_meta = normalizar_meta_campaign_id(str(meta_id) if meta_id else None)
    if camp_meta and lead_meta and camp_meta == lead_meta:
        return True

    # 3) Código CTWA na mensagem pré-preenchida
    camp_cod = normalizar_utm(getattr(campanha, "codigo_ctwa", None))
    if camp_cod and codigo and camp_cod == codigo:
        return True

    # 4) ad_id manual (Fase 1): muitos anúncios → 1 campanha
    ad_ids_camp = {
        normalizar_meta_campaign_id(getattr(a, "ad_id", None))
        for a in getattr(campanha, "anuncios", [])
    }
    ad_ids_camp.discard(None)
    lead_ad = normalizar_meta_campaign_id(
        (lead.get("meta_ad_id_first") if modo == "first" else lead.get("meta_ad_id"))
        or lead.get("meta_ad_id")
    )
    if ad_ids_camp and lead_ad and lead_ad in ad_ids_camp:
        return True

    return False


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
        "meta_campaign_id",
        "codigo_ctwa",
        "periodo_inicio",
        "periodo_fim",
        "notas",
    )
    return {c: (form.get(c) or "").strip() for c in campos}


def preencher_campanha(campanha: Campanha, dados: dict, *, email: str | None = None) -> None:
    from app.meta_ads_spend import normalizar_meta_campaign_id

    campanha.nome = dados["nome"].strip()
    campanha.canal = dados["canal"].strip().casefold()
    campanha.status = (dados.get("status") or "ativa").strip().casefold()
    campanha.utm_source = (dados.get("utm_source") or "").strip() or None
    campanha.utm_medium = (dados.get("utm_medium") or "").strip() or None
    campanha.utm_campaign = (dados.get("utm_campaign") or "").strip()
    campanha.utm_campaign_norm = normalizar_utm(campanha.utm_campaign) or ""
    campanha.utm_content = (dados.get("utm_content") or "").strip() or None
    campanha.utm_term = (dados.get("utm_term") or "").strip() or None
    campanha.meta_campaign_id = normalizar_meta_campaign_id(dados.get("meta_campaign_id"))
    cod = (dados.get("codigo_ctwa") or "").strip()
    campanha.codigo_ctwa = cod[:40] if cod else None
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
