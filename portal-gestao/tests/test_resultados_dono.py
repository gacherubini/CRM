from datetime import date, datetime, timezone
from decimal import Decimal

from conftest import csrf_da_resposta, login
from app.db import SessionLocal
from app.models import Campanha, CampanhaGasto, Venda, novo_id
from app.roi_calc import calcular_roi_loja
from app.resultados_dono import alertas_trafego, checklist_medicao, resumo_periodo


def _dados():
    campanha = Campanha(
        id=novo_id(), loja_slug="loja-teste", nome="Meta campeã", canal="meta", status="ativa",
        utm_campaign="meta-campea", utm_campaign_norm="meta-campea",
        criada_por_email="dono@loja.test",
    )
    gasto = CampanhaGasto(
        campanha_id=campanha.id, loja_slug="loja-teste", valor=Decimal("1000"),
        referencia=date(2026, 7, 20), criada_por="dono@loja.test",
    )
    venda = Venda(
        id=novo_id(), loja_slug="loja-teste", lead_ref="lead-1", vendedor_email="v@loja.test",
        descricao="Moto", preco_venda=Decimal("10000"), status="confirmada",
        campanha_id_last=campanha.id, criada_em=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    return campanha, gasto, venda


def test_resumo_alertas_e_checklist_puros():
    campanha, gasto, venda = _dados()
    linhas = calcular_roi_loja(
        campanhas=[campanha], gastos=[gasto], leads=[], vendas_confirmadas=[venda],
        d_inicio=date(2026, 7, 14), d_fim=date(2026, 7, 21),
    )
    resumo = resumo_periodo(linhas)
    assert resumo["totais"]["gasto"] == Decimal("1000.00")
    assert resumo["totais"]["vendas"] == 1
    assert resumo["totais"]["roas"] == Decimal("10.00")
    alertas = alertas_trafego(linhas=linhas, config=None, ultimo_outbox=None)
    assert alertas[0].codigo == "pixel_nao_config"
    checklist = checklist_medicao(
        config=None, campanhas=[campanha], gastos=[gasto], vendas=[venda], outboxes=[]
    )
    assert checklist["concluidos"] == 3
    assert checklist["total"] == 5


def test_dashboard_resultados_somente_dono_gerente(client, chatbot_fake):
    login(client)
    pagina = client.get("/app")
    assert "Resultados do tráfego" in pagina.text
    # Com PORTAL_TRAFEGO_UI_LEGACY=1 (conftest) o checklist técnico ainda aparece.
    assert "Medindo de verdade" in pagina.text


def test_dashboard_vendedor_nao_expoe_gasto_ou_roas(client):
    login(client, papel="vendedor")
    pagina = client.get("/app")
    assert "Resultados do tráfego" not in pagina.text
    assert "ROAS" not in pagina.text


def test_dono_pode_dispensar_checklist_medicao(client):
    login(client)
    pagina = client.get("/app")
    assert "Medindo de verdade" in pagina.text
    resposta = client.post(
        "/app/trafego/onboarding/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "Medindo de verdade" not in client.get("/app").text


def test_slim_portal_sem_menus_tecnicos_de_trafego(client, monkeypatch):
    """Produção (sem LEGACY): dono vê resultados, sem Tráfego/Campanhas na nav."""
    monkeypatch.delenv("PORTAL_TRAFEGO_UI_LEGACY", raising=False)
    monkeypatch.setenv("PORTAL_TRAFEGO_UI_LEGACY", "0")
    login(client)
    pagina = client.get("/app")
    assert "Resultados do tráfego" in pagina.text
    assert 'href="/app/trafego"' not in pagina.text
    assert 'href="/app/campanhas"' not in pagina.text
    assert "Medindo de verdade" not in pagina.text
    r = client.get("/app/trafego", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
