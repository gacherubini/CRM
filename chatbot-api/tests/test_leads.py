def test_lead_com_nome_sem_consentimento(client, loja_a):
    h = loja_a["headers"]
    tel = "5511988887777"
    # consentimento não é mais obrigatório: o nome é gravado direto
    r = client.post("/v1/leads", json={"telefone": tel, "nome": "Fulano"}, headers=h)
    assert r.status_code == 201
    assert r.json()["nome"] == "Fulano"
    assert r.json()["consentimento_em"] is None


def test_interesse_sem_nome_nao_exige_consentimento(client, loja_a):
    h = loja_a["headers"]
    r = client.post(
        "/v1/leads",
        json={"telefone": "5511900000000", "interesse": "CG 160 2023"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["interesse"] == "CG 160 2023"
    assert r.json()["consentimento_em"] is None


def test_consentimento_depois_lead_com_nome(client, loja_a):
    h = loja_a["headers"]
    tel = "5511988887777"
    cons = client.post(
        "/v1/consentimentos",
        json={"telefone": tel, "versao_texto": "Aceito os termos v1"},
        headers=h,
    )
    assert cons.status_code == 201
    assert cons.json()["consentimento_em"] is not None

    lead = client.post("/v1/leads", json={"telefone": tel, "nome": "Fulano"}, headers=h)
    assert lead.status_code == 201
    assert lead.json()["nome"] == "Fulano"


def test_listar_e_isolamento_por_loja(client, loja_a, loja_b):
    ha, hb = loja_a["headers"], loja_b["headers"]
    client.post("/v1/leads", json={"telefone": "5511111111111", "interesse": "Onix"}, headers=ha)

    assert len(client.get("/v1/leads", headers=ha).json()["leads"]) == 1
    assert client.get("/v1/leads", headers=hb).json()["leads"] == []


def test_obter_lead_de_outra_loja_404(client, loja_a, loja_b):
    lid = client.post(
        "/v1/leads", json={"telefone": "5511111111111", "interesse": "x"}, headers=loja_a["headers"]
    ).json()["id"]
    assert client.get(f"/v1/leads/{lid}", headers=loja_b["headers"]).status_code == 404


def test_atualizar_etapa_do_lead(client, loja_a):
    headers = loja_a["headers"]
    lead_id = client.post(
        "/v1/leads",
        json={"telefone": "5511999990000", "interesse": "Civic"},
        headers=headers,
    ).json()["id"]

    resposta = client.patch(
        f"/v1/leads/{lead_id}/etapa",
        json={"etapa": "qualificado"},
        headers=headers,
    )

    assert resposta.status_code == 200
    assert resposta.json()["etapa"] == "qualificado"
    assert client.get(f"/v1/leads/{lead_id}", headers=headers).json()["etapa"] == "qualificado"


def test_atualizar_etapa_rejeita_valor_fora_da_allowlist(client, loja_a):
    headers = loja_a["headers"]
    lead_id = client.post(
        "/v1/leads", json={"telefone": "5511888880000"}, headers=headers
    ).json()["id"]

    resposta = client.patch(
        f"/v1/leads/{lead_id}/etapa",
        json={"etapa": "etapa_inventada"},
        headers=headers,
    )

    assert resposta.status_code == 422
    assert client.get(f"/v1/leads/{lead_id}", headers=headers).json()["etapa"] == "novo"


def test_atualizar_etapa_de_outra_loja_retorna_404(client, loja_a, loja_b):
    lead_id = client.post(
        "/v1/leads",
        json={"telefone": "5511777770000"},
        headers=loja_a["headers"],
    ).json()["id"]

    resposta = client.patch(
        f"/v1/leads/{lead_id}/etapa",
        json={"etapa": "perdido"},
        headers=loja_b["headers"],
    )

    assert resposta.status_code == 404
    assert client.get(f"/v1/leads/{lead_id}", headers=loja_a["headers"]).json()["etapa"] == "novo"


def test_criar_lead_rejeita_etapa_fora_da_allowlist(client, loja_a):
    resposta = client.post(
        "/v1/leads",
        json={"telefone": "5511666660000", "etapa": "invalida"},
        headers=loja_a["headers"],
    )

    assert resposta.status_code == 422


def test_exportar_leads_csv(client, loja_a):
    h = loja_a["headers"]
    client.post("/v1/leads", json={"telefone": "5511222223333", "interesse": "Onix"}, headers=h)
    r = client.get("/v1/leads.csv", headers=h)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "telefone" in r.text and "5511222223333" in r.text
