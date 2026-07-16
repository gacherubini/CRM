"""Task 9A — UI de credenciais das financeiras (BFF → Motor)."""
from conftest import MotorFake, csrf_da_resposta, login

from app.clients.motor import MotorClient, MotorIndisponivel
from app.main import app, get_motor_client


def test_lista_exige_autenticacao(client):
    resposta = client.get("/app/financeiras", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_dono_lista_financeiras(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 200
    assert "PAN" in resposta.text
    assert "Santander" in resposta.text
    assert "Configurado" in resposta.text
    assert "Acessos dos bancos" in resposta.text
    assert "Acessos dos bancos" in resposta.text  # nav


def test_gerente_acessa(client, motor_fake):
    login(client, papel="gerente")
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 200
    assert "PAN" in resposta.text


def test_vendedor_proibido(client, motor_fake):
    login(client, papel="vendedor")
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 403
    assert "Pan" not in resposta.text
    assert "SENHA-SECRETA" not in resposta.text
    assert "não tem permissão" in resposta.text.lower() or "permissão" in resposta.text.lower()


def test_html_nunca_contem_senha_bruta(client, motor_fake):
    login(client)
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 200
    assert "SENHA-SECRETA-NUNCA-NO-HTML" not in resposta.text
    # campos de senha do form ficam vazios (placeholder só)
    assert 'name="campo__senha"' in resposta.text or 'name="senha"' in resposta.text
    assert "senha-super" not in resposta.text.lower()


def test_upsert_chama_motor_com_ator(client, motor_fake):
    login(client)
    pagina = client.get("/app/financeiras")
    csrf = csrf_da_resposta(pagina)
    resposta = client.post(
        "/app/financeiras/Pan",
        data={
            "csrf": csrf,
            "usuario": "loja-nova",
            "senha": "nova-senha-rotacionada",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "ok=salvo" in resposta.headers["location"]
    assert len(motor_fake.upserts) == 1
    up = motor_fake.upserts[0]
    assert up["nome"] == "Pan"
    assert up["usuario"] == "loja-nova"
    assert up["senha"] == "nova-senha-rotacionada"
    assert up["ator"] == "dono@loja.test"
    assert up["campos"] is None


def test_vendedor_nao_faz_upsert(client, motor_fake):
    login(client, papel="vendedor")
    # CSRF via login page (vendedor não vê /app/financeiras)
    pagina = client.get("/login")
    # reutiliza sessão e tenta POST direto
    pagina_app = client.get("/app")
    csrf = csrf_da_resposta(pagina_app)
    resposta = client.post(
        "/app/financeiras/Pan",
        data={"csrf": csrf, "usuario": "x", "senha": "y"},
        follow_redirects=False,
    )
    assert resposta.status_code == 403
    assert motor_fake.upserts == []


def test_testar_login_chama_motor(client, motor_fake):
    login(client)
    pagina = client.get("/app/financeiras")
    csrf = csrf_da_resposta(pagina)
    resposta = client.post(
        "/app/financeiras/Pan/testar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "teste=placeholder" in resposta.headers["location"]
    assert motor_fake.testes == [{"nome": "Pan", "ator": "dono@loja.test"}]


def test_motor_indisponivel_mensagem_amigavel(client, motor_fake):
    motor_fake.indisponivel = True
    login(client)
    resposta = client.get("/app/financeiras")
    assert resposta.status_code == 200
    assert "Não foi possível acessar o Motor" in resposta.text
    assert "SENHA-SECRETA" not in resposta.text


def test_motor_desligado_explica_integracao(client):
    fake = MotorFake(configurado=False)
    app.dependency_overrides[get_motor_client] = lambda: fake
    try:
        login(client)
        resposta = client.get("/app/financeiras")
        assert resposta.status_code == 200
        assert "desligada" in resposta.text.lower() or "não configurada" in resposta.text.lower() or "MOTOR" in resposta.text
        assert "Pan" not in resposta.text or "Configurado" not in resposta.text
    finally:
        app.dependency_overrides[get_motor_client] = lambda: MotorFake(configurado=True)


def test_client_motor_nao_configurado_levanta():
    cliente = MotorClient("", "", timeout=1)
    assert cliente.configurado is False
    try:
        cliente.listar_credenciais(ator="x@y.z")
        assert False, "deveria falhar"
    except MotorIndisponivel as exc:
        assert "não configurada" in str(exc).lower() or "configur" in str(exc).lower()


def test_nav_financeiras_ausente_para_vendedor(client, motor_fake):
    login(client, papel="vendedor")
    resposta = client.get("/app")
    assert resposta.status_code == 200
    assert 'href="/app/financeiras"' not in resposta.text
