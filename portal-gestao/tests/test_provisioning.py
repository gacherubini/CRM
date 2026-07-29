"""Projeção operacional do Control e gate de registro de vendas no Portal."""
from conftest import csrf_da_resposta, login, seed_loja_operacional

from app import provisioning
from app.db import SessionLocal
from app.models import LojaOperacionalProjecao, Venda


SERVICE_TOKEN = "portal-svc-token-test"
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


def test_apply_monotonico_stale_e_idempotente(db):
    slug = "loja-prov"
    db.query(LojaOperacionalProjecao).filter_by(loja_slug=slug).delete()
    db.commit()

    active = _payload(
        slug,
        [
            _envelope(aggregate="loja", version=3, state="ativa", event_id="e-loja-3"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    reasons = provisioning.apply_payload(db, slug, active)
    db.commit()
    assert reasons == ["applied", "applied", "applied"]
    assert provisioning.allows_processing(db, slug) is True
    assert provisioning.allows_processing(db, slug, module="vendas") is True

    same = provisioning.apply_payload(db, slug, active)
    db.commit()
    assert same == ["idempotent", "idempotent", "idempotent"]

    suspended = _payload(
        slug,
        [
            _envelope(aggregate="loja", version=4, state="suspensa", event_id="e-loja-4"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    suspend_reasons = provisioning.apply_payload(db, slug, suspended)
    db.commit()
    assert "applied" in suspend_reasons
    assert provisioning.allows_processing(db, slug) is False
    assert provisioning.allows_processing(db, slug, module="vendas") is False

    stale_reasons = provisioning.apply_payload(db, slug, active)
    db.commit()
    assert stale_reasons == ["stale", "idempotent", "idempotent"]
    assert provisioning.allows_processing(db, slug) is False
    loja_proj = db.get(LojaOperacionalProjecao, (slug, "loja"))
    assert loja_proj is not None
    assert loja_proj.state == "suspensa"
    assert loja_proj.version == 4


def test_allows_processing_fail_closed_sem_projecao(db):
    slug = "sem-projecao"
    db.query(LojaOperacionalProjecao).filter_by(loja_slug=slug).delete()
    db.commit()
    assert provisioning.allows_processing(db, slug) is False
    assert provisioning.allows_processing(db, slug, module="vendas") is False


def test_allows_processing_modulo_ausente_bloqueia_so_modulo(db):
    slug = "loja-mod"
    db.query(LojaOperacionalProjecao).filter_by(loja_slug=slug).delete()
    db.commit()
    seed_loja_operacional(db, loja_slug=slug, state="ativa")
    db.commit()
    assert provisioning.allows_processing(db, slug) is True
    assert provisioning.allows_processing(db, slug, module="vendas") is False


def test_endpoint_desligado_sem_token(client, monkeypatch):
    monkeypatch.delenv("PORTAL_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("PORTAL_PROVISIONING_TOKEN", raising=False)
    r = client.post(ENDPOINT, json=_payload("loja-teste", []))
    assert r.status_code == 503


def test_endpoint_exige_auth(client, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", SERVICE_TOKEN)
    r = client.post(ENDPOINT, json=_payload("loja-teste", []))
    assert r.status_code == 401

    r2 = client.post(
        ENDPOINT,
        json=_payload("loja-teste", []),
        headers=_headers("token-errado"),
    )
    assert r2.status_code == 401


def test_endpoint_exige_loja_slug(client, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", SERVICE_TOKEN)
    body = _payload("loja-teste", [])
    body.pop("loja_slug")
    r = client.post(ENDPOINT, json=body, headers=_headers())
    assert r.status_code == 422


def test_endpoint_aplica_e_retorna_allows_processing(client, db, monkeypatch):
    monkeypatch.setenv("PORTAL_SERVICE_TOKEN", SERVICE_TOKEN)
    slug = "loja-api"
    db.query(LojaOperacionalProjecao).filter_by(loja_slug=slug).delete()
    db.commit()

    r = client.post(
        ENDPOINT,
        json=_payload(
            slug,
            [
                _envelope(aggregate="loja", version=2, state="ativa", event_id="api-2"),
                _envelope(aggregate="vendas", version=1, state="ativo", event_id="api-v1"),
            ],
        ),
        headers=_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reasons"] == ["applied", "applied"]
    assert body["allows_processing"] is True

    db.expire_all()
    proj = db.get(LojaOperacionalProjecao, (slug, "loja"))
    assert proj is not None
    assert proj.state == "ativa"
    assert proj.version == 2
    assert proj.loja_slug == slug


def test_endpoint_aceita_alias_provisioning_token(client, monkeypatch):
    monkeypatch.delenv("PORTAL_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("PORTAL_PROVISIONING_TOKEN", "alias-token")
    r = client.post(
        ENDPOINT,
        json=_payload(
            "loja-alias",
            [_envelope(aggregate="loja", version=1, state="ativa", event_id="a1")],
        ),
        headers=_headers("alias-token"),
    )
    assert r.status_code == 200
    assert r.json()["allows_processing"] is True


def test_vendas_nova_bloqueada_sem_projecao(client, db):
    login(client)
    db.query(LojaOperacionalProjecao).filter_by(loja_slug="loja-teste").delete()
    db.commit()

    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Corolla 2023",
            "preco_venda": "120000.50",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?erro=loja-nao-operacional"
    assert db.query(Venda).filter_by(loja_slug="loja-teste").count() == 0


def test_vendas_nova_bloqueada_quando_suspensa(client, db):
    login(client)
    proj = db.get(LojaOperacionalProjecao, ("loja-teste", "loja"))
    assert proj is not None
    proj.state = "suspensa"
    proj.version = 9
    db.commit()

    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Corolla 2023",
            "preco_venda": "120000.50",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?erro=loja-nao-operacional"
    assert db.query(Venda).filter_by(loja_slug="loja-teste").count() == 0


def test_vendas_nova_permitida_quando_loja_ativa(client):
    login(client)
    pagina = client.get("/app/vendas/nova")
    resposta = client.post(
        "/app/vendas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            "descricao": "Corolla 2023",
            "preco_venda": "120000.50",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/vendas?ok=registrada"

    db = SessionLocal()
    try:
        assert db.query(Venda).filter_by(loja_slug="loja-teste").count() == 1
    finally:
        db.close()


def test_leitura_vendas_permanece_aberta_sem_projecao(client, db):
    login(client)
    db.query(LojaOperacionalProjecao).filter_by(loja_slug="loja-teste").delete()
    db.commit()
    r = client.get("/app/vendas")
    assert r.status_code == 200
