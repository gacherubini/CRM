from conftest import csrf_da_resposta, login

from app.web.simulacoes import (
    _cards_bancos_progresso,
    _grupos_resultados_por_banco,
    _resumo_grupos,
    _veredito_do_codigo,
)


def _csrf_do_form(client):
    pagina = client.get("/app/simulacoes")
    return csrf_da_resposta(pagina)


def _dados_motor(csrf, **extra):
    base = {
        "csrf": csrf,
        "modo": "todos",
        "cpf": "52998224725",
        "nascimento": "1990-05-20",
        "celular": "11987654321",
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
    assert "Celular" in resposta.text


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
    assert 'name="provedores"' in resposta.text
    assert "Marcar todos" in resposta.text
    assert "Placa" in resposta.text
    assert "Banco PAN" in resposta.text or "pan" in resposta.text.lower()


def test_form_mostra_omni_quando_credencial_pronta(client, chatbot_fake, motor_fake):
    """Omni aparece sozinho quando o Motor expõe a credencial (sem hardcode)."""
    motor_fake.credenciais.append({
        "provedor": "omni",
        "usuario": "lojista",
        "senha_configurada": True,
        "senha_mascara": "****",
        "habilitado": True,
        "atualizado_em": "2026-09-12T12:00:00+00:00",
        "ultimo_sucesso_em": None,
        "ultimo_erro_sanitizado": None,
        "falhas_login": 0,
    })
    motor_fake.provedores.append({
        "nome": "omni", "rotulo": "Omni", "habilitado": True,
        "real": True, "modo": "playwright",
        "campos_credencial": [],
    })
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert 'value="omni"' in resposta.text
    assert "Omni" in resposta.text


def test_rotulos_conhecem_motrix_e_omni():
    from app.web.simulacoes import _PROVEDORES_REAIS, _ROTULOS_BANCO
    assert {"motrix", "omni"} <= set(_PROVEDORES_REAIS)
    assert _ROTULOS_BANCO["motrix"] == "Motrix"
    assert _ROTULOS_BANCO["omni"] == "Omni"


def test_form_bancos_sem_inline_style(client, chatbot_fake, motor_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert "sim-bank-chips" in resposta.text
    assert "sim-bank-bar" in resposta.text
    assert 'sim-bank-chips" style=' not in resposta.text
    assert "display:flex;flex-wrap:wrap;gap:10px" not in resposta.text


def test_simular_banco_unico_escolhido(client, chatbot_fake, motor_fake):
    """Checkbox permite testar 1 banco por vez."""
    motor_fake.credenciais[1]["senha_configurada"] = True
    motor_fake.credenciais[1]["habilitado"] = True
    motor_fake.credenciais[1]["usuario"] = "lojista"
    login(client, papel="dono")
    dados = _dados_motor(_csrf_do_form(client), provedores="santander")
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    body = motor_fake.simulacoes[0]
    assert body["provedores"] == ["santander"]


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
    assert body["pessoa"]["ddd"] == "11"
    assert body["pessoa"]["celular"] == "11987654321"
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
        provedores=["pan", "santander"],
    )
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    body = motor_fake.simulacoes[0]
    assert set(body["provedores"]) == {"pan", "santander"}


def test_payload_envia_celular_e_sem_campos_pan_api(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    dados = _dados_motor(
        _csrf_do_form(client),
        valor="22000",
        entrada="5000",
        prazos_meses="24,36,48",
        zero_km="sim",
        celular="(21) 99876-5432",
    )
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    body = motor_fake.simulacoes[0]
    assert body["provedores"] == ["pan"]
    assert body["pessoa"]["ddd"] == "21"
    assert body["pessoa"]["celular"] == "21998765432"
    assert body["pessoa"].get("codigo_natureza_ocupacao") is None
    assert body["veiculo"].get("codigo_provedor") is None
    assert body["veiculo"].get("ano_modelo") is None
    assert body["veiculo"]["zero_km"] is True


def test_simular_sem_celular_rejeita(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    antes = len(getattr(motor_fake, "simulacoes", []) or [])
    dados = _dados_motor(_csrf_do_form(client), celular="")
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 422
    assert "celular" in resposta.text.lower()
    assert len(getattr(motor_fake, "simulacoes", []) or []) == antes


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
    # Atualiza por fetch, sem recarregar a página e jogar a rolagem para o topo.
    assert 'http-equiv="refresh"' not in job.text
    assert 'data-atualizacao="3"' in job.text
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
    # multi-banco: seções separadas
    assert "Santander" in resposta.text
    assert "Bradesco" in resposta.text
    assert "Abrir print" in resposta.text or "print" in resposta.text.lower()
    # Sem meta refresh: a página não pode voltar ao topo enquanto o dono lê um print.
    assert 'http-equiv="refresh"' not in resposta.text
    assert 'data-auto-refresh="1"' in resposta.text
    assert 'data-evento-id="1"' in resposta.text
    # Botão próprio para as parcelas, separado dos registros.
    assert 'href="/app/simulacoes/job/sim-motor-1"' in resposta.text
    assert "Ver parcelas" in resposta.text


def test_registros_tem_botao_minimizar_bancos(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/sim-motor-1/registros")
    assert resposta.status_code == 200
    # Botão fica no cabeçalho (fora do #sim-registros), então o auto-refresh
    # não o recria. A classe de colapso vai no próprio #sim-registros.
    assert 'id="sim-bancos-toggle"' in resposta.text
    assert "Minimizar bancos" in resposta.text
    assert 'data-provedor="santander"' in resposta.text
    assert 'data-provedor="bradesco"' in resposta.text


def test_registros_de_job_encerrado_nao_se_atualizam(client, chatbot_fake, motor_fake):
    motor_fake.status_retorno = "concluida"
    login(client, papel="dono")
    resposta = client.get("/app/simulacoes/sim-motor-1/registros")
    assert 'data-auto-refresh="0"' in resposta.text


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


def test_resultado_reaberto_pelo_historico_mostra_parametros_do_motor(
    client, chatbot_fake, motor_fake
):
    motor_fake.status_retorno = "aguardando_intervencao"
    motor_fake.parametros_retorno = {
        "placa": "TJK2I60",
        "prazos_meses": [12, 24, 36, 48],
        "categoria": "moto",
        "valor": 21900.0,
        "entrada": 1500.0,
        "uf_licenciamento": "RS",
        "zero_km": False,
    }
    login(client, papel="dono")
    # Sem POST antes: a sessão não tem os parâmetros, só o Motor.
    resposta = client.get("/app/simulacoes/job/sim-historico-1")
    assert resposta.status_code == 200
    assert "Parcelas simuladas" in resposta.text
    assert "21.900,00" in resposta.text
    assert "1.500,00" in resposta.text
    assert "Moto" in resposta.text
    assert "RS" in resposta.text
    assert 'href="/app/simulacoes/sim-historico-1/registros"' in resposta.text


def test_resultado_mostra_cpf_inteiro_para_dono(client, chatbot_fake, motor_fake):
    login(client, papel="dono")
    post = client.post(
        "/app/simulacoes", data=_dados_motor(_csrf_do_form(client)), follow_redirects=False
    )
    job = client.get(post.headers["location"])
    assert "529.982.247-25" in job.text


def test_resultado_mascara_cpf_para_vendedor(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor", email="vend@loja.test")
    post = client.post(
        "/app/simulacoes", data=_dados_motor(_csrf_do_form(client)), follow_redirects=False
    )
    job = client.get(post.headers["location"])
    assert "529.982.247-25" not in job.text
    assert "52998224725" not in job.text


def test_form_tem_campo_sexo(client, chatbot_fake, motor_fake):
    login(client)
    resposta = client.get("/app/simulacoes")
    assert resposta.status_code == 200
    assert 'name="sexo"' in resposta.text
    assert "Masculino" in resposta.text
    assert "Feminino" in resposta.text


def test_sexo_vai_no_payload_do_motor(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    dados = _dados_motor(_csrf_do_form(client), sexo="Feminino")
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert motor_fake.simulacoes[-1]["pessoa"]["sexo"] == "Feminino"


def test_sem_sexo_payload_vai_nulo(client, chatbot_fake, motor_fake):
    login(client, papel="vendedor")
    dados = _dados_motor(_csrf_do_form(client))
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert motor_fake.simulacoes[-1]["pessoa"]["sexo"] is None


# --- veredito por banco: captcha/rede não é falha -----------------------------


def test_card_aguardando_intervencao_nao_e_falha():
    """16/09: tarefa de captcha vinha do Motor como `aguardando_intervencao` e
    o card dizia 'Falhou' com o job dizendo 'Aguardando intervenção'."""
    cards = _cards_bancos_progresso(
        ["bradesco"],
        resultados=[],
        tarefas=[
            {
                "provedor": "bradesco",
                "status": "aguardando_intervencao",
                "codigo_erro": "captcha_login",
            }
        ],
        status_job="aguardando_intervencao",
    )

    assert cards[0]["veredito"] == "intervencao"
    assert cards[0]["status_label"] == "Aguardando intervenção"


def test_resultado_aguardando_intervencao_nao_e_falha():
    """Na tela de resultado o veredito vinha só do `codigo_erro`: captcha
    caía em 'falha' (vermelho). O status da linha manda."""
    grupos = _grupos_resultados_por_banco(
        [
            {
                "provedor": "bradesco",
                "status": "aguardando_intervencao",
                "codigo_erro": "captcha_login",
                "valor_parcela": None,
            }
        ]
    )

    assert grupos[0]["veredito"] == "intervencao"
    assert grupos[0]["veredito_rotulo"] == "Aguardando ação"


def test_recusa_segue_como_recusado_e_conta_no_resumo():
    """Guarda contra regressão: `credito_recusado` continua 'recusado' e o
    resumo do topo não deixa banco nenhum fora da conta."""
    grupos = _grupos_resultados_por_banco(
        [
            {
                "provedor": "santander",
                "status": "rejeitada",
                "codigo_erro": "credito_recusado",
                "valor_parcela": None,
            },
            {
                "provedor": "bradesco",
                "status": "aguardando_intervencao",
                "codigo_erro": "captcha_login",
                "valor_parcela": None,
            },
        ]
    )

    assert _veredito_do_codigo("credito_recusado") == "recusado"
    resumo = _resumo_grupos(grupos)
    assert resumo["ok"] == 0
    assert resumo["recusados"] == 2  # recusado + intervencao contam como sem oferta
    assert resumo["total"] == 2


def test_provedores_da_simulacao_preserva_ordem_do_form():
    from app.web.simulacoes import _provedores_da_simulacao

    class _Form(dict):
        def getlist(self, nome):
            return self.get(nome, [])

    prontos = [
        {"provedor": "pan"},
        {"provedor": "santander"},
        {"provedor": "bradesco"},
    ]
    # A ordem da tela vence a ordem da lista de credenciais.
    assert _provedores_da_simulacao(
        _Form(provedores=["bradesco", "pan"]), prontos
    ) == ["bradesco", "pan"]


def test_ordem_bancos_salva_e_reordena_os_chips(client, motor_fake):
    # Dois bancos prontos: o padrão é a ordem da lista de credenciais [pan, santander].
    motor_fake.credenciais[1]["senha_configurada"] = True
    motor_fake.credenciais[1]["habilitado"] = True
    login(client, papel="dono")
    pagina = client.get("/app/simulacoes")
    assert pagina.text.index('data-provedor="pan"') < pagina.text.index(
        'data-provedor="santander"'
    )

    resposta = client.post(
        "/app/simulacoes/ordem-bancos",
        json={"csrf": csrf_da_resposta(pagina), "ordem": ["santander", "pan"]},
    )
    assert resposta.status_code == 200
    assert resposta.json()["ordem"] == ["santander", "pan"]

    nova = client.get("/app/simulacoes")
    assert nova.text.index('data-provedor="santander"') < nova.text.index(
        'data-provedor="pan"'
    )
    # A ordem gravada também vai no campo oculto do form (ordem de consulta).
    assert 'value="santander,pan"' in nova.text


def test_ordem_bancos_exige_csrf(client, motor_fake):
    login(client, papel="dono")
    resposta = client.post(
        "/app/simulacoes/ordem-bancos",
        json={"csrf": "invalido", "ordem": ["pan"]},
    )
    assert resposta.status_code == 403


def _tornar_bradesco_pronto(motor_fake):
    motor_fake.credenciais.append(
        {
            "provedor": "bradesco",
            "usuario": "loja",
            "senha_configurada": True,
            "senha_mascara": "****",
            "habilitado": True,
            "atualizado_em": None,
            "ultimo_sucesso_em": None,
            "ultimo_erro_sanitizado": None,
            "falhas_login": 0,
        }
    )


def test_bradesco_exige_sexo(client, motor_fake):
    _tornar_bradesco_pronto(motor_fake)
    login(client, papel="dono")
    dados = _dados_motor(_csrf_do_form(client), provedores=["bradesco"], sexo="")
    resposta = client.post("/app/simulacoes", data=dados)
    assert resposta.status_code == 422
    assert "Sexo" in resposta.text
    # Nada foi enviado ao Motor: a validação barra antes de gastar a rodada.
    assert not getattr(motor_fake, "simulacoes", None)


def test_bradesco_com_sexo_passa(client, motor_fake):
    _tornar_bradesco_pronto(motor_fake)
    login(client, papel="dono")
    dados = _dados_motor(
        _csrf_do_form(client), provedores=["bradesco"], sexo="Masculino"
    )
    resposta = client.post("/app/simulacoes", data=dados, follow_redirects=False)
    assert resposta.status_code == 303
    assert motor_fake.simulacoes[0]["provedores"] == ["bradesco"]
