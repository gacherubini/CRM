"""API v1 serviço: resultados de mídia e eventos de venda."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.clients.chatbot import ChatbotClient, ChatbotIndisponivel
from app.config import settings
from app.db import get_db
from app.financeiro_calc import calcular_metricas_vendas, hoje_portal, periodo_padrao
from app.meta_capi import enfileirar_purchase
from app.meta_capi_messaging import enfileirar_purchase_messaging
from app.models import Campanha, CampanhaGasto, MetaCapiOutbox, agora, novo_id
from app.resultados import resumo_periodo
from app.roi_calc import calcular_roi_loja, totais_roi
from app.service_auth import exigir_service_token
import json

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


def get_chatbot() -> ChatbotClient:
    return ChatbotClient(
        settings.chatbot_url,
        settings.chatbot_token,
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
        leads = get_chatbot().listar_leads()
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


class VendaConfirmadaBody(BaseModel):
    venda_id: str
    lead_ref: str | None = None
    valor: str | float | Decimal
    moeda: str = "BRL"
    event_id: str | None = None
    cliente_telefone: str | None = None
    cliente_email: str | None = None
    fbclid: str | None = None
    fbc: str | None = None
    ctwa_clid: str | None = None
    campanha_id_first: str | None = None
    campanha_id_last: str | None = None


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

    event_id = (body.event_id or f"purchase-{body.venda_id}").strip()
    ctwa = (body.ctwa_clid or "").strip()
    # O caminho messaging grava a outbox com sufixo "-msg": a idempotência tem
    # que conferir exatamente o event_id que este caminho vai gravar, senão o
    # reenvio de uma venda CTWA já enfileirada devolve idempotent=False.
    if ctwa and not event_id.endswith("-msg"):
        event_id_efetivo = f"{event_id}-msg"
    else:
        event_id_efetivo = event_id

    # O marcador de "sem config CAPI" é sempre gravado com o event_id puro
    # (serve aos dois caminhos), então a busca considera os dois ids: o do
    # caminho atual e o puro.
    ids_possiveis = [event_id_efetivo]
    if event_id not in ids_possiveis:
        ids_possiveis.append(event_id)
    linhas = (
        db.query(MetaCapiOutbox)
        .filter(MetaCapiOutbox.event_id.in_(ids_possiveis))
        .all()
    )
    por_id = {linha.event_id: linha for linha in linhas}
    # Só conta como "já enviado" quem virou evento de verdade; um marcador
    # "skipped" significa que o Purchase nunca chegou ao Meta.
    for candidato in ids_possiveis:
        linha = por_id.get(candidato)
        if linha is not None and linha.status != "skipped":
            return {"ok": True, "outbox_id": linha.id, "idempotent": True}

    marcadores = [linha for linha in linhas if linha.status == "skipped"]
    # Se a loja configurou o Pixel/CAPI depois, o reenvio tem que enfileirar de
    # verdade. Removemos o marcador para não bloquear a dedupe interna do
    # enfileirar (event_id é único) — se continuar sem config, é regravado abaixo.
    marcador_id = marcadores[0].id if marcadores else None
    if marcadores:
        for marcador in marcadores:
            db.delete(marcador)
        db.commit()

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
        )
    # Continua sem config CAPI: regrava o marcador skipped (event_id puro, comum
    # aos dois caminhos) para não perder o rastro da venda.
    if outbox is None:
        outbox = MetaCapiOutbox(
            id=marcador_id or novo_id(),
            loja_slug=slug,
            venda_id=body.venda_id,
            event_id=event_id,
            event_name="Purchase",
            payload_json=json.dumps({"skipped": True, "reason": "sem_config_capi"}),
            status="skipped",
            attempts=0,
            criada_em=agora(),
            atualizada_em=agora(),
        )
        db.add(outbox)
        db.commit()
        # Nada mudou desde a chamada anterior: segue idempotente para o caller.
        return {
            "ok": True,
            "outbox_id": outbox.id,
            "idempotent": marcador_id is not None,
        }
    db.commit()
    return {
        "ok": True,
        "outbox_id": outbox.id,
        "idempotent": False,
    }
