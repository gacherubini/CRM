"""Projeção operacional do Control e gate 404/HIDE da vitrine pública."""
from app import provisioning as provisioning_mod
from app.provisioning import ProvisioningStore


SERVICE_TOKEN = "catalogo-svc-token-test"
ENDPOINT = "/internal/v1/provisioning/state"


def _envelope(
    *,
    aggregate: str,
    version: int,
    state: str,
    event_id: str,
    loja_id: str = "control-loja",
):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "loja_id": loja_id,
        "aggregate": aggregate,
        "version": version,
        "state": state,
        "effective_at": "2026-07-29T12:00:00+00:00",
        "occurred_at": "2026-07-29T12:00:00+00:00",
        "reason": None,
    }


def _payload(slug: str, operational: list[dict]):
    return {
        "schema_version": 1,
        "loja_id": "control-uuid",
        "loja_slug": slug,
        "operational": operational,
        "people": [],
        "roles": [],
    }


def _headers(token: str = SERVICE_TOKEN):
    return {"X-Service-Token": token}


def _seed_ativa(store: ProvisioningStore, slug: str = "moto-center"):
    store.apply_payload(
        slug,
        _payload(
            slug,
            [
                _envelope(
                    aggregate="loja", version=1, state="ativa", event_id="loja-1"
                ),
                _envelope(
                    aggregate="estoque",
                    version=1,
                    state="ativo",
                    event_id="estoque-1",
                ),
            ],
        ),
    )


def test_apply_monotonico_stale_e_idempotente(provisioning_store):
    slug = "loja-prov"
    active = _payload(
        slug,
        [
            _envelope(aggregate="loja", version=3, state="ativa", event_id="e-loja-3"),
            _envelope(
                aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"
            ),
            _envelope(
                aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"
            ),
        ],
    )
    reasons = provisioning_store.apply_payload(slug, active)
    assert reasons == ["applied", "applied", "applied"]
    assert provisioning_store.allows_processing(slug) is True
    assert provisioning_store.allows_processing(slug, module="estoque") is True

    same = provisioning_store.apply_payload(slug, active)
    assert same == ["idempotent", "idempotent", "idempotent"]

    suspended = _payload(
        slug,
        [
            _envelope(
                aggregate="loja", version=4, state="suspensa", event_id="e-loja-4"
            ),
            _envelope(
                aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"
            ),
            _envelope(
                aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"
            ),
        ],
    )
    suspend_reasons = provisioning_store.apply_payload(slug, suspended)
    assert "applied" in suspend_reasons
    assert provisioning_store.allows_processing(slug) is False
    assert provisioning_store.allows_processing(slug, module="estoque") is False

    stale_reasons = provisioning_store.apply_payload(slug, active)
    assert stale_reasons == ["stale", "idempotent", "idempotent"]
    assert provisioning_store.allows_processing(slug) is False
    loja_proj = provisioning_store.get(slug, "loja")
    assert loja_proj is not None
    assert loja_proj["state"] == "suspensa"
    assert loja_proj["version"] == 4


def test_allows_processing_fail_open_sem_projecao(provisioning_store):
    """Catálogo: sem projeção a vitrine permanece visível (cutover).

    Differe do Chatbot/Estoque, que falham fechado sem projeção.
    """
    slug = "sem-projecao"
    assert provisioning_store.get(slug, "loja") is None
    assert provisioning_store.allows_processing(slug) is True
    assert provisioning_store.allows_processing(slug, module="estoque") is True


def test_allows_processing_modulo_estoque_ausente_bloqueia_com_loja_projetada(
    provisioning_store,
):
    slug = "loja-mod"
    provisioning_store.apply_payload(
        slug,
        _payload(
            slug,
            [
                _envelope(
                    aggregate="loja", version=1, state="ativa", event_id="l1"
                ),
            ],
        ),
    )
    assert provisioning_store.allows_processing(slug) is True
    assert provisioning_store.allows_processing(slug, module="estoque") is False


