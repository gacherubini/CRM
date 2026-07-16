from conftest import csrf_da_resposta, login


def _csrf_do_form(client):
    pagina = client.get("/app/simulacoes")
    return csrf_da_resposta(pagina)


def _dados_motor(csrf, **extra):
    base = {
        "csrf": csrf,
        "modo": "todos",
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
        "zero_km": "nao",
    }
    base.update(extra)
    return base


def test_form_renderiza_para_dono(client, chatbot_fake, motor_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "Simulação manual" in resposta.text
    assert "Mock" not in resposta.text
    assert "Natureza da ocupação" not in resposta.text
    assert "Código do veículo" not in resposta.text
    assert "Prazo único" not in resposta.text
    assert "Renda mensal" not in resposta.text
    assert "DDD" not in resposta.text


def test_vendedor_acessa_o_form(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "Simulação manual" in resposta.text


def test_vendedor_pode_simular_via_motor(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    dados = _dados_motor(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert chatbot_fake.simulacoes == []
    assert len(motor_fake.simulacoes) == 1
    job = client.get(resposta.headers["location"])
    assert job.status_code == 200
    assert "946,28" in job.text or "946.28" in job.text


def test_vendedor_nao_ve_dados_sensiveis(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    dados = _dados_motor(_csrf_do_form(client))
    post = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    job = client.get(post.headers["location"])
    texto = job.text
    for sentinela in ("98888", "12345", "SEGREDO", "77777", "6543", "spread", "margem", "lucro"):
        assert sentinela not in texto


def test_dono_simula_via_motor(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    dados = _dados_motor(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert len(motor_fake.simulacoes) == 1


def test_form_lista_bancos_prontos(client, chatbot_fake, motor_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert "Serão consultados" in resposta.text
    assert "Placa" in resposta.text
    assert "Banco PAN" in resposta.text or "pan" in resposta.text.lower()


def test_simular_todos_usa_bancos_com_credencial(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    dados = _dados_motor(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    loc = resposta.headers["location"]
    assert loc.startswith("/app/simulacoes/job/")
    assert chatbot_fake.simulacoes == []
    body = motor_fake.simulacoes[0]
    assert body["provedores"] == ["pan"]
    assert body["veiculo"]["placa"] == "FUV7G58"
    assert body["pessoa"]["cnh"] is True
    assert "ddd" not in body["pessoa"] or body["pessoa"].get("ddd") is None
    assert body["veiculo"].get("codigo_provedor") is None

    job = client.get(loc)
    assert job.status_code == 200
    assert "946,28" in job.text or "946.28" in job.text
    assert "FUV7G58" in job.text


def test_simular_todos_com_dois_bancos(client, chatbot_fake, motor_fake):
    motor_fake.credenciais[1]["senha_configurada"] = True
    motor_fake.credenciais[1]["habilitado"] = True
    motor_fake.credenciais[1]["usuario"] = "lojista"
    login(client, papel="dono")
    dados = _dados_motor(
        _csrf_do_form(client),
        placa="ABC1D23",
        valor="20000",
        entrada="0",
        prazos_meses="36",
    )
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    body = motor_fake.simulacoes[0]
    assert set(body["provedores"]) == {"pan", "santander"}


def test_payload_sem_campos_pan_api(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    dados = _dados_motor(
        _csrf_do_form(client),
        valor="22000",
        entrada="5000",
        prazos_meses="24,36,48",
        zero_km="sim",
    )
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    body = motor_fake.simulacoes[0]
    assert body["provedores"] == ["pan"]
    assert body["pessoa"].get("ddd") is None
    assert body["pessoa"].get("celular") is None
    assert body["pessoa"].get("codigo_natureza_ocupacao") is None
    assert body["veiculo"].get("codigo_provedor") is None
    assert body["veiculo"].get("ano_modelo") is None
    assert body["veiculo"]["zero_km"] is True


def test_job_em_processamento_mostra_progresso(client, chatbot_fake, motor_fake):
    motor_fake.status_retorno = "processando"
    login(client, papel="dono")
    dados = _dados_motor(_csrf_do_form(client), prazos_meses="48")
    post = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert post.status_code == 303
    job = client.get(post.headers["location"])
    assert job.status_code == 200
    assert "Simulação em andamento" in job.text
    assert (
        "Processando no banco" in job.text
        or "Consultando" in job.text
        or "Por banco" in job.text
    )
    assert 'http-equiv="refresh"' in job.text
    assert "FUV7G58" in job.text
    assert "52998224725" not in job.text


def test_registros_mostram_timeline_e_link_de_print_para_dono(
    client, chatbot_fake, motor_fake
):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/sim-motor-1/registros")
    assert resposta.status_code == 200
    assert "Preparando o navegador" in resposta.text
    assert "Login confirmado" in resposta.text
    assert "Ver print desta etapa" in resposta.text
    assert 'http-equiv="refresh"' in resposta.text


def test_vendedor_ve_timeline_mas_nao_abre_print(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    pagina = client.get("/app/simulacoes/sim-motor-1/registros")
    assert pagina.status_code == 200
    assert "Print restrito" in pagina.text
    imagem = client.get("/app/simulacoes/sim-motor-1/registros/2/print")
    assert imagem.status_code == 403


def test_dono_abre_print_sem_cache(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    imagem = client.get("/app/simulacoes/sim-motor-1/registros/2/print")
    assert imagem.status_code == 200
    assert imagem.content == b"PNG-FAKE"
    assert "no-store" in imagem.headers["cache-control"]


def test_job_na_fila_mostra_etapa_enfileirada(client, chatbot_fake, motor_fake):
    motor_fake.status_retorno = "recebida"
    login(client)
    dados = _dados_motor(
        _csrf_do_form(client),
        placa="ABC1D23",
        valor="20000",
        entrada="0",
        prazos_meses="36",
    )
    post = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    job = client.get(post.headers["location"])
    assert job.status_code == 200
    assert "Na fila" in job.text or "enfileirada" in job.text.lower()
