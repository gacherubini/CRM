from conftest import csrf_da_resposta, login

_CAMPOS = {
    "tipo": "moto", "marca": "Honda", "modelo": "CG 160", "versao": "Fan",
    "ano_modelo": "2022", "cor": "Preta", "km": "10000", "preco": "15900",
    "custo": "12000", "codigo_interno": "H01", "foto_url": "", "placa": "ABC1D23",
}


def test_upload_de_foto_no_cadastro_chama_estoque(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        files={"foto": ("moto.jpg", b"\xff\xd8fakejpeg", "image/jpeg")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303  # sucesso → redirect
    assert estoque_fake.fotos, "adicionar_foto deveria ter sido chamado"
    chamada = estoque_fake.fotos[-1]
    assert chamada["content_type"] == "image/jpeg"
    assert chamada["conteudo"] == b"\xff\xd8fakejpeg"
    assert chamada["idempotency_key"].startswith("portal-foto:")


def test_upload_de_mime_invalido_mostra_erro(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        files={"foto": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        follow_redirects=False,
    )
    assert resposta.status_code == 422
    assert "Formato de foto inválido" in resposta.text


def test_cadastro_sem_arquivo_nao_chama_upload(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert not estoque_fake.fotos


def test_form_tem_input_de_arquivo(client):
    login(client)
    pagina = client.get("/app/estoque/novo")
    assert 'enctype="multipart/form-data"' in pagina.text
    assert 'type="file"' in pagina.text and 'name="foto"' in pagina.text
