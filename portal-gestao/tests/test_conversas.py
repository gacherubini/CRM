import httpx
from conftest import csrf_da_resposta, login

from app.clients.chatbot import ChatbotClient, ConversaNaoEncontrada


def test_lista_renderiza_conversas(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/conversas")
    assert resposta.status_code == 200
    assert "Tem Civic disponível?" in resposta.text
    assert 'href="/app/conversas/5511987654321"' in resposta.text


def test_lista_mascara_telefone_no_display(client, chatbot_fake):
    # O telefone é a chave do recurso (aparece só no href do link).
    # O texto exibido ao operador é mascarado.
    login(client)
    resposta = client.get("/app/conversas")
    assert "•••• 4321" in resposta.text
    assert "<strong>5511987654321</strong>" not in resposta.text


def test_lista_filtra_por_busca(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/conversas", params={"busca": "1111"})
    assert resposta.status_code == 200
    assert 'href="/app/conversas/5511911112222"' in resposta.text
    assert 'href="/app/conversas/5511987654321"' not in resposta.text


def test_lista_trata_indisponivel_sem_500(client, chatbot_fake):
    chatbot_fake.indisponivel = True
    login(client)
    resposta = client.get("/app/conversas")
    assert resposta.status_code == 200
    assert "Conversas desconectadas" in resposta.text


def test_detalhe_renderiza_thread(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/conversas/5511987654321")
    assert resposta.status_code == 200
    assert "Tem Civic disponível?" in resposta.text
    assert "Temos sim!" in resposta.text
    assert "Assumir atendimento" in resposta.text


def test_detalhe_conversa_inexistente_404(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/conversas/0000")
    assert resposta.status_code == 404
    assert "Conversa não encontrada" in resposta.text


def test_detalhe_humano_mostra_devolver(client, chatbot_fake):
    chatbot_fake.mensagens["5511911112222"] = [
        {"direcao": "saida", "texto": "oi", "criada_em": "2026-07-12T13:00:00+00:00"}
    ]
    login(client)
    resposta = client.get("/app/conversas/5511911112222")
    assert resposta.status_code == 200
    assert "Devolver ao bot" in resposta.text


def test_handoff_assumir_pausa_bot(client, chatbot_fake):
    login(client)
    pagina = client.get("/app/conversas/5511987654321")
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "assumir"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert chatbot_fake.handoffs == [("5511987654321", False)]


def test_handoff_devolver_reativa_bot(client, chatbot_fake):
    login(client)
    pagina = client.get("/app/conversas/5511987654321")
    client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": csrf_da_resposta(pagina), "acao": "devolver"},
        follow_redirects=False,
    )
    assert chatbot_fake.handoffs == [("5511987654321", True)]


def test_handoff_csrf_invalido_nao_altera(client, chatbot_fake):
    login(client)
    resposta = client.post(
        "/app/conversas/5511987654321/handoff",
        data={"csrf": "errado", "acao": "assumir"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert chatbot_fake.handoffs == []


def test_conversas_exige_login(client, chatbot_fake):
    resposta = client.get("/app/conversas", follow_redirects=False)
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


def test_client_listar_conversas_com_bearer(monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Bearer tok-secreto"
        assert request.url.path == "/v1/conversas"
        return httpx.Response(200, json={"conversas": [{"telefone": "55"}], "limit": 50, "offset": 0})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    assert chatbot.listar_conversas() == [{"telefone": "55"}]


def test_client_mensagens_404_mapeia_conversa_nao_encontrada(monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"detail": "conversa não encontrada"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    try:
        chatbot.listar_mensagens("55")
        assert False, "deveria levantar ConversaNaoEncontrada"
    except ConversaNaoEncontrada:
        pass


def test_client_definir_bot_ativo_faz_patch(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/v1/conversas/55/estado"
        return httpx.Response(200, json={"bot_ativo": False, "status": "handoff"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    assert chatbot.definir_bot_ativo("55", False)["status"] == "handoff"
