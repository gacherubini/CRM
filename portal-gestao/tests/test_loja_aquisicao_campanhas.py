"""Detalhe de aquisicao na Revy Loja: por campanha e por canal.

A API /v1/lojas/{slug}/resultados ja devolvia `campanhas`, `canais` e `melhor`;
o read model da Loja pegava so `totais` e jogava o resto fora, deixando o dono
sem saber de qual anuncio veio o resultado.
"""
from __future__ import annotations

from decimal import Decimal

from conftest import login

from app.db import SessionLocal
from app.financeiro_calc import periodo_padrao
from app.loja.sales_overview import build_sales_overview

from test_loja_sales_overview import ChatbotStub  # noqa: E402


def _payload_api():
    return {
        "periodo": {"chatbot_offline": False},
        "totais": {
            "gasto": "500.00",
            "leads": 10,
            "vendas": 2,
            "faturamento": "60000.00",
            "cpl": "50.00",
            "cpa": "250.00",
            "roas": "120.00",
        },
        "campanhas": [
            {
                "id": "camp-1",
                "nome": "Civic — julho",
                "canal": "meta",
                "utm_campaign": "civic-julho",
                "gasto": "300.00",
                "leads": 7,
                "vendas": 2,
                "faturamento": "60000.00",
                "cpl": "42.86",
                "cpa": "150.00",
                "roas": "200.00",
            },
            {
                "id": "camp-2",
                "nome": "Onix — julho",
                "canal": "meta",
                "utm_campaign": "onix-julho",
                "gasto": "200.00",
                "leads": 3,
                "vendas": 0,
                "faturamento": "0.00",
                "cpl": "66.67",
                "cpa": None,
                "roas": None,
            },
        ],
        "canais": [
            {"canal": "meta", "gasto": "500.00", "vendas": 2, "faturamento": "60000.00"}
        ],
    }


def _overview_com_api(payload):
    db = SessionLocal()
    try:
        d_inicio, d_fim = periodo_padrao(None, None)
        return build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            fetch_resultados_api=lambda **kwargs: payload,
            revy_trafego_resultados_enabled=True,
        )
    finally:
        db.close()


def test_overview_expoe_campanhas_da_api():
    overview = _overview_com_api(_payload_api())

    nomes = [c["nome"] for c in overview.aquisicao_campanhas]
    assert nomes == ["Civic — julho", "Onix — julho"]
    primeira = overview.aquisicao_campanhas[0]
    assert primeira["gasto"] == Decimal("300.00")
    assert primeira["vendas"] == 2
    assert primeira["roas"] == Decimal("200.00")


def test_overview_expoe_canais_da_api():
    overview = _overview_com_api(_payload_api())

    assert [c["canal"] for c in overview.aquisicao_canais] == ["meta"]
    assert overview.aquisicao_canais[0]["gasto"] == Decimal("500.00")


def test_campanhas_ordenadas_por_gasto():
    payload = _payload_api()
    payload["campanhas"].reverse()

    overview = _overview_com_api(payload)

    assert [c["nome"] for c in overview.aquisicao_campanhas] == [
        "Civic — julho",
        "Onix — julho",
    ]


def test_sem_api_nao_inventa_campanhas():
    """Fallback local nao tem detalhe confiavel por campanha — melhor vazio."""
    db = SessionLocal()
    try:
        d_inicio, d_fim = periodo_padrao(None, None)
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="dono",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            revy_trafego_resultados_enabled=False,
        )
        assert overview.aquisicao_campanhas == []
        assert overview.aquisicao_canais == []
    finally:
        db.close()


def test_tela_de_resultado_renderiza_o_bloco_de_campanhas(client, monkeypatch):
    """Render real: o bloco só existe com campanhas, então nada mais o cobre."""
    from app.config import settings

    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)
    object.__setattr__(settings, "revy_trafego_resultados_enabled", True)
    monkeypatch.setattr(
        "app.web.loja_vendas._fetch_resultados_api",
        lambda: (lambda **kwargs: _payload_api()),
    )
    login(client)
    try:
        pagina = client.get("/app/loja/vendas")
    finally:
        object.__setattr__(settings, "revy_trafego_resultados_enabled", False)

    assert pagina.status_code == 200
    assert "De onde veio o resultado" in pagina.text
    assert "Civic — julho" in pagina.text


def test_vendedor_nao_recebe_detalhe_de_midia():
    """Custo de midia e leitura de dono/gerente (pode_ver_resultados_midia)."""
    db = SessionLocal()
    try:
        d_inicio, d_fim = periodo_padrao(None, None)
        overview = build_sales_overview(
            db,
            loja_slug="loja-teste",
            papel="vendedor",
            vendedor_email="vendedor@loja.test",
            inicio=d_inicio,
            fim=d_fim,
            chatbot=ChatbotStub(),
            fetch_resultados_api=lambda **kwargs: _payload_api(),
            revy_trafego_resultados_enabled=False,
        )
        assert overview.aquisicao_campanhas == []
    finally:
        db.close()
