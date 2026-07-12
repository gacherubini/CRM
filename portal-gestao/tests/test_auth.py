from conftest import csrf_da_resposta, criar_usuario, login


def test_area_privada_redireciona_para_login(client):
    resposta = client.get("/app", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_login_cria_sessao_e_abre_dashboard(client):
    resposta = login(client)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"
    dashboard = client.get("/app")
    assert dashboard.status_code == 200
    assert "Visão geral" in dashboard.text
    assert "Ana Loja" in dashboard.text


def test_login_rejeita_csrf_invalido(client):
    criar_usuario()
    resposta = client.post(
        "/login",
        data={"email": "dono@loja.test", "senha": "senha-segura", "csrf": "falso"},
    )
    assert resposta.status_code == 400
    assert "Sessão expirada" in resposta.text


def test_logout_invalida_sessao(client):
    login(client)
    pagina = client.get("/app")
    resposta = client.post("/logout", data={"csrf": csrf_da_resposta(pagina)}, follow_redirects=False)
    assert resposta.status_code == 303
    assert client.get("/app", follow_redirects=False).headers["location"] == "/login"
