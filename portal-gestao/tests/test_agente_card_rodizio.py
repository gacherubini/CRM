from dataclasses import replace
from datetime import datetime, timedelta, timezone

from conftest import login

from app.config import settings as portal_settings
from app.main import app, get_chatbot_client

# "Atendidos" e "Perdidos" contam os últimos 7 dias. Com data fixa no corpo do
# teste, ele passa na semana em que foi escrito e reprova sozinho na seguinte —
# foi o que aconteceu: `2026-08-13` saiu da janela em 20/08 e o vermelho não
# tinha nada a ver com o código.
ONTEM = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


class _ChatbotAgente:
    def __init__(self, ofertas=None):
        self.ofertas = ofertas or []

    def resumo_atendimento(self, desde=None, ate=None):
        return {"atendimentos": 4, "transferidos": 1, "transferidos_pct": 0.25, "por_dia": []}

    def listar_ofertas(self, estado=None):
        if estado is None:
            return [o for o in self.ofertas if o["estado"] in ("aberta", "esgotada")]
        return [o for o in self.ofertas if o["estado"] == estado]


def _ligar(monkeypatch):
    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


def test_card_mostra_quatro_numeros(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, email="dono-card@loja.test")
    _override(_ChatbotAgente([
        {"id": "1", "estado": "aberta", "criado_em": ONTEM},
        {"id": "2", "estado": "esgotada", "criado_em": ONTEM},
        {"id": "3", "estado": "travada", "criado_em": ONTEM},
        {"id": "4", "estado": "expirada", "criado_em": ONTEM},
    ]))

    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "id=\"card-rodizio-7d\"" in r.text or 'id="card-rodizio-7d"' in r.text
    assert "Oferecidos" in r.text
    assert "Atendidos" in r.text
    assert "Aguardando" in r.text
    assert "Perdidos" in r.text


def test_aguardando_nao_e_perdidos(client, monkeypatch):
    """Spec §5.4: esgotou a fila ≠ morreu sem humano."""
    _ligar(monkeypatch)
    login(client, email="dono-dist@loja.test")
    _override(_ChatbotAgente([
        {"id": "e1", "estado": "esgotada", "criado_em": ONTEM},
        {"id": "e2", "estado": "esgotada", "criado_em": ONTEM},
        {"id": "x1", "estado": "expirada", "criado_em": ONTEM},
    ]))

    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    # 2 aguardando, 1 perdido — textos distintos no card
    assert "data-rodizio-aguardando=\"2\"" in r.text
    assert "data-rodizio-perdidos=\"1\"" in r.text


def test_modo1_sem_ofertas_esconde_o_card(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, email="dono-m1-card@loja.test")
    _override(_ChatbotAgente([]))

    r = client.get("/app/loja/agente")
    assert r.status_code == 200
    assert "card-rodizio-7d" not in r.text
