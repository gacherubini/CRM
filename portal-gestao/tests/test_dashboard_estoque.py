from conftest import csrf_da_resposta, login


def test_dashboard_resume_estoque_real(client):
    login(client)
    resposta = client.get("/app")
    assert resposta.status_code == 200
    assert "Honda Civic" in resposta.text
    assert "Yamaha MT-03" in resposta.text
    assert "118.900,00" in resposta.text


def test_dono_cadastra_veiculo(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={
            "csrf": csrf_da_resposta(pagina), "tipo": "carro", "marca": "Toyota",
            "modelo": "Corolla", "versao": "GLi", "ano_modelo": "2023", "cor": "Prata",
            "km": "12000", "preco": "129900.50", "custo": "110000",
            "codigo_interno": "T01", "foto_url": "",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/estoque?ok=criado"
    assert estoque_fake.criados[0]["modelo"] == "Corolla"
    assert estoque_fake.criados[0]["custo"] == 110000.0


def test_vendedor_ve_estoque_sem_custo_e_nao_edita(client):
    login(client, papel="vendedor")
    lista = client.get("/app/estoque")
    assert lista.status_code == 200
    assert "Honda Civic" in lista.text
    assert "Novo veículo" not in lista.text
    assert "102.000,00" not in lista.text
    edicao = client.get("/app/estoque/v1", follow_redirects=False)
    assert edicao.status_code == 303
    assert edicao.headers["location"] == "/app/estoque"


def test_acao_invalida_nao_chega_ao_cliente(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/v1")
    resposta = client.post(
        "/app/estoque/v1/apagar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/estoque?erro=acao"
    assert estoque_fake.acoes == []


def test_shell_exibe_navegacao_tech_com_estado_atual(client):
    login(client)
    resposta = client.get("/app/estoque")
    assert resposta.status_code == 200
    assert "Motora" in resposta.text
    assert 'href="/app/estoque" aria-current="page"' in resposta.text
    assert 'href="/app/simulacoes"' in resposta.text
    assert 'href="/app/equipe"' in resposta.text
    assert 'href="/app/configuracoes"' in resposta.text


def test_navegacao_respeita_papel_do_vendedor(client):
    login(client, papel="vendedor")
    resposta = client.get("/app")
    assert resposta.status_code == 200
    assert 'href="/app/estoque"' in resposta.text
    # Vendedor pode simular manualmente (decisão de produto #3A.1 Task 13).
    assert 'href="/app/simulacoes"' in resposta.text
    assert 'href="/app/equipe"' not in resposta.text
    assert 'href="/app/configuracoes"' not in resposta.text
    restrita = client.get("/app/equipe", follow_redirects=False)
    assert restrita.status_code == 303
    assert restrita.headers["location"] == "/app"
