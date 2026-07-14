"""Histórico de simulações por usuário no Portal (Task 16).

Rota BFF /app/simulacoes/historico: lista as sims do usuário logado (por email
do ator), respeita RBAC (pode_simular), não vaza token e dá atalho ao job.
"""
from conftest import login


def test_historico_exige_login(client, motor_fake):
    resposta = client.get("/app/simulacoes/historico", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_historico_lista_apenas_minhas_sims_por_padrao(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico")
    assert resposta.status_code == 200
    # Filtrou pelo email do usuário logado (ator = solicitado_por).
    filtro = motor_fake.listagens[-1]
    assert filtro["solicitado_por"] == "dono@loja.test"
    assert filtro["ator"] == "dono@loja.test"
    # Vê a própria sim, não a de outro usuário da loja.
    assert "ABC1D23" in resposta.text
    assert "ZZZ9Z99" not in resposta.text


def test_historico_tem_atalho_para_o_job(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico")
    assert "/app/simulacoes/job/sim-dono-1" in resposta.text


def test_historico_vendedor_escopo_forcado_para_minhas(client, motor_fake):
    login(client, papel="vendedor", email="vend@loja.test")
    # Mesmo pedindo escopo=loja, vendedor só vê as próprias.
    resposta = client.get("/app/simulacoes/historico?escopo=loja")
    assert resposta.status_code == 200
    assert motor_fake.listagens[-1]["solicitado_por"] == "vend@loja.test"


def test_historico_dono_pode_ver_toda_a_loja(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico?escopo=loja")
    assert resposta.status_code == 200
    # Escopo loja: não filtra por solicitado_por → Motor devolve todas do tenant.
    assert motor_fake.listagens[-1]["solicitado_por"] is None
    assert "ABC1D23" in resposta.text
    assert "ZZZ9Z99" in resposta.text


def test_historico_filtra_por_status(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico?status=falhou")
    assert resposta.status_code == 200
    assert motor_fake.listagens[-1]["status"] == "falhou"


def test_historico_nao_vaza_token_no_html(client, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico")
    assert "Bearer" not in resposta.text
    assert "Authorization" not in resposta.text


def test_historico_motor_indisponivel_mostra_erro(client, motor_fake):
    motor_fake.indisponivel = True
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/historico")
    assert resposta.status_code == 200
    assert "Motor" in resposta.text


def test_form_tem_link_para_historico(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes")
    assert "/app/simulacoes/historico" in resposta.text


def test_client_listar_simulacoes_envia_token_ator_e_filtros(monkeypatch):
    import httpx

    from app.clients.motor import MotorClient

    def handler(request):
        assert request.headers["authorization"] == "Bearer tok-servidor"
        assert request.headers["x-ator"] == "ana@loja.test"
        assert request.url.path == "/v1/simulacoes"
        params = dict(request.url.params)
        assert params["solicitado_por"] == "ana@loja.test"
        assert params["status"] == "concluida"
        assert params["limite"] == "20"
        return httpx.Response(200, json={"itens": [{"id": "s1"}], "total": 1})

    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr("app.clients.motor.httpx.Client", fabrica)
    motor = MotorClient("http://motor", "tok-servidor")
    dados = motor.listar_simulacoes(
        ator="ana@loja.test", solicitado_por="ana@loja.test",
        status="concluida", limite=20,
    )
    assert dados["itens"][0]["id"] == "s1"
