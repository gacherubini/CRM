"""E2E do funil Catálogo -> Chatbot pela camada de entrega real (outbox).

Diferente de `test_catalog_attribution.py`, que posta o payload direto no TestClient, aqui
exercitamos o `process_pending` REAL do Catálogo — os headers Bearer/Idempotency-Key/X-Event-Type
e o retry/backoff que o wiring de deploy (`CATALOGO_EVENTS_URL`/`TOKEN`) liga em produção.

Os dois produtos usam o mesmo pacote top-level `app`, então o Catálogo é carregado por caminho de
arquivo (importlib). `outbox.py` faz `from app.events import InterestStore`, satisfeito injetando o
módulo já carregado em `sys.modules["app.events"]` só durante o teste.
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CATALOG_APP = Path(__file__).parents[2] / "catalogo-publico" / "app"


def _load_by_path(filename: str, modname: str):
    spec = importlib.util.spec_from_file_location(modname, CATALOG_APP / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def catalogo():
    """Módulos reais do Catálogo (events + outbox) carregados por caminho de arquivo."""
    events = _load_by_path("events.py", "catalog_events_e2e")
    sys.modules["app.events"] = events  # satisfaz o import de outbox.py
    try:
        outbox = _load_by_path("outbox.py", "catalog_outbox_e2e")
        yield events, outbox
    finally:
        for name in ("app.events", "catalog_events_e2e", "catalog_outbox_e2e"):
            sys.modules.pop(name, None)


def _token(loja) -> str:
    return loja["headers"]["Authorization"].removeprefix("Bearer ")


EVENTS_PATH = "/v1/integracoes/catalogo/interesses"


def test_outbox_entrega_com_headers_corretos_e_atribui_lead(client, loja_a, tmp_path, catalogo):
    events, outbox = catalogo
    store = events.InterestStore(str(tmp_path / "catalogo.db"))
    store.initialize()
    click = store.record(
        loja_slug=loja_a["slug"],
        veiculo_id="vehicle-outbox",
        visitante_id="anon-1",
        utm_source="google",
        utm_medium="cpc",
        utm_campaign="e2e-outbox",
    )

    captured: dict = {}

    def poster(url, body, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        resp = client.post(url, content=body, headers=headers)
        return resp.status_code, None

    summary = outbox.process_pending(
        store, url=EVENTS_PATH, token=_token(loja_a), poster=poster
    )

    # entrega real ocorreu, com o contrato de headers que o deploy liga
    assert summary["delivered"] == 1
    assert captured["headers"]["Authorization"] == f"Bearer {_token(loja_a)}"
    assert captured["headers"]["Idempotency-Key"] == click.event_id
    assert captured["headers"]["X-Event-Type"] == "catalog.interest_clicked"
    assert store.get_outbox(click.event_id)["status"] == "delivered"

    # atribuição fica pendente: só clique não cria lead
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []

    # a primeira mensagem com a ref correlaciona e enriquece o lead atribuído
    inbound = client.post(
        "/webhook/mensagem",
        json={
            "instance": loja_a["instance"],
            "telefone": "5511977777777",
            "texto": f"Vim do catálogo, código {click.public_ref}",
            "provider_message_id": "E2E-OUTBOX-MSG",
            "from_me": False,
        },
    )
    assert inbound.json()["catalog_interest_ref"] == click.public_ref
    assert client.get("/v1/leads", headers=loja_a["headers"]).json()["leads"] == []
    lead = client.post(
        "/v1/leads",
        json={
            "telefone": "5511977777777",
            "interesse": "simulação de financiamento",
            "etapa": "qualificado",
        },
        headers=loja_a["headers"],
    ).json()
    assert lead["telefone"] == "5511977777777"
    assert lead["veiculo_ref"] == "vehicle-outbox"
    assert lead["catalog_interest_ref"] == click.public_ref
    assert lead["utm_campaign"] == "e2e-outbox"
    assert lead["atribuida_em"]


def test_outbox_retenta_falha_e_reentrega_sem_duplicar(client, loja_a, tmp_path, catalogo):
    events, outbox = catalogo
    store = events.InterestStore(str(tmp_path / "catalogo.db"))
    store.initialize()
    click = store.record(
        loja_slug=loja_a["slug"], veiculo_id="v-retry", visitante_id="anon-2"
    )

    # janela 1: rede cai -> fica pendente para retry, nada entregue
    def poster_falha(url, body, headers, timeout):
        raise RuntimeError("conexao recusada")

    t0 = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    s1 = outbox.process_pending(
        store, url=EVENTS_PATH, token=_token(loja_a), poster=poster_falha, now=t0
    )
    assert s1["retried"] == 1 and s1["delivered"] == 0
    assert store.get_outbox(click.event_id)["status"] == "pending"

    # janela 2 (após backoff): rede volta -> entrega
    def poster_ok(url, body, headers, timeout):
        resp = client.post(url, content=body, headers=headers)
        return resp.status_code, None

    t1 = t0 + timedelta(hours=1)
    s2 = outbox.process_pending(
        store, url=EVENTS_PATH, token=_token(loja_a), poster=poster_ok, now=t1
    )
    assert s2["delivered"] == 1
    assert store.get_outbox(click.event_id)["status"] == "delivered"

    # reentrega do mesmo evento é idempotente no Chatbot (não duplica atribuição)
    first = client.post(
        EVENTS_PATH,
        content=store.get_outbox(click.event_id)["payload"].encode("utf-8"),
        headers=loja_a["headers"] | {"Idempotency-Key": click.event_id},
    )
    assert first.status_code == 202
    assert first.json()["duplicado"] is True


def test_outbox_desligado_quando_token_ausente(loja_a, tmp_path, catalogo):
    """Sem URL/token o worker nem entrega: cliques ficam locais (funil desligado por padrão)."""
    events, outbox = catalogo
    store = events.InterestStore(str(tmp_path / "catalogo.db"))
    store.initialize()
    store.record(loja_slug=loja_a["slug"], veiculo_id="v-off", visitante_id="anon-3")

    summary = outbox.process_pending(store, url="", token="")
    assert summary["delivered"] == 0
    assert summary["not_configured"] == 1