def test_endpoint_desligado_sem_token(client, monkeypatch):
    monkeypatch.delenv("CATALOGO_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("CATALOGO_PROVISIONING_TOKEN", raising=False)
    from app import main as main_mod
    from dataclasses import fields
    from app.config import Settings, settings as base

    valores = {f.name: getattr(base, f.name) for f in fields(base)}
    valores["service_token"] = ""
    monkeypatch.setattr(main_mod, "settings", Settings(**valores))

    r = client.post(ENDPOINT, json=_payload("loja-teste", []))
    assert r.status_code == 503


def test_endpoint_exige_auth(client, monkeypatch):
    monkeypatch.setenv("CATALOGO_SERVICE_TOKEN", SERVICE_TOKEN)
    r = client.post(ENDPOINT, json=_payload("loja-teste", []))
    assert r.status_code == 401

    r2 = client.post(
        ENDPOINT,
        json=_payload("loja-teste", []),
        headers=_headers("token-errado"),
    )
    assert r2.status_code == 401


def test_endpoint_exige_loja_slug(client, monkeypatch):
    monkeypatch.setenv("CATALOGO_SERVICE_TOKEN", SERVICE_TOKEN)
    body = _payload("loja-teste", [])
    body.pop("loja_slug")
    r = client.post(ENDPOINT, json=body, headers=_headers())
    assert r.status_code == 422


def test_endpoint_aplica_e_retorna_allows_processing(
    client, provisioning_store, monkeypatch
):
    monkeypatch.setenv("CATALOGO_SERVICE_TOKEN", SERVICE_TOKEN)
    slug = "loja-api"

    r = client.post(
        ENDPOINT,
        json=_payload(
            slug,
            [
                _envelope(aggregate="loja", version=2, state="ativa", event_id="api-2"),
                _envelope(
                    aggregate="estoque", version=1, state="ativo", event_id="api-e1"
                ),
            ],
        ),
        headers=_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reasons"] == ["applied", "applied"]
    assert body["allows_processing"] is True

    proj = provisioning_store.get(slug, "loja")
    assert proj is not None
    assert proj["state"] == "ativa"
    assert proj["version"] == 2
    assert proj["loja_slug"] == slug


def test_endpoint_aceita_alias_provisioning_token(client, monkeypatch):
    monkeypatch.delenv("CATALOGO_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("CATALOGO_PROVISIONING_TOKEN", "alias-token")
    r = client.post(
        ENDPOINT,
        json=_payload(
            "loja-alias",
            [
                _envelope(aggregate="loja", version=1, state="ativa", event_id="a1"),
                _envelope(
                    aggregate="estoque", version=1, state="ativo", event_id="a-e1"
                ),
            ],
        ),
        headers=_headers("alias-token"),
    )
    assert r.status_code == 200
    assert r.json()["allows_processing"] is True


def test_vitrine_permanece_aberta_sem_projecao(client):
    """Fail-open: cutover sem Control não derruba o catálogo."""
    r = client.get("/l/moto-center")
    assert r.status_code == 200
    assert "Honda CG 160" in r.text


def test_vitrine_oculta_quando_loja_suspensa(client, provisioning_store):
    provisioning_store.apply_payload(
        "moto-center",
        _payload(
            "moto-center",
            [
                _envelope(
                    aggregate="loja", version=5, state="suspensa", event_id="s5"
                ),
                _envelope(
                    aggregate="estoque", version=1, state="ativo", event_id="e1"
                ),
            ],
        ),
    )
    r = client.get("/l/moto-center")
    assert r.status_code == 404
    assert "Loja não encontrada" in r.text
    assert "suspens" not in r.text.lower()


def test_detalhe_e_interesse_ocultos_quando_estoque_suspenso(
    client, provisioning_store, interest_store
):
    _seed_ativa(provisioning_store, "moto-center")
    provisioning_store.apply_payload(
        "moto-center",
        _payload(
            "moto-center",
            [
                _envelope(
                    aggregate="estoque",
                    version=2,
                    state="suspenso",
                    event_id="est-susp",
                ),
            ],
        ),
    )
    detalhe = client.get("/l/moto-center/veiculos/vehicle-1")
    assert detalhe.status_code == 404
    assert "Loja não encontrada" in detalhe.text

    interesse = client.get(
        "/l/moto-center/interesse/vehicle-1", follow_redirects=False
    )
    assert interesse.status_code == 404
    assert interest_store.count() == 0


def test_vitrine_visivel_quando_operacional(client, provisioning_store):
    _seed_ativa(provisioning_store, "moto-center")
    r = client.get("/l/moto-center")
    assert r.status_code == 200
    assert "Honda CG 160" in r.text

    d = client.get("/l/moto-center/veiculos/vehicle-1")
    assert d.status_code == 200


def test_docstring_documenta_fail_open():
    doc = provisioning_mod.__doc__ or ""
    assert "fail-open" in doc.lower() or "Fail-open" in doc
    assert "Chatbot" in doc or "fail-closed" in doc.lower()
