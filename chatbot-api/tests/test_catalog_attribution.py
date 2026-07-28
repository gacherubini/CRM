import uuid
import importlib.util
import sys
from pathlib import Path
from datetime import datetime, timezone


REF = "CAT-ABCDEFGH2345"


def _event(loja, *, event_id=None, ref=REF):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "catalog.interest_clicked",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "loja_slug": loja["slug"],
        "catalog_interest_ref": ref,
        "veiculo_ref": "vehicle-123",
        "origem": "catalogo_publico",
        "canal": "whatsapp",
        "utm_source": "instagram",
        "utm_medium": "social",
        "utm_campaign": "feirao",
        "utm_content": "story-a",
        "utm_term": "suv-usado",
    }


def _message(loja, phone, text, message_id):
    return {
        "instance": loja["instance"],
        "telefone": phone,
        "texto": text,
        "provider_message_id": message_id,
        "from_me": False,
    }


def _qualify(client, loja, phone):
    response = client.post(
        "/v1/leads",
        json={
            "telefone": phone,
            "interesse": "simulação de financiamento",
            "etapa": "qualificado",
        },
        headers=loja["headers"],
    )
    assert response.status_code == 201
    return response.json()


def test_clique_nao_cria_lead_e_ingestao_e_idempotente(client, loja_a):
    event = _event(loja_a)
    headers = loja_a["headers"] | {"Idempotency-Key": event["event_id"]}
    first = client.post("/v1/integracoes/catalogo/interesses", json=event, headers=headers)
    second = client.post("/v1/integracoes/catalogo/interesses", json=event, headers=headers)
    assert first.status_code == 202
    assert first.json()["duplicado"] is False
    assert second.status_code == 202
    assert second.json() == {"duplicado": True, "atribuicao_id": first.json()["atribuicao_id"]}
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []


def test_primeira_mensagem_correlaciona_ref_e_enriquece_lead(client, loja_a):
    event = _event(loja_a)
    event["fbclid"] = "IwAR0test"
    client.post("/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"])

    inbound = client.post(
        "/webhook/mensagem",
        json=_message(
            loja_a,
            "5511900001111",
            f"Olá, vim pelo catálogo. código {REF.lower()}",
            "CAT-MSG-1",
        ),
    )
    assert inbound.status_code == 200
    assert inbound.json()["catalog_interest_ref"] == REF

    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    _qualify(client, loja_a, "5511900001111")
    leads = client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["telefone"] == "5511900001111"
    assert lead["catalog_interest_ref"] == REF
    assert lead["veiculo_ref"] == "vehicle-123"
    assert lead["origem"] == "catalogo_publico"
    assert lead["canal"] == "whatsapp"
    assert lead["utm_source"] == "instagram"
    assert lead["utm_medium"] == "social"
    assert lead["utm_campaign"] == "feirao"
    assert lead["utm_campaign_first"] == "feirao"
    assert lead["utm_campaign_last"] == "feirao"
    assert lead["utm_content"] == "story-a"
    assert lead["utm_term"] == "suv-usado"
    assert lead["fbclid"] == "IwAR0test"
    assert lead["atribuida_em"]
    detail = client.get(f"/v1/leads/{lead['id']}", headers=loja_a["headers"]).json()
    assert detail["catalog_interest_ref"] == REF


def test_referencia_catalogo_com_rotulo_codigo_nao_vira_ctwa(client, loja_a):
    event = _event(loja_a)
    client.post("/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"])

    inbound = client.post(
        "/webhook/mensagem",
        json=_message(
            loja_a,
            "5511900001212",
            f"Olá! Código: {REF}",
            "CAT-NAO-CTWA-1",
        ),
    )
    assert inbound.status_code == 200
    assert inbound.json()["catalog_interest_ref"] == REF
    assert inbound.json()["ctwa_atribuido"] is False

    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    lead = _qualify(client, loja_a, "5511900001212")
    assert lead["origem"] == "catalogo_publico"
    assert lead["ctwa_codigo"] is None
    assert lead["ctwa_atribuido_em"] is None


def test_segunda_atribuicao_preserva_first_atualiza_last(client, loja_a):
    # Refs no alfabeto CAT-[A-Z2-7]{10,16}
    ref1 = "CAT-ABCDEFGH2345"
    ref2 = "CAT-JKLMNPQRSTUV"
    e1 = _event(loja_a, ref=ref1)
    e1["utm_campaign"] = "feirao"
    e2 = _event(loja_a, ref=ref2)
    e2["utm_campaign"] = "feirao-blackfriday"
    e2["utm_source"] = "google"
    r1 = client.post("/v1/integracoes/catalogo/interesses", json=e1, headers=loja_a["headers"])
    assert r1.status_code == 202
    client.post(
        "/webhook/mensagem",
        json=_message(loja_a, "5511900002222", f"código {ref1}", "MSG-FT-1"),
    )
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    _qualify(client, loja_a, "5511900002222")
    r2 = client.post("/v1/integracoes/catalogo/interesses", json=e2, headers=loja_a["headers"])
    assert r2.status_code == 202
    client.post(
        "/webhook/mensagem",
        json=_message(loja_a, "5511900002222", f"voltei {ref2}", "MSG-FT-2"),
    )
    leads = client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"]
    lead = next(l for l in leads if l["telefone"] == "5511900002222")
    assert lead["utm_campaign_first"] == "feirao"
    assert lead["utm_campaign_last"] == "feirao-blackfriday"
    assert lead["utm_campaign"] == "feirao-blackfriday"
    assert lead["utm_source_last"] == "google"


