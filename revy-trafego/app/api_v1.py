"""API v1 serviço: resultados de mídia e eventos de venda."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel
from app.config import settings
from app.control.google_ads_conversions import (
    EVENT_VENDA_CONFIRMADA,
    EnqueueConversion,
    GoogleAdsConversionsControl,
)
from app.db import SessionLocal, get_db
from app.financeiro_calc import calcular_metricas_vendas, hoje_portal, periodo_padrao
from app.meta_capi import enfileirar_purchase
from app.meta_capi_messaging import enfileirar_purchase_messaging
from app.models import Campanha, CampanhaGasto, Loja, MetaCapiOutbox, agora
from app.resultados import resumo_periodo
from app.roi_calc import calcular_roi_loja, totais_roi
from app.service_auth import exigir_service_token
from app.vendas_projection import VendaSnapshot, projetar_venda
router = APIRouter(prefix="/v1", tags=["v1"])


def _dec_str(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return str(v.quantize(Decimal("0.01")))


def _periodo_query(
    periodo: str | None,
    inicio: str | None,
    fim: str | None,
) -> tuple[date, date, str]:
    chave = (periodo or "7d").strip().lower()
    hoje = hoje_portal()
    if inicio or fim:
        d_inicio, d_fim = periodo_padrao(inicio, fim)
        return d_inicio, d_fim, "custom"
    if chave == "mes":
        d_inicio = hoje.replace(day=1)
        return d_inicio, hoje, "mes"
    # default 7d (inclui hoje)
    d_inicio = hoje - timedelta(days=6)
    return d_inicio, hoje, "7d"


def _serializar_linha(linha) -> dict[str, Any]:
    return {
        "id": linha.campanha_id,
        "nome": linha.nome,
        "canal": linha.canal,
        "utm_campaign": linha.utm_campaign,
        "status": linha.status,
        "gasto": _dec_str(linha.gasto) or "0.00",
        "leads": linha.leads,
        "vendas": linha.vendas,
        "faturamento": _dec_str(linha.faturamento) or "0.00",
        "cpl": _dec_str(linha.cpl),
        "cpa": _dec_str(linha.cpa),
        "roas": _dec_str(linha.roas),
    }


def get_chatbot(loja_slug: str) -> ChatbotClient:
    return ChatbotClient(
        settings.chatbot_url,
        settings.chatbot_token_para(loja_slug),
        settings.request_timeout,
    )


@router.get("/lojas/{loja_slug}/resultados")
def api_resultados(
    loja_slug: str,
    periodo: str | None = "7d",
    inicio: str | None = None,
    fim: str | None = None,
    modo: str | None = "last",
    db: Session = Depends(get_db),
    _: None = Depends(exigir_service_token),
):
    slug = (loja_slug or "").strip()
    if not slug or len(slug) > 120:
        return JSONResponse({"detail": "loja_slug inválido"}, status_code=400)

    d_inicio, d_fim, chave = _periodo_query(periodo, inicio, fim)
    touch = modo if modo in ("first", "last") else "last"
    campanhas = db.query(Campanha).filter(Campanha.loja_slug == slug).all()
    gastos = db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == slug).all()
    metricas = calcular_metricas_vendas(db, slug, d_inicio, d_fim)
    leads: list[dict] = []
    chatbot_offline = False
    try:
        leads = get_chatbot(slug).listar_leads()
    except ChatbotIndisponivel:
        chatbot_offline = True

    linhas = calcular_roi_loja(
        campanhas=campanhas,
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=metricas["confirmadas"],
        d_inicio=d_inicio,
        d_fim=d_fim,
        modo_atribuicao=touch,
    )
    resumo = resumo_periodo(linhas)
    totais = totais_roi(linhas)
    melhor = resumo.get("melhor_campanha")
    campanhas_json = [
        _serializar_linha(l) for l in linhas if l.campanha_id is not None
    ]
    return {
        "loja_slug": slug,
        "periodo": {
            "chave": chave,
            "inicio": d_inicio.isoformat(),
            "fim": d_fim.isoformat(),
            "modo": touch,
            "chatbot_offline": chatbot_offline,
        },
        "totais": {
            "gasto": _dec_str(totais["gasto"]) or "0.00",
            "leads": totais["leads"],
            "vendas": totais["vendas"],
            "faturamento": _dec_str(totais["faturamento"]) or "0.00",
            "cpl": _dec_str(totais.get("cpl")),
            "cpa": _dec_str(totais.get("cpa")),
            "roas": _dec_str(totais.get("roas")),
        },
        "canais": [
            {
                "canal": c["canal"],
                "gasto": _dec_str(c["gasto"]) or "0.00",
                "vendas": c["vendas"],
                "faturamento": _dec_str(c["faturamento"]) or "0.00",
                "roas": _dec_str(c.get("roas")),
                "roas_barra_pct": c.get("roas_barra_pct", 0.0),
            }
            for c in resumo.get("canais") or []
        ],
        "melhor_campanha": (
            {
                "id": melhor.campanha_id,
                "nome": melhor.nome,
                "canal": melhor.canal,
                "gasto": _dec_str(melhor.gasto),
                "leads": melhor.leads,
                "vendas": melhor.vendas,
                "roas": _dec_str(melhor.roas),
            }
            if melhor is not None
            else None
        ),
        "campanhas": campanhas_json,
        "tem_campanhas": bool(resumo.get("tem_campanhas")),
        "vendas_sem_campanha": resumo.get("vendas_sem_campanha") or 0,
        "leads_sem_campanha": resumo.get("leads_sem_campanha") or 0,
    }


class VendaSnapshotBody(BaseModel):
    venda_id: str
    lead_ref: str | None = None
    valor: str | float | Decimal
    moeda: str = "BRL"
    status: str = "confirmada"
    criada_em: datetime | None = None
    confirmada_em: datetime | None = None
    atualizada_em: datetime | None = None
    custo_veiculo: str | float | Decimal | None = None
    custos_diretos_total: str | float | Decimal = Decimal("0")
    campanha_id_first: str | None = None
    campanha_id_last: str | None = None
    utm_campaign_first: str | None = None
    utm_campaign_last: str | None = None


class VendaConfirmadaBody(VendaSnapshotBody):
    event_id: str | None = None
    cliente_telefone: str | None = None
    cliente_email: str | None = None
    fbclid: str | None = None
    fbc: str | None = None
    # Click IDs Google (opacos, opcionais) — F4D usará para Data Manager.
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None
    consent_ad_user_data: bool = False
    ctwa_clid: str | None = None


def _snapshot(
    loja_slug: str,
    body: VendaSnapshotBody,
    *,
    status: str | None = None,
) -> VendaSnapshot:
    instante = body.atualizada_em or body.confirmada_em or datetime.now(timezone.utc)
    return VendaSnapshot(
        venda_id=body.venda_id,
        loja_slug=loja_slug,
        status=status or body.status,
        valor=Decimal(str(body.valor)),
        atualizada_em=instante,
        lead_ref=body.lead_ref,
        criada_em=body.criada_em,
        confirmada_em=body.confirmada_em,
        custo_veiculo=(
            Decimal(str(body.custo_veiculo))
            if body.custo_veiculo is not None
            else None
        ),
        custos_diretos_total=Decimal(str(body.custos_diretos_total or 0)),
        campanha_id_first=body.campanha_id_first,
        campanha_id_last=body.campanha_id_last,
        utm_campaign_first=body.utm_campaign_first,
        utm_campaign_last=body.utm_campaign_last,
    )


@router.post("/lojas/{loja_slug}/eventos/venda-atualizada")
def api_venda_atualizada(
    loja_slug: str,
    body: VendaSnapshotBody,
    db: Session = Depends(get_db),
    _: None = Depends(exigir_service_token),
):
    """Atualiza a projecao de ROI sem disparar efeitos externos."""
    slug = (loja_slug or "").strip()
    if not slug or body.status not in {"confirmada", "cancelada"}:
        return JSONResponse({"detail": "evento de venda invalido"}, status_code=400)
    resultado = projetar_venda(db, _snapshot(slug, body))
    if body.status == "cancelada":
        pendentes = (
            db.query(MetaCapiOutbox)
            .filter(
                MetaCapiOutbox.loja_slug == slug,
                MetaCapiOutbox.venda_id == body.venda_id,
                MetaCapiOutbox.status.in_(
                    ("pending", "failed", "blocked_config", "processing", "skipped")
                ),
            )
            .all()
        )
        for item in pendentes:
            item.status = "cancelled"
            item.last_error = "venda cancelada no Portal"
            item.atualizada_em = agora()
    db.commit()
    return {
        "ok": True,
        "venda_id": body.venda_id,
        "projecao": resultado.motivo,
    }


@router.post("/lojas/{loja_slug}/eventos/venda-confirmada")
def api_venda_confirmada(
    loja_slug: str,
    body: VendaConfirmadaBody,
    db: Session = Depends(get_db),
    _: None = Depends(exigir_service_token),
):
    """Enfileira Purchase CAPI (web e/ou messaging). Idempotente por event_id/venda_id."""
    slug = (loja_slug or "").strip()
    if not slug:
        return JSONResponse({"detail": "loja_slug inválido"}, status_code=400)

    projecao = projetar_venda(db, _snapshot(slug, body, status="confirmada"))
    db.commit()
    # Um cancelamento mais novo nao pode ser revertido por retry atrasado da
    # confirmacao, nem voltar a disparar Purchase.
    if not projecao.aplicada and projecao.venda.status != "confirmada":
        return {
            "ok": True,
            "outbox_id": None,
            "idempotent": True,
            "projecao": projecao.motivo,
        }

    event_id = (body.event_id or f"purchase-{body.venda_id}").strip()
    ctwa = (body.ctwa_clid or "").strip()
    # O caminho messaging grava a outbox com sufixo "-msg": a idempotência tem
    # que conferir exatamente o event_id que este caminho vai gravar, senão o
    # reenvio de uma venda CTWA já enfileirada devolve idempotent=False.
    if ctwa and not event_id.endswith("-msg"):
        event_id_efetivo = f"{event_id}-msg"
    else:
        event_id_efetivo = event_id

    ids_possiveis = [event_id_efetivo]
    linhas = (
        db.query(MetaCapiOutbox)
        .filter(
            MetaCapiOutbox.loja_slug == slug,
            MetaCapiOutbox.event_id.in_(ids_possiveis),
        )
        .all()
    )
    if linhas:
        linha = linhas[0]
        return {"ok": True, "outbox_id": linha.id, "idempotent": True}

    lead = {
        "telefone": body.cliente_telefone,
        "email": body.cliente_email,
        "fbclid": body.fbclid,
        "fbc": body.fbc,
    }
    outbox = None
    if ctwa:
        outbox = enfileirar_purchase_messaging(
            db,
            loja_slug=slug,
            venda_id=body.venda_id,
            event_id=event_id_efetivo,
            value=body.valor,
            currency=body.moeda or "BRL",
            ctwa_clid=ctwa,
            phone=body.cliente_telefone,
            email=body.cliente_email,
            event_time=body.confirmada_em,
        )
    else:
        outbox = enfileirar_purchase(
            db,
            loja_slug=slug,
            venda_id=body.venda_id,
            event_id=event_id_efetivo,
            value=body.valor,
            currency=body.moeda or "BRL",
            lead=lead,
            event_time=body.confirmada_em,
        )
    if outbox is None:
        return JSONResponse(
            {"detail": "nao foi possivel persistir o evento de venda"},
            status_code=503,
        )
    db.commit()

    # Hook lean Google Ads (fire-and-forget): não bloqueia nem reverte a venda.
    google_outbox_id = _maybe_enqueue_google_conversion(slug, body)

    return {
        "ok": True,
        "outbox_id": outbox.id,
        "idempotent": False,
        "google_ads_outbox_id": google_outbox_id,
    }


def _maybe_enqueue_google_conversion(
    loja_slug: str,
    body: VendaConfirmadaBody,
) -> str | None:
    if not settings.google_conversions_enabled:
        return None
    gclid = (body.gclid or "").strip() or None
    gbraid = (body.gbraid or "").strip() or None
    wbraid = (body.wbraid or "").strip() or None
    if not gclid and not gbraid and not wbraid:
        return None
    try:
        with SessionLocal() as session:
            loja = (
                session.query(Loja)
                .filter(Loja.slug == loja_slug.strip())
                .first()
            )
            if loja is None:
                return None
            loja_id = loja.id
        view = GoogleAdsConversionsControl(SessionLocal).enqueue_conversion(
            EnqueueConversion(
                loja_id=loja_id,
                event_type=EVENT_VENDA_CONFIRMADA,
                domain_event_id=(body.event_id or body.venda_id).strip(),
                gclid=gclid,
                gbraid=gbraid,
                wbraid=wbraid,
                value=body.valor,
                currency=body.moeda or "BRL",
                consent=bool(body.consent_ad_user_data),
                email=body.cliente_email,
                phone=body.cliente_telefone,
                conversion_time=body.confirmada_em,
            )
        )
        return view.id if view is not None else None
    except Exception:
        return None
