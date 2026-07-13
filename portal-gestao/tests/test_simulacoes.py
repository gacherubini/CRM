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


def test_vendedor_acessa_o_form(client, chatbot_fake):
    login(client, papel="vendedor")
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "Simulação manual" in resposta.text


def test_vendedor_pode_simular(client, chatbot_fake):
    login(client, papel="vendedor")
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    assert "Banco Teste" in resposta.text
    assert "796,91" in resposta.text
    assert chatbot_fake.simulacoes[0]["cpf"] == "12345678909"


def test_vendedor_nao_ve_dados_sensiveis(client, chatbot_fake):
    login(client, papel="vendedor")
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    texto = resposta.text
    # Nenhum custo, lucro, margem, comissão, token ou métrica pode vazar.
    for sentinela in ("98888", "12345", "SEGREDO", "77777", "6543", "spread", "margem", "lucro"):
        assert sentinela not in texto


def test_dono_continua_com_acesso_completo(client, chatbot_fake):
    login(client, papel="dono")
    dados = _dados_validos(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    assert "Banco Teste" in resposta.text
    assert "796,91" in resposta.text


def test_form_tem_modo_santander(client, chatbot_fake, motor_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "santander" in resposta.text
    assert "Placa" in resposta.text


def test_simular_santander_vai_ao_motor_nao_chatbot(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    csrf = _csrf_do_form(client)
    dados = {
        "csrf": csrf,
        "modo": "santander",
        "cpf": "52998224725",
        "nascimento": "1990-05-20",
        "cnh": "sim",
        "placa": "FUV7G58",
        "uf_licenciamento": "SP",
        "finalidade": "comum",
        "valor": "21900",
        "entrada": "1123.20",
        "prazos_meses": "12,24,36,48",
        "categoria": "moto",
        "prazo_meses": "48",
    }
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 200
    assert "946,28" in resposta.text or "946.28" in resposta.text
    assert "santander" in resposta.text.lower()
    assert chatbot_fake.simulacoes == []
    assert len(motor_fake.simulacoes) == 1
    body = motor_fake.simulacoes[0]
    assert body["provedores"] == ["santander"]
    assert body["veiculo"]["placa"] == "FUV7G58"
    assert body["pessoa"]["cnh"] is True


def test_sanitizador_remove_campos_sensiveis_sem_mutar_original():
    from app.main import simulacao_sem_dados_sensiveis

    bruto = {
        "id": "s1",
        "status": "concluida",
        "criada_em": "2026-07-13T10:00:00",
        "custo_veiculo": 98888.0,
        "lucro": 12345.0,
        "margem": 0.27,
        "motor_token": "SEGREDO",
        "metricas": {"spread": 0.11},
        "resultados": [
            {
                "provedor": "BV",
                "status": "concluida",
                "valor_parcela": 700.0,
                "taxa_am": 1.5,
                "prazo_meses": 48,
                "valor_financiado": 25000.0,
                "codigo_erro": None,
                "custo": 77777.0,
                "margem": 0.2,
                "comissao": 6543.0,
                "token": "res-tok",
            }
        ],
    }
    limpo = simulacao_sem_dados_sensiveis(bruto)
    assert limpo == {
        "id": "s1",
        "status": "concluida",
        "criada_em": "2026-07-13T10:00:00",
        "resultados": [
            {
                "provedor": "BV",
                "status": "concluida",
                "valor_parcela": 700.0,
                "taxa_am": 1.5,
                "prazo_meses": 48,
                "valor_financiado": 25000.0,
                "codigo_erro": None,
            }
        ],
    }
    # dono/gerente continuam vendo tudo: o dicionário original não é alterado.
    assert bruto["custo_veiculo"] == 98888.0
    assert bruto["resultados"][0]["custo"] == 77777.0


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
