"""Fase 1 (Task 4): o lead nasce na 2a mensagem de conversa com CTWA pendente."""


def test_segunda_mensagem_ctwa_cria_lead(client, loja_a):
    inst, headers = loja_a["instance"], loja_a["headers"]
    # 1a msg (clique do anuncio) -- NAO cria lead
    r1 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511987654321", "texto": "oi",
        "provider_message_id": "wamid-1", "from_me": False,
        "ctwa_clid": "ARclid1", "meta_ad_id": "120252470707220341"})
    assert r1.status_code == 200
    assert client.get("/v1/leads", headers=headers).json()["leads"] == []
    # 2a msg (cliente respondeu de verdade) -- cria lead com o ad_id
    r2 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511987654321", "texto": "quero saber o preço",
        "provider_message_id": "wamid-2", "from_me": False})
    assert r2.status_code == 200
    assert r2.json().get("lead_criado_auto") is True
    leads = client.get("/v1/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    assert leads[0]["meta_ad_id"] == "120252470707220341"
    assert leads[0]["origem"] == "meta_ctwa"


def test_segunda_mensagem_sem_ctwa_nao_cria_lead(client, loja_a):
    inst, headers = loja_a["instance"], loja_a["headers"]
    for i in (1, 2):
        client.post("/webhook/mensagem", json={
            "instance": inst, "telefone": "5511900000000", "texto": "oi",
            "provider_message_id": f"nctwa-{i}", "from_me": False})
    assert client.get("/v1/leads", headers=headers).json()["leads"] == []


def test_terceira_mensagem_ctwa_nao_duplica_lead(client, loja_a):
    """Idempotencia: apos criar na 2a, a 3a nao cria outro lead nem re-sinaliza."""
    inst, headers = loja_a["instance"], loja_a["headers"]
    client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511911112222", "texto": "oi",
        "provider_message_id": "dup-1", "from_me": False,
        "ctwa_clid": "ARclidDup", "meta_ad_id": "120252470707220341"})
    r2 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511911112222", "texto": "quero saber",
        "provider_message_id": "dup-2", "from_me": False})
    assert r2.json().get("lead_criado_auto") is True
    r3 = client.post("/webhook/mensagem", json={
        "instance": inst, "telefone": "5511911112222", "texto": "ainda aqui",
        "provider_message_id": "dup-3", "from_me": False})
    assert r3.status_code == 200
    # a 3a mensagem nao cria um novo lead
    assert r3.json().get("lead_criado_auto") is False
    leads = client.get("/v1/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
