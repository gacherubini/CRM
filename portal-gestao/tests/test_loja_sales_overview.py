"""Fase 3 — SalesOverview (Vendas Visão geral)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from conftest import login
from app.config import settings
from app.db import SessionLocal
from app.financeiro_calc import calcular_metricas_vendas, periodo_padrao
from app.loja.sales_overview import (
    aquisicao_sem_investimento,
    build_sales_overview,
    _aquisicao_de_totais,
)
from app.models import Campanha, CampanhaGasto, Venda, novo_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    # Settings é frozen dataclass instanciado no import — recria atributo.
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _disable_shell(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    object.__setattr__(settings, "revy_loja_shell_enabled", False)


def _criar_venda(
    *,
    preco="50000",
    custo="40000",
    status="confirmada",
    loja_slug="loja-teste",
    vendedor="dono@loja.test",
    criada_em=None,
):
    db = SessionLocal()
    venda = Venda(
        loja_slug=loja_slug,
        vendedor_email=vendedor,
        descricao="Venda teste overview",
        preco_venda=Decimal(preco),
        custo_veiculo=Decimal(custo) if custo is not None else None,
        status=status,
        criada_em=criada_em or datetime.now(timezone.utc),
    )
    db.add(venda)
    db.commit()
    vid = venda.id
    db.close()
    return vid


class ChatbotStub:
    def __init__(self, leads=None, indisponivel=False):
        self.leads = leads if leads is not None else []
        self.indisponivel = indisponivel

    def listar_leads(self, etapa=None):
        if self.indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel

            raise ChatbotIndisponivel("chatbot offline")
        itens = self.leads
        if etapa:
            itens = [l for l in itens if l.get("etapa") == etapa]
        return itens


# ---------------------------------------------------------------------------
# Domain: KPIs, ROAS, aquisição parcial
# ---------------------------------------------------------------------------


def test_kpi_consistencia_com_financeiro_calc():
    """Receita e qtd batem com calcular_metricas_vendas no mesmo período."""
    _criar_venda(preco="50000", custo="40000")
    _criar_venda(preco="30000", custo="20000")
    d_inicio, d_fim = periodo_padrao(None, None)
    db = SessionLocal()
    try:
        esperado = calcular_metricas_vendas(db, "loja-teste", d_inicio, d_fim)
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            revy_trafego_resultados_enabled=False,
        )
        assert overview.qtd_vendas == esperado["quantidade"] == 2
        assert overview.receita == esperado["faturamento"] == Decimal("80000")
        assert overview.margem == esperado["lucro_bruto"] == Decimal("20000")
        assert overview.vendas_status == "ok"
        assert overview.margem_completa is True
    finally:
        db.close()


def test_roas_sem_investimento_indisponivel():
    """ROAS sem gasto → indisponível; nunca infinito nem zero inventado."""
    aq = aquisicao_sem_investimento(faturamento=Decimal("10000"), gasto=None)
    assert aq.roas_disponivel is False
    assert aq.roas is None
    assert aq.investimento_disponivel is False
    assert aq.investimento is None
    assert aq.status == "indisponivel"

    aq0 = aquisicao_sem_investimento(faturamento=Decimal("10000"), gasto=Decimal("0"))
    assert aq0.roas_disponivel is False
    assert aq0.roas is None
    assert aq0.investimento_disponivel is False
    assert aq0.investimento is None

    # Com gasto real, ROAS calculável
    aq_ok = _aquisicao_de_totais(
        {
            "gasto": Decimal("1000"),
            "faturamento": Decimal("5000"),
            "leads": 10,
            "vendas": 2,
            "cpa": Decimal("500"),
            "roas": Decimal("5.00"),
        },
        fonte="local",
    )
    assert aq_ok.roas_disponivel is True
    assert aq_ok.roas == Decimal("5.00")
    assert aq_ok.investimento_disponivel is True
    assert aq_ok.investimento == Decimal("1000")
    assert aq_ok.google_status == "indisponivel"


def test_falha_control_aquisicao_parcial_vendas_ok():
    """API de aquisição falha → aquisicao parcial; vendas permanecem ok."""
    _criar_venda(preco="10000", custo="7000")
    d_inicio, d_fim = periodo_padrao(None, None)
    db = SessionLocal()
    try:
        # Campanha local com gasto para fallback; simulamos flag API ligada + fetch None
        camp = Campanha(
            id=novo_id(),
            loja_slug="loja-teste",
            nome="Meta teste",
            canal="meta",
            status="ativa",
            utm_campaign="meta-teste",
            utm_campaign_norm="meta-teste",
            criada_por_email="dono@loja.test",
        )
        db.add(camp)
        db.add(
            CampanhaGasto(
                campanha_id=camp.id,
                loja_slug="loja-teste",
                valor=Decimal("500"),
                referencia=d_inicio,
                criada_por="dono@loja.test",
            )
        )
        db.commit()

        def fetch_falha(**kwargs):
            return None

        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            fetch_resultados_api=fetch_falha,
            revy_trafego_resultados_enabled=True,
        )
        assert overview.qtd_vendas == 1
        assert overview.receita == Decimal("10000.00") or overview.receita == Decimal("10000")
        assert overview.vendas_status == "ok"
        # API falhou mas há fallback local → parcial (api_falhou=True)
        assert overview.aquisicao_status in {"parcial", "ok"}
        assert overview.aquisicao is not None
        if overview.aquisicao_status == "parcial":
            assert overview.status in {"parcial", "ok"}
        # Google nunca vira zero
        assert overview.aquisicao.google_status == "indisponivel"
    finally:
        db.close()


def test_falha_control_sem_campanhas_locais_parcial():
    """Flag API on + fetch None + sem campanhas → aquisição parcial, vendas ok."""
    _criar_venda(preco="12000", custo="9000")
    d_inicio, d_fim = periodo_padrao(None, None)
    db = SessionLocal()
    try:

        def fetch_falha(**kwargs):
            return None

        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            fetch_resultados_api=fetch_falha,
            revy_trafego_resultados_enabled=True,
        )
        assert overview.qtd_vendas == 1
        assert overview.vendas_status == "ok"
        assert overview.aquisicao_status == "parcial"
        assert overview.aquisicao is not None
        assert overview.aquisicao.investimento is None
        assert overview.aquisicao.roas is None
        assert overview.aquisicao.google_status == "indisponivel"
        assert overview.status in {"parcial", "ok"}
    finally:
        db.close()


def test_aquisicao_consulta_api_com_a_janela_escolhida():
    """ROAS tem que dividir receita e gasto da MESMA janela.

    Antes a chamada ia com periodo="mes" fixo: filtrar 7 dias devolvia vendas de
    7 dias sobre gasto do mes inteiro.
    """
    _criar_venda(preco="10000", custo="8000")
    d_inicio = date(2026, 7, 10)
    d_fim = date(2026, 7, 16)
    capturado: dict = {}

    def fetch_espiao(**kwargs):
        capturado.update(kwargs)
        return None

    db = SessionLocal()
    try:
        build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            fetch_resultados_api=fetch_espiao,
            revy_trafego_resultados_enabled=True,
        )
        assert capturado.get("inicio") == d_inicio.isoformat()
        assert capturado.get("fim") == d_fim.isoformat()
    finally:
        db.close()


def test_vendedor_so_proprias_metricas():
    _criar_venda(preco="50000", custo="40000", vendedor="vendedor@loja.test")
    _criar_venda(preco="30000", custo="20000", vendedor="outro@loja.test")
    d_inicio, d_fim = periodo_padrao(None, None)
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="vendedor",
            vendedor_email="vendedor@loja.test",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            revy_trafego_resultados_enabled=False,
            pode_ver_margem=False,
        )
        assert overview.escopo == "vendedor"
        assert overview.qtd_vendas == 1
        assert overview.receita == Decimal("50000")
        assert overview.margem is None  # vendedor sem custo
        assert overview.aquisicao is None
        assert overview.aquisicao_status == "indisponivel"
    finally:
        db.close()


def test_papel_nao_autorizado_retorna_erro():
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="financeiro_externo",
        )
        assert overview.status == "erro"
    finally:
        db.close()


def test_estado_vazio_sem_vendas():
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            chatbot=ChatbotStub(),
            revy_trafego_resultados_enabled=False,
        )
        assert overview.qtd_vendas == 0
        assert overview.vendas_status == "vazio"
        assert overview.receita == Decimal("0") or overview.receita == Decimal("0.00")
    finally:
        db.close()


def test_overview_nao_calcula_mais_metas_nem_pendencias():
    """Os dois blocos saíram da tela Resultado em 2026-08-16 (decisão do dono).

    O read model não pode continuar calculando o que ninguém exibe: metas
    seguem em /app/metas e no painel financeiro legado.
    """
    _criar_venda(preco="10000", custo=None, status="registrada")
    d_inicio, d_fim = periodo_padrao(None, None)
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(leads=[{"id": "x", "etapa": "novo", "telefone": "5511999"}]),
            revy_trafego_resultados_enabled=False,
        )
        assert not hasattr(overview, "metas")
        assert not hasattr(overview, "metas_status")
        assert not hasattr(overview, "pendencias")
        serializado = overview.to_dict()
        assert "metas" not in serializado
        assert "pendencias" not in serializado
    finally:
        db.close()


def test_to_dict_serializa_decimals():
    _criar_venda(preco="1000", custo="500")
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            chatbot=ChatbotStub(),
            revy_trafego_resultados_enabled=False,
        )
        payload = overview.to_dict()
        assert payload["qtd_vendas"] == 1
        assert isinstance(payload["receita"], str)
        assert payload["aquisicao_status"] in {"ok", "parcial", "indisponivel", "vazio"}
    finally:
        db.close()


def test_funil_usa_contagem_viva_quando_projecao_local_vazia():
    """Bug (moto-center): a projeção local FunilEvento não foi materializada,
    mas o Chatbot tem leads no período. O funil reportava total_leads=0 (a
    projeção vazia) em vez da contagem viva — o Copiloto então dizia "0 leads"
    com centenas de leads reais. Deve cair na contagem auditável (elegiveis),
    a mesma fonte de "Por onde as pessoas chegam"."""
    d_inicio, d_fim = date(2026, 8, 1), date(2026, 8, 31)
    leads = [
        {"id": "l1", "criada_em": "2026-08-05T12:00:00+00:00"},
        {"id": "l2", "criada_em": "2026-08-06T12:00:00+00:00"},
        {"id": "l3", "criada_em": "2026-08-07T12:00:00+00:00"},
    ]
    db = SessionLocal()
    try:
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(leads=leads),
            revy_trafego_resultados_enabled=False,
        )
        # FunilEvento não foi semeada → projeção local = 0; há 3 leads vivos.
        assert overview.funil is not None
        assert overview.funil["total_leads"] == 3
        # Nunca "vazio" quando há leads vivos (o prompt trataria como zero real).
        assert overview.funil_status in {"ok", "parcial"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_rota_404_quando_shell_off(client, monkeypatch):
    _disable_shell(monkeypatch)
    login(client)
    r = client.get("/app/loja/vendas")
    assert r.status_code == 404
    r2 = client.get("/app/loja/vendas/dados")
    assert r2.status_code == 404


def test_rota_html_dono_quando_shell_on(client, monkeypatch, chatbot_fake):
    _enable_shell(monkeypatch)
    _criar_venda(preco="50000", custo="40000")
    login(client)
    r = client.get("/app/loja/vendas")
    assert r.status_code == 200
    # "Visão geral" virou "Resultado" (havia dois itens de menu homônimos).
    assert "Resultado" in r.text
    # O rodapé "Atalhos" apontava para as telas legadas que o shell substitui.
    assert "Painel clássico" not in r.text
    assert "Receita" in r.text
    assert "50.000,00" in r.text or "50000" in r.text
    # Linguagem comercial — sem UI técnica
    assert "OAuth" not in r.text
    assert "Pixel" not in r.text
    assert "webhook" not in r.text.lower()
    assert "Google Ads" in r.text
    assert "indisponível" in r.text.casefold()


def test_rota_json_dados(client, monkeypatch, chatbot_fake):
    _enable_shell(monkeypatch)
    _criar_venda(preco="15000", custo="10000")
    login(client)
    r = client.get("/app/loja/vendas/dados")
    assert r.status_code == 200
    body = r.json()
    assert body["qtd_vendas"] == 1
    assert body["escopo"] == "loja"
    assert "receita" in body
    assert body["aquisicao"] is None or body["aquisicao"]["google_status"] == "indisponivel"


def test_vendedor_acessa_proprias_metricas(client, monkeypatch, chatbot_fake):
    _enable_shell(monkeypatch)
    _criar_venda(preco="20000", custo="15000", vendedor="vendedor@loja.test")
    _criar_venda(preco="90000", custo="80000", vendedor="dono@loja.test")
    login(client, papel="vendedor")
    r = client.get("/app/loja/vendas/dados")
    assert r.status_code == 200
    body = r.json()
    assert body["escopo"] == "vendedor"
    assert body["qtd_vendas"] == 1
    assert body["aquisicao"] is None


def test_legado_app_continua(client, monkeypatch):
    """Flag da Loja não quebra o dashboard clássico."""
    _enable_shell(monkeypatch)
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
