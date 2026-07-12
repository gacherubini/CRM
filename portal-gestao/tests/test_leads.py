import httpx
from conftest import login

from app.clients.chatbot import ChatbotClient, LeadNaoEncontrado


def test_lista_renderiza_leads(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads")
    assert resposta.status_code == 200
    assert "Maria Silva" in resposta.text
    assert 'href="/app/leads/l1"' in resposta.text


def test_lista_mascara_telefone(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads")
    assert resposta.status_code == 200
    assert "5511987654321" not in resposta.text
    assert "•••• 4321" in resposta.text


def test_lista_esconde_nome_sem_consentimento(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads")
    assert resposta.status_code == 200
    assert "Joao Oculto" not in resposta.text
    assert "Contato sem consentimento" in resposta.text


def test_lista_filtra_por_busca_local(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads", params={"busca": "Maria"})
    assert resposta.status_code == 200
    assert "Maria Silva" in resposta.text
    assert 'href="/app/leads/l2"' not in resposta.text


def test_lista_trata_indisponivel_sem_500(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    login(client)
    resposta = client.get("/app/leads")
    assert resposta.status_code == 200
    assert "Leads desconectados" in resposta.text


def test_detalhe_renderiza_lead(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads/l1")
    assert resposta.status_code == 200
    assert "Maria Silva" in resposta.text
    assert "Honda Civic 2022" in resposta.text
    assert "5511987654321" not in resposta.text


def test_detalhe_lead_inexistente_retorna_404(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads/nao-existe")
    assert resposta.status_code == 404
    assert "Lead não encontrado" in resposta.text


def test_leads_exige_login(client, chatbot_fake):
    resposta = client.get("/app/leads", follow_redirects=False)
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


def test_client_lista_leads_com_bearer(monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Bearer tok-secreto"
        assert request.url.path == "/v1/leads"
        return httpx.Response(200, json={"leads": [{"id": "l1", "etapa": "novo"}]})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    leads = chatbot.listar_leads()
    assert leads == [{"id": "l1", "etapa": "novo"}]


def test_client_obter_lead_404_mapeia_nao_encontrado(monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"detail": "nao encontrado"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    try:
        chatbot.obter_lead("x")
        assert False, "deveria levantar LeadNaoEncontrado"
    except LeadNaoEncontrado:
        pass