def test_ref_nao_cruza_tenant_nem_e_transferida_para_outro_telefone(
    client, loja_a, loja_b
):
    event = _event(loja_a)
    client.post("/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"])

    other_store = client.post(
        "/webhook/mensagem",
        json=_message(loja_b, "5511911111111", f"Código {REF}", "OTHER-STORE"),
    )
    assert other_store.json()["catalog_interest_ref"] is None
    assert client.get("/v1/leads", headers=loja_b["headers"]).json()["leads"] == []

    client.post(
        "/webhook/mensagem",
        json=_message(loja_a, "5511922222222", f"Código {REF}", "OWNER-1"),
    )
    forwarded = client.post(
        "/webhook/mensagem",
        json=_message(loja_a, "5511933333333", f"Código {REF}", "FORWARDED-1"),
    )
    assert forwarded.json()["catalog_interest_ref"] is None
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    _qualify(client, loja_a, "5511922222222")
    leads = client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"]
    assert [lead["telefone"] for lead in leads] == ["5511922222222"]


def test_ingestao_valida_tenant_idempotency_e_timezone(client, loja_a, loja_b):
    wrong_tenant = _event(loja_b)
    assert client.post(
        "/v1/integracoes/catalogo/interesses",
        json=wrong_tenant,
        headers=loja_a["headers"],
    ).status_code == 403

    event = _event(loja_a)
    bad_key = loja_a["headers"] | {"Idempotency-Key": str(uuid.uuid4())}
    assert client.post(
        "/v1/integracoes/catalogo/interesses", json=event, headers=bad_key
    ).status_code == 422

    event["occurred_at"] = "2026-07-12T12:00:00"
    assert client.post(
        "/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"]
    ).status_code == 422


def test_mensagem_outbound_nao_correlaciona(client, loja_a):
    event = _event(loja_a)
    client.post("/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"])
    message = _message(loja_a, "5511944444444", f"Código {REF}", "OUTBOUND-1")
    message["from_me"] = True
    response = client.post("/webhook/mensagem", json=message)
    assert response.json()["catalog_interest_ref"] is None
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []


def test_evento_atrasado_correlaciona_mensagem_inbound_ja_persistida(client, loja_a):
    client.post(
        "/webhook/mensagem",
        json=_message(
            loja_a,
            "5511900000000",
            f"Não é uma ref com limite válido: X{REF}Z",
            "INVALID-EARLY-REF",
        ),
    )
    client.post(
        "/webhook/mensagem",
        json=_message(
            loja_a,
            "5511955555555",
            f"Cheguei primeiro com o código {REF}",
            "EARLY-MESSAGE-1",
        ),
    )
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []

    event = _event(loja_a)
    response = client.post(
        "/v1/integracoes/catalogo/interesses", json=event, headers=loja_a["headers"]
    )
    assert response.status_code == 202
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    _qualify(client, loja_a, "5511955555555")
    leads = client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"]
    assert len(leads) == 1
    assert leads[0]["telefone"] == "5511955555555"
    assert leads[0]["catalog_interest_ref"] == REF


def test_e2e_fake_clique_evento_mensagem_lead(client, loja_a, tmp_path):
    """Usa o gerador real do Catálogo e a ingestão real do Chatbot, sem rede externa."""
    events_path = Path(__file__).parents[2] / "catalogo-publico" / "app" / "events.py"
    spec = importlib.util.spec_from_file_location("catalog_events_e2e", events_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    catalog_store = module.InterestStore(str(tmp_path / "catalog-e2e.db"))
    catalog_store.initialize()
    click = catalog_store.record(
        loja_slug=loja_a["slug"],
        veiculo_id="vehicle-e2e",
        visitante_id="anonymous-local",
        origem="detalhe_catalogo",
        utm_source="google",
        utm_medium="cpc",
        utm_campaign="e2e",
    )
    assert "telefone" not in click.payload
    assert "visitante_id" not in click.payload

    ingest = client.post(
        "/v1/integracoes/catalogo/interesses",
        json=click.payload,
        headers=loja_a["headers"] | {"Idempotency-Key": click.event_id},
    )
    assert ingest.status_code == 202
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []

    inbound = client.post(
        "/webhook/mensagem",
        json=_message(
            loja_a,
            "5511966666666",
            f"Quero continuar o atendimento. Código {click.public_ref}",
            "E2E-CATALOG-MESSAGE",
        ),
    )
    assert inbound.json()["catalog_interest_ref"] == click.public_ref
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    lead = _qualify(client, loja_a, "5511966666666")
    assert lead["telefone"] == "5511966666666"
    assert lead["veiculo_ref"] == "vehicle-e2e"
    assert lead["utm_campaign"] == "e2e"
