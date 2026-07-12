import httpx
from conftest import csrf_da_resposta, login

from app.clients.chatbot import ChatbotClient, SimulacaoIndisponivel


def _csrf_do_form(client):
    pagina = client.get("/app/simulacoes")
    return csrf_da_resposta(pagina)


def _dados_validos(csrf):
    return {
        "csrf": csrf,
        "cpf": "12345678909",
        "nascimento": "1990-05-20",
        "valor": "30000",
        "prazo_meses": "48",
        "entrada": "5000",
        "renda": "4000",
        "categoria": "moto",
    }


def test_form_renderiza_para_dono(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "Simulação manual" in resposta.text


def test_vendedor_e_redirecionado(client, chatbot_fake):
    login(client, papel="vendedor")
    resposta = client.get("/app/simulacoes", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"


def test_post_retorna_parcelas_da_api(client, chatbot_fake):
    login(client)
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    assert "Banco Teste" in resposta.text
    assert "796,91" in resposta.text
    assert chatbot_fake.simulacoes[0]["cpf"] == "12345678909"


def test_post_409_mostra_nao_habilitada(client, chatbot_fake):
    chatbot_fake.simulacao_indisponivel = True
    login(client)
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 409
    assert "não habilitada" in resposta.text


def test_post_csrf_invalido_e_rejeitado(client, chatbot_fake):
    login(client)
    _csrf_do_form(client)
    dados = _dados_validos("csrf-errado")
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/simulacoes"
    assert chatbot_fake.simulacoes == []


def test_cpf_completo_nao_aparece_no_resultado(client, chatbot_fake):
    login(client)
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    assert "12345678909" not in resposta.text
    assert "•••.•••.•••-09" in resposta.text


def test_simulacoes_exige_login(client, chatbot_fake):
    resposta = client.get("/app/simulacoes", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def _cliente_com_transporte(monkeypatch, handler):
    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def fabrica(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr("app.clients.chatbot.httpx.Client", fabrica)
    return ChatbotClient("http://chatbot", "tok-secreto")


def test_client_simular_envia_payload(monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Bearer tok-secreto"
        assert request.url.path == "/v1/simular"
        return httpx.Response(200, json={"id": "s1", "resultados": [{"provedor": "BV"}]})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    resultado = chatbot.simular({"cpf": "1", "valor": 10})
    assert resultado["resultados"][0]["provedor"] == "BV"


def test_client_simular_409_mapeia_indisponivel(monkeypatch):
    def handler(request):
        return httpx.Response(409, json={"detail": "simulação não habilitada nesta instalação"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    try:
        chatbot.simular({"cpf": "1"})
        assert False, "deveria levantar SimulacaoIndisponivel"
    except SimulacaoIndisponivel:
        pass
