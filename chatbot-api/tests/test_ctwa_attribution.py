from app.servico import aplicar_touch_ctwa, extrair_codigo_ctwa_do_texto


def test_extrair_codigo_ctwa_do_texto():
    assert extrair_codigo_ctwa_do_texto("Olá! Cód: RV-JUL") == "RV-JUL"
    assert extrair_codigo_ctwa_do_texto("ref:seminovos") == "seminovos"
    assert extrair_codigo_ctwa_do_texto("utm_campaign=feirao-ago") == "feirao-ago"
    assert extrair_codigo_ctwa_do_texto("Código: CAT-ABCDEFGH2345") is None
    assert extrair_codigo_ctwa_do_texto("só oi") is None


def test_mensagem_comum_nao_cria_lead(client, loja_a):
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": "5511900009090",
            "texto": "Olá, gostaria de saber o horário.",
            "provider_message_id": "wamid-sem-tracking-1",
            "from_me": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["lead_id"] is None
    assert r.json()["ctwa_atribuido"] is False
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []


def test_webhook_ctwa_enriquece_lead(client, loja_a):
    headers = loja_a["headers"]
    instance = loja_a["instance"]

    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": "5511988877665",
            "texto": "Olá! Tenho interesse. Cód: RV-JUL",
            "provider_message_id": "wamid-ctwa-1",
            "from_me": False,
            "ctwa_clid": "ARActwaClick123",
            "meta_campaign_id": "12033999",
            "meta_ad_id": "12033888",
        },
    )
    assert r.status_code == 200
    assert r.json().get("ctwa_atribuido") is True

    leads = client.get("/v1/leads", headers=headers).json()["leads"]
    lead = next(x for x in leads if "988877665" in x["telefone"])
    assert lead["ctwa_clid"] == "ARActwaClick123"
    assert lead["ctwa_clid_first"] == "ARActwaClick123"
    assert lead["meta_campaign_id"] == "12033999"
    assert lead["ctwa_codigo"] == "RV-JUL"
    assert lead["origem"] == "meta_ctwa"
    assert lead["canal"] == "whatsapp"

    r2 = client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": "5511988877665",
            "texto": "ainda aqui",
            "provider_message_id": "wamid-ctwa-2",
            "from_me": False,
            "ctwa_clid": "ARActwaClick999",
        },
    )
    assert r2.status_code == 200
    lead2 = client.get(f"/v1/leads/{lead['id']}", headers=headers).json()
    assert lead2["ctwa_clid_first"] == "ARActwaClick123"
    assert lead2["ctwa_clid"] == "ARActwaClick999"


def test_webhook_so_codigo_sem_clid(client, loja_a):
    instance = loja_a["instance"]
    r = client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": "5511977766554",
            "texto": "Quero a moto. cod: FAN160",
            "provider_message_id": "wamid-cod-1",
            "from_me": False,
        },
    )
    assert r.status_code == 200
    assert r.json().get("ctwa_atribuido") is True
    leads = client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"]
    lead = next(x for x in leads if "77766554" in x["telefone"])
    assert lead["ctwa_codigo"] == "FAN160"
    assert lead["origem"] == "meta_ctwa"


def test_auditoria_ctwa_lista_evento(client, loja_a):
    instance = loja_a["instance"]
    client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": "5511966655443",
            "texto": "Oi do anúncio",
            "provider_message_id": "wamid-aud-1",
            "from_me": False,
            "ctwa_clid": "ARAlongClickId999999",
            "meta_campaign_id": "camp-77",
            "meta_ad_id": "ad-88",
        },
    )
    r = client.get("/v1/auditoria/ctwa", headers=loja_a["headers"])
    assert r.status_code == 200
    itens = r.json()["itens"]
    assert len(itens) >= 1
    ev = itens[0]
    assert ev["tem_ctwa_clid"] is True
    assert ev["ctwa_clid_sufixo"] == "Id999999" or ev["ctwa_clid_sufixo"].endswith("999999")
    assert ev["meta_campaign_id"] == "camp-77"
    assert ev["meta_ad_id"] == "ad-88"
    assert "****" in ev["telefone_mascarado"] or "***" in ev["telefone_mascarado"]
    assert ev["atribuido_lead"] is True

    so_clid = client.get(
        "/v1/auditoria/ctwa",
        headers=loja_a["headers"],
        params={"so_com_clid": True},
    )
    assert so_clid.status_code == 200
    assert all(i["tem_ctwa_clid"] for i in so_clid.json()["itens"])
