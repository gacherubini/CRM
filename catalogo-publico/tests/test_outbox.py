import json
from datetime import datetime, timedelta, timezone

from app.outbox import process_pending


def _record(store):
    store.initialize()
    return store.record(
        loja_slug="moto-center",
        veiculo_id="vehicle-1",
        visitante_id="visitor-local-only",
        origem="detalhe_catalogo",
        utm_source="instagram",
        utm_medium="social",
        utm_campaign="feirao",
        utm_content="story-a",
        utm_term="moto",
    )


def test_clique_e_outbox_sao_atomicos_e_payload_nao_tem_identidade(interest_store):
    record = _record(interest_store)
    interest = interest_store.get_interest(record.event_id)
    outbox = interest_store.get_outbox(record.event_id)
    payload = json.loads(outbox["payload"])

    assert interest["public_ref"] == record.public_ref
    assert record.public_ref.startswith("CAT-")
    assert payload["catalog_interest_ref"] == record.public_ref
    assert payload["event_type"] == "catalog.interest_clicked"
    assert payload["origem"] == "catalogo_publico"
    assert payload["canal"] == "whatsapp"
    assert payload["utm_content"] == "story-a"
    assert "visitante_id" not in payload
    assert "telefone" not in payload


def test_outbox_entrega_com_bearer_e_idempotency_key(interest_store):
    record = _record(interest_store)
    calls = []

    def poster(url, body, headers, timeout):
        calls.append((url, json.loads(body), headers, timeout))
        return 202, None

    result = process_pending(
        interest_store,
        url="https://chatbot.example/v1/integracoes/catalogo/interesses",
        token="server-secret",
        timeout=2,
        poster=poster,
    )
    assert result["delivered"] == 1
    assert calls[0][2]["Authorization"] == "Bearer server-secret"
    assert calls[0][2]["Idempotency-Key"] == record.event_id
    assert calls[0][1]["event_id"] == record.event_id
    assert interest_store.get_outbox(record.event_id)["status"] == "delivered"


def test_outbox_retry_timeout_preserva_event_id_e_descarta_no_limite(interest_store):
    record = _record(interest_store)
    calls = []

    def timeout(url, body, headers, request_timeout):
        calls.append(headers["Idempotency-Key"])
        raise TimeoutError("timeout")

    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    first = process_pending(
        interest_store,
        url="https://chatbot.example/events",
        token="secret",
        max_attempts=2,
        now=now,
        poster=timeout,
    )
    assert first["retried"] == 1
    assert interest_store.get_outbox(record.event_id)["status"] == "pending"

    second = process_pending(
        interest_store,
        url="https://chatbot.example/events",
        token="secret",
        max_attempts=2,
        now=now + timedelta(minutes=1),
        poster=timeout,
    )
    assert second["discarded"] == 1
    assert calls == [record.event_id, record.event_id]
    row = interest_store.get_outbox(record.event_id)
    assert row["status"] == "discarded"
    assert row["attempts"] == 2


def test_outbox_sem_configuracao_mantem_pendente(interest_store):
    record = _record(interest_store)
    result = process_pending(interest_store, url="", token="")
    assert result["not_configured"] == 1
    assert interest_store.get_outbox(record.event_id)["attempts"] == 0
