from datetime import datetime, timezone

from conftest import login

from app.db import SessionLocal
from app.models import FunilEvento


def adicionar_evento(
    lead_ref: str,
    tipo: str,
    ocorrido_em: str,
    *,
    loja_slug: str = "loja-teste",
) -> None:
    db = SessionLocal()
    db.add(
        FunilEvento(
            loja_slug=loja_slug,
            lead_ref=lead_ref,
            tipo=tipo,
            ocorrido_em=datetime.fromisoformat(ocorrido_em).astimezone(timezone.utc),
            idempotency_key=f"teste:{loja_slug}:{lead_ref}:{tipo}",
        )
    )
    db.commit()
    db.close()


def test_funil_ui_exige_login_e_restringe_vendedor(client):
    anonimo = client.get("/app/funil", follow_redirects=False)
    assert anonimo.status_code == 303
    assert anonimo.headers["location"] == "/login"

    login(client, papel="vendedor", email="vendedor-funil@loja.test")
    vendedor = client.get("/app/funil", follow_redirects=False)
    assert vendedor.status_code == 303
    assert vendedor.headers["location"] == "/app"


def test_funil_ui_nao_expoe_painel_comercial_ao_admin_plataforma(client):
    login(client, papel="admin_plataforma", email="admin-funil@revy.test")

    resposta = client.get("/app/funil", follow_redirects=False)
    dados = client.get("/app/funil/dados", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"
    assert dados.status_code == 303
    assert dados.headers["location"] == "/app"


def test_funil_ui_permite_gerente_e_mostra_estado_vazio(client):
    login(client, papel="gerente", email="gerente-funil@loja.test")

    resposta = client.get(
        "/app/funil",
        params={"inicio": "2026-07-01", "fim": "2026-07-31"},
    )

    assert resposta.status_code == 200
    assert "Funil comercial" in resposta.text
    assert 'href="/app/funil" aria-current="page"' in resposta.text
    assert "Nenhum lead criado neste período" in resposta.text
    assert resposta.text.count("Sem base") >= 6
    assert "0%" not in resposta.text


def test_funil_ui_calcula_taxas_e_tempos_com_timestamps_fixos(client):
    adicionar_evento("lead-a", "lead_criado", "2026-07-10T12:00:00+00:00")
    adicionar_evento("lead-a", "primeira_resposta", "2026-07-10T12:03:00+00:00")
    adicionar_evento("lead-a", "venda_confirmada", "2026-07-10T14:00:00+00:00")
    adicionar_evento("lead-b", "lead_criado", "2026-07-10T13:00:00+00:00")
    adicionar_evento("lead-b", "primeira_resposta", "2026-07-10T13:09:00+00:00")
    login(client)

    resposta = client.get(
        "/app/funil",
        params={"inicio": "2026-07-10", "fim": "2026-07-10"},
    )

    assert resposta.status_code == 200
    assert "2 de 2 leads" in resposta.text
    assert "1 de 2 leads" in resposta.text
    assert "100%" in resposta.text
    assert "50%" in resposta.text
    assert resposta.text.count("6 min") == 2
    assert resposta.text.count("2 h") == 2


def test_funil_ui_isola_eventos_de_outra_loja(client):
    adicionar_evento("lead-local", "lead_criado", "2026-07-10T12:00:00+00:00")
    for indice in range(4):
        lead = f"lead-outra-{indice}"
        adicionar_evento(
            lead,
            "lead_criado",
            "2026-07-10T12:00:00+00:00",
            loja_slug="outra-loja",
        )
        adicionar_evento(
            lead,
            "primeira_resposta",
            "2026-07-10T12:01:00+00:00",
            loja_slug="outra-loja",
        )
    login(client)

    resposta = client.get(
        "/app/funil",
        params={"inicio": "2026-07-10", "fim": "2026-07-10"},
    )

    assert resposta.status_code == 200
    assert "0 de 1 leads" in resposta.text
    assert "0%" in resposta.text
    assert "4 de 4 leads" not in resposta.text
    assert "lead-outra" not in resposta.text


def test_funil_ui_mantem_eventos_locais_se_chatbot_falhar(client, chatbot_fake):
    adicionar_evento("lead-local", "lead_criado", "2026-07-10T12:00:00+00:00")
    chatbot_fake.indisponivel = True
    login(client)

    resposta = client.get(
        "/app/funil",
        params={"inicio": "2026-07-10", "fim": "2026-07-10"},
    )

    assert resposta.status_code == 200
    assert "O Chatbot não respondeu agora" in resposta.text
    assert "Os eventos locais já registrados continuam exibidos" in resposta.text
    assert "criados no período selecionado" in resposta.text
    assert "Não foi possível acessar o chatbot agora" not in resposta.text
