from conftest import login

from app.db import SessionLocal
from app.models import MetaPixelConfig


def test_configuracoes_exige_login(client):
    resposta = client.get("/app/configuracoes", follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_dono_ve_dados_status_e_todos_os_atalhos(client):
    login(client)

    resposta = client.get("/app/configuracoes")

    assert resposta.status_code == 200
    assert "Configuração da operação" in resposta.text
    assert "loja-teste" in resposta.text
    assert "Ana Loja" in resposta.text
    assert "dono@loja.test" in resposta.text
    assert "Estoque" in resposta.text
    assert "Chatbot" in resposta.text
    assert "Motor" in resposta.text
    assert "Meta / CAPI" in resposta.text
    assert 'href="/app/equipe"' in resposta.text
    assert 'href="/app/trafego"' in resposta.text
    assert 'href="/app/financeiras"' in resposta.text
    assert "Próximo incremento" not in resposta.text
    assert "Estrutura preparada" not in resposta.text


def test_admin_plataforma_ve_somente_atalho_permitido(client):
    login(client, papel="admin_plataforma", email="admin@plataforma.test")

    resposta = client.get("/app/configuracoes")

    assert resposta.status_code == 200
    assert 'href="/app/equipe"' in resposta.text
    assert 'href="/app/trafego"' not in resposta.text
    assert 'href="/app/financeiras"' not in resposta.text


def test_gerente_e_vendedor_nao_acessam_configuracoes(client):
    for papel in ("gerente", "vendedor"):
        client.cookies.clear()
        login(client, papel=papel, email=f"{papel}@loja.test")

        resposta = client.get("/app/configuracoes", follow_redirects=False)

        assert resposta.status_code == 303
        assert resposta.headers["location"] == "/app"


def test_meta_capi_considera_apenas_configuracao_da_loja_logada(client):
    db = SessionLocal()
    db.add(
        MetaPixelConfig(
            loja_slug="outra-loja",
            pixel_id="pixel-outra-loja",
            token_ciphertext="ciphertext-outra-loja",
        )
    )
    db.commit()
    db.close()
    login(client)

    resposta = client.get("/app/configuracoes")

    bloco_meta = resposta.text.split("Meta / CAPI", 1)[1].split("</article>", 1)[0]
    assert "Não configurado" in bloco_meta
    assert "pixel-outra-loja" not in resposta.text
    assert "ciphertext-outra-loja" not in resposta.text


def test_configuracoes_nao_expoe_urls_tokens_ou_segredos(client):
    db = SessionLocal()
    db.add(
        MetaPixelConfig(
            loja_slug="loja-teste",
            pixel_id="pixel-secreto-nao-renderizar",
            token_ciphertext="capi-ciphertext-nao-renderizar",
            test_event_code="evento-secreto-nao-renderizar",
        )
    )
    db.commit()
    db.close()
    login(client)

    resposta = client.get("/app/configuracoes")

    assert resposta.status_code == 200
    bloco_meta = resposta.text.split("Meta / CAPI", 1)[1].split("</article>", 1)[0]
    assert "Configurado" in bloco_meta
    proibidos = (
        "http://estoque-api:8000",
        "http://chatbot-api:8000",
        "http://motor-simulacao:8000",
        "token-de-teste",
        "token-chatbot-teste",
        "pixel-secreto-nao-renderizar",
        "capi-ciphertext-nao-renderizar",
        "evento-secreto-nao-renderizar",
    )
    for segredo in proibidos:
        assert segredo not in resposta.text
