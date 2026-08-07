from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.config import settings as app_settings
from app.db import SessionLocal
from app.models import Loja, VendaProjetada
from app.web import control as control_mod
from app.web import control_ui as control_ui_mod


def _enable(monkeypatch):
    patched = replace(
        app_settings,
        revy_control_enabled=True,
        revy_control_dashboard_enabled=True,
        revy_control_rbac_enabled=False,
    )
    monkeypatch.setattr(control_mod, "settings", patched)
    monkeypatch.setattr(control_ui_mod, "settings", patched)


class _FakeLeadsPort:
    def count_for_store(self, slug):
        return 8


class _FakeLeadsIndisponivel:
    def count_for_store(self, slug):
        return None


def _seed_venda(monkeypatch, leads_port_cls):
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        viva = Loja(nome="Loja Viva", slug="loja-viva", status="ativa")
        db.add(viva)
        db.flush()
        db.add(
            VendaProjetada(
                id="v1", loja_slug="loja-viva", loja_id=viva.id,
                preco_venda=Decimal("30000.00"), status="confirmada",
                criada_em=agora, confirmada_em=agora, atualizada_em=agora,
            )
        )
        db.commit()
    monkeypatch.setattr(control_ui_mod, "_ChatbotLeadsPort", leads_port_cls)


def test_dashboard_mostra_kpis_de_negocio(client, monkeypatch):
    _enable(monkeypatch)
    _seed_venda(monkeypatch, _FakeLeadsPort)
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    r = client.get("/app/control/dashboard")

    assert r.status_code == 200
    assert "Vendas no mês" in r.text
    assert "Leads na rede" in r.text
    assert "Desempenho por loja" in r.text
    assert "Loja Viva" in r.text


def test_dashboard_leads_indisponivel_nao_inventa_zero(client, monkeypatch):
    _enable(monkeypatch)
    _seed_venda(monkeypatch, _FakeLeadsIndisponivel)
    client.post("/login", data={"email": "trafego@revy.local", "senha": "secret-teste"},
                follow_redirects=False)

    r = client.get("/app/control/dashboard")

    assert r.status_code == 200
    assert "indisponível" in r.text.lower()
