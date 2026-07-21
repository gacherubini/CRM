import json

import httpx
from conftest import csrf_da_resposta, login

from app.clients.chatbot import ChatbotClient, LeadNaoEncontrado
from app.db import SessionLocal
from app.models import FunilEvento


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


def test_lista_mostra_nome_quando_presente(client, chatbot_fake):
    login(client)
    resposta = client.get("/app/leads")
    assert resposta.status_code == 200
    assert "Joao Oculto" in resposta.text
    assert "Contato sem consentimento" not in resposta.text


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
    assert 'action="/app/leads/l1/etapa"' in resposta.text
    assert '<option value="novo" selected>' in resposta.text


def test_vendedor_atualiza_etapa_com_csrf(client, chatbot_fake):
    login(client, papel="vendedor")
    pagina = client.get("/app/leads/l1")

    resposta = client.post(
        "/app/leads/l1/etapa",
        data={"csrf": csrf_da_resposta(pagina), "etapa": "qualificado"},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/leads/l1?ok=etapa-atualizada"
    assert chatbot_fake.etapas_atualizadas == [("l1", "qualificado")]
    db = SessionLocal()
    evento = db.query(FunilEvento).filter_by(lead_ref="l1", tipo="etapa_manual").one()
    assert evento.loja_slug == "loja-teste"
    assert json.loads(evento.payload_json) == {"etapa_nova": "qualificado"}
    db.close()


def test_etapa_perdido_registra_movimento_e_perda(client, chatbot_fake):
    login(client)
    pagina = client.get("/app/leads/l1")

    resposta = client.post(
        "/app/leads/l1/etapa",
        data={"csrf": csrf_da_resposta(pagina), "etapa": "perdido"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/leads/l1?ok=etapa-atualizada"
    db = SessionLocal()
    eventos = db.query(FunilEvento).filter_by(lead_ref="l1").all()
    assert {evento.tipo for evento in eventos} == {"etapa_manual", "perda"}
    db.close()


def test_atualizar_etapa_rejeita_valor_invalido(client, chatbot_fake):
    login(client)
    pagina = client.get("/app/leads/l1")

    resposta = client.post(
        "/app/leads/l1/etapa",
        data={"csrf": csrf_da_resposta(pagina), "etapa": "inventada"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/leads/l1?erro=etapa"
    assert chatbot_fake.etapas_atualizadas == []


def test_atualizar_etapa_exige_csrf(client, chatbot_fake):
    login(client)

    resposta = client.post(
        "/app/leads/l1/etapa",
        data={"csrf": "invalido", "etapa": "perdido"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/leads/l1?erro=sessao"
    assert chatbot_fake.etapas_atualizadas == []


def test_papel_sem_permissao_nao_atualiza_etapa(client, chatbot_fake):
    login(client, papel="auditor")
    pagina = client.get("/app/leads/l1")
    assert 'action="/app/leads/l1/etapa"' not in pagina.text

    resposta = client.post(
        "/app/leads/l1/etapa",
        data={"csrf": csrf_da_resposta(pagina), "etapa": "convertido"},
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/leads"
    assert chatbot_fake.etapas_atualizadas == []


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


def test_client_lista_eventos_funil_sanitizados(monkeypatch):
    evento = {
        "lead_ref": "l1",
        "tipo": "lead_criado",
        "ocorrido_em": "2026-07-09T09:00:00+00:00",
        "idempotency_key": "chatbot:lead:l1:criado",
        "payload": None,
    }

    def handler(request):
        assert request.url.path == "/v1/funil/eventos"
        assert request.url.params["limit"] == "500"
        assert request.url.params["offset"] == "0"
        return httpx.Response(200, json={"eventos": [evento]})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    assert chatbot.listar_eventos_funil() == [evento]


def test_client_obter_lead_404_mapeia_nao_encontrado(monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"detail": "nao encontrado"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)
    try:
        chatbot.obter_lead("x")
        assert False, "deveria levantar LeadNaoEncontrado"
    except LeadNaoEncontrado:
        pass


def test_client_atualiza_etapa_com_patch_e_bearer(monkeypatch):
    def handler(request):
        assert request.method == "PATCH"
        assert request.headers["authorization"] == "Bearer tok-secreto"
        assert request.url.path == "/v1/leads/l1/etapa"
        assert json.loads(request.read()) == {"etapa": "qualificado"}
        return httpx.Response(200, json={"id": "l1", "etapa": "qualificado"})

    chatbot = _cliente_com_transporte(monkeypatch, handler)

    assert chatbot.atualizar_etapa_lead("l1", "qualificado")["etapa"] == "qualificado"
