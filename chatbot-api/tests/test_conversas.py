def _enviar(client, instance, telefone, texto, mid, from_me=False):
    return client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": telefone,
            "texto": texto,
            "provider_message_id": mid,
            "from_me": from_me,
        },
    )


def test_listar_conversas_ordenadas_com_preview(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    _enviar(client, inst, "5511100000001", "oi da conversa 1", "A1")
    _enviar(client, inst, "5511100000002", "oi da conversa 2", "A2")
    # nova mensagem na conversa 1 a torna a mais recente
    _enviar(client, inst, "5511100000001", "voltei na conversa 1", "A3")

    r = client.get("/v1/conversas", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 50 and body["offset"] == 0
    conversas = body["conversas"]
    assert [c["telefone"] for c in conversas] == ["5511100000001", "5511100000002"]
    assert conversas[0]["ultima_mensagem"]["texto"] == "voltei na conversa 1"
    assert conversas[0]["ultima_mensagem"]["direcao"] == "entrada"
    assert conversas[0]["ultima_mensagem"]["criada_em"] is not None
    assert set(conversas[0]) == {
        "id",
        "telefone",
        "bot_ativo",
        "status",
        "atualizada_em",
        "ultima_mensagem",
        "canal_id",
        "evolution_instance",
        "canal_label",
        "numero_mascarado",
        "canal_ativo",
        "canal_estado",
    }


def test_paginacao_conversas(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    for i in range(5):
        _enviar(client, inst, f"551150000000{i}", f"msg {i}", f"P{i}")

    pagina1 = client.get("/v1/conversas?limit=2&offset=0", headers=h).json()
    pagina2 = client.get("/v1/conversas?limit=2&offset=2", headers=h).json()
    assert len(pagina1["conversas"]) == 2
    assert pagina1["limit"] == 2 and pagina2["offset"] == 2
    ids1 = {c["id"] for c in pagina1["conversas"]}
    ids2 = {c["id"] for c in pagina2["conversas"]}
    assert ids1.isdisjoint(ids2)


def test_busca_por_telefone(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    _enviar(client, inst, "5511988880000", "achar", "B1")
    _enviar(client, inst, "5521977770000", "outro", "B2")

    r = client.get("/v1/conversas?busca=98888", headers=h).json()
    assert [c["telefone"] for c in r["conversas"]] == ["5511988880000"]


def test_mensagens_ordenadas_asc(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    tel = "5511911112222"
    _enviar(client, inst, tel, "primeira", "M1")
    _enviar(client, inst, tel, "segunda", "M2", from_me=True)
    _enviar(client, inst, tel, "terceira", "M3")

    r = client.get(f"/v1/conversas/{tel}/mensagens", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["telefone"] == tel
    assert body["limit"] == 100 and body["offset"] == 0
    textos = [m["texto"] for m in body["mensagens"]]
    assert textos == ["primeira", "segunda", "terceira"]
    assert body["mensagens"][1]["direcao"] == "saida"


def test_mensagens_paginacao(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    tel = "5511933334444"
    for i in range(4):
        _enviar(client, inst, tel, f"m{i}", f"MP{i}")

    r = client.get(f"/v1/conversas/{tel}/mensagens?limit=2&offset=2", headers=h).json()
    assert [m["texto"] for m in r["mensagens"]] == ["m2", "m3"]


def test_mensagens_conversa_desconhecida_404(client, loja_a):
    r = client.get("/v1/conversas/5511000000000/mensagens", headers=loja_a["headers"])
    assert r.status_code == 404


def test_conversas_isoladas_por_loja(client, loja_a, loja_b):
    _enviar(client, loja_a["instance"], "5511100000009", "da loja a", "T1")

    minhas = client.get("/v1/conversas", headers=loja_a["headers"]).json()["conversas"]
    outras = client.get("/v1/conversas", headers=loja_b["headers"]).json()["conversas"]
    assert len(minhas) == 1
    assert outras == []

    # loja B não acessa a conversa da loja A nem por telefone
    r = client.get(
        "/v1/conversas/5511100000009/mensagens", headers=loja_b["headers"]
    )
    assert r.status_code == 404


def test_cpf_mascarado_na_ingestao_e_saida(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    tel = "5511977778888"
    _enviar(client, inst, tel, "meu cpf é 111.444.777-35 e o avulso 11144477735", "CPF1")

    body = client.get(f"/v1/conversas/{tel}/mensagens", headers=h).json()
    texto = body["mensagens"][0]["texto"]
    assert "111.444.777-35" not in texto
    assert "11144477735" not in texto
    assert "***.***.***-35" in texto
    assert "*********35" in texto


def test_saida_nao_expoe_provider_message_id(client, loja_a):
    inst, h = loja_a["instance"], loja_a["headers"]
    tel = "5511955556666"
    _enviar(client, inst, tel, "segredo", "SECRET-123")

    conversas = client.get("/v1/conversas", headers=h).text
    mensagens = client.get(f"/v1/conversas/{tel}/mensagens", headers=h).text
    assert "SECRET-123" not in conversas
    assert "SECRET-123" not in mensagens
    assert "provider_message_id" not in conversas
    assert "provider_message_id" not in mensagens
