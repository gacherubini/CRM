"""Ponta a ponta: o endpoint que a Loja consome conta a venda atribuida pelo lead.

A funcao pura ja tem teste em test_roi_heranca_lead.py. Aqui o que se prova e o
caminho inteiro in-process — Campanha + cache Graph + VendaProjetada + leads do
Chatbot — porque e o endpoint que alimenta a tabela de aquisicao da Loja.
"""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app import config as config_mod
from app.clients.chatbot import ChatbotClient
from app.db import SessionLocal
from app.models import Campanha, MetaAdCampanha, VendaProjetada, novo_id

AD_ID = "120249613359810224"
CAMPAIGN_ID = "120249613359800224"


def _token(valor: str = "tok-teste-svc"):
    config_mod.settings = replace(config_mod.settings, service_token=valor)
    return {"X-Service-Token": valor}


def _semear(db, *, com_cache: bool = True) -> str:
    agora = datetime.now(timezone.utc)
    campanha = Campanha(
        id=novo_id(),
        loja_slug="moto-center",
        nome="MT03 - CAUA VENDAS",
        canal="meta",
        status="ativa",
        utm_campaign="MT03AGOSTO",
        utm_campaign_norm="mt03agosto",
        meta_campaign_id=CAMPAIGN_ID,
        criada_por_email="dono@loja.test",
    )
    db.add(campanha)
    if com_cache:
        db.add(
            MetaAdCampanha(
                id=novo_id(),
                loja_slug="moto-center",
                ad_id=AD_ID,
                meta_campaign_id=CAMPAIGN_ID,
                meta_campaign_nome="MT03 - CAUA VENDAS",
                resolvido_em=agora,
            )
        )
    db.add(
        VendaProjetada(
            id=novo_id(),
            loja_slug="moto-center",
            lead_ref="lead-1",
            preco_venda=Decimal("32000.00"),
            custos_diretos_total=Decimal("0"),
            status="confirmada",
            campanha_id_last=None,
            campanha_id_first=None,
            utm_campaign_last=None,
            utm_campaign_first=None,
            criada_em=agora,
            confirmada_em=agora,
            atualizada_em=agora,
        )
    )
    db.commit()
    return campanha.id


def _leads_fake(monkeypatch, leads):
    monkeypatch.setattr(ChatbotClient, "listar_leads", lambda self, **kw: leads)


def test_resultados_conta_venda_atribuida_por_ad_id(client, monkeypatch):
    headers = _token()
    db = SessionLocal()
    try:
        campanha_id = _semear(db)
    finally:
        db.close()

    _leads_fake(
        monkeypatch,
        [
            {
                "id": "lead-1",
                "meta_ad_id": AD_ID,
                "criada_em": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    r = client.get("/v1/lojas/moto-center/resultados?periodo=7d", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["periodo"]["chatbot_offline"] is False

    linha = next(c for c in body["campanhas"] if c["id"] == campanha_id)
    assert linha["vendas"] == 1
    assert linha["faturamento"] == "32000.00"
    assert body["totais"]["vendas"] == 1
    assert body["totais"]["faturamento"] == "32000.00"


def test_resultados_sem_cache_graph_deixa_venda_sem_campanha(client, monkeypatch):
    """Sem o ad->campanha resolvido nao ha rota: a venda fica fora do atribuido."""
    headers = _token()
    db = SessionLocal()
    try:
        campanha_id = _semear(db, com_cache=False)
    finally:
        db.close()

    _leads_fake(
        monkeypatch,
        [
            {
                "id": "lead-1",
                "meta_ad_id": AD_ID,
                "criada_em": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    r = client.get("/v1/lojas/moto-center/resultados?periodo=7d", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    linha = next(c for c in body["campanhas"] if c["id"] == campanha_id)
    assert linha["vendas"] == 0
    assert body["totais"]["vendas"] == 0
