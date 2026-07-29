"""Projeção operacional do Control e gate de simulação."""
from app import models_db, provisioning
from app.main import app
from app.simulation import MockSimulationProvider, get_simulation_provider


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


def _sim_payload():
    return {
        "cpf": "529.982.247-25",
        "nascimento": "1990-05-20",
        "valor": 20000,
        "entrada": 5000,
        "prazo_meses": 48,
    }


def test_apply_monotonico_stale_e_idempotente(db, loja_a):
    loja_id = loja_a["loja_id"]
    db.query(models_db.LojaOperacionalProjecao).filter_by(loja_id=loja_id).delete()
    db.commit()

    active = _payload(
        loja_a["slug"],
        [
            _envelope(aggregate="loja", version=3, state="ativa", event_id="e-loja-3"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    reasons = provisioning.apply_payload(db, loja_id, active)
    db.commit()
    assert reasons == ["applied", "applied", "applied"]
    assert provisioning.allows_processing(db, loja_id) is True
    assert provisioning.allows_processing(db, loja_id, module="vendas") is True

    same = provisioning.apply_payload(db, loja_id, active)
    db.commit()
    assert same == ["idempotent", "idempotent", "idempotent"]

    suspended = _payload(
        loja_a["slug"],
        [
            _envelope(aggregate="loja", version=4, state="suspensa", event_id="e-loja-4"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    suspend_reasons = provisioning.apply_payload(db, loja_id, suspended)
    db.commit()
    assert "applied" in suspend_reasons
    assert provisioning.allows_processing(db, loja_id) is False
    assert provisioning.allows_processing(db, loja_id, module="vendas") is False

    stale_reasons = provisioning.apply_payload(db, loja_id, active)
    db.commit()
    assert stale_reasons == ["stale", "idempotent", "idempotent"]
    assert provisioning.allows_processing(db, loja_id) is False
    loja_proj = db.get(models_db.LojaOperacionalProjecao, (loja_id, "loja"))
    assert loja_proj is not None
    assert loja_proj.state == "suspensa"
    assert loja_proj.version == 4


def test_allows_processing_fail_closed_sem_projecao(db, loja_a):
    loja_id = loja_a["loja_id"]
    db.query(models_db.LojaOperacionalProjecao).filter_by(loja_id=loja_id).delete()
    db.commit()
    assert provisioning.allows_processing(db, loja_id) is False


def test_endpoint_exige_auth(client, loja_a):
    r = client.post(
        "/v1/internal/provisioning/state",
        json=_payload(loja_a["slug"], []),
    )
    assert r.status_code == 401


def test_endpoint_rejeita_slug_mismatch(client, loja_a):
    r = client.post(
        "/v1/internal/provisioning/state",
        json=_payload(
            "outra-loja",
            [_envelope(aggregate="loja", version=1, state="ativa", event_id="x")],
        ),
        headers=loja_a["headers"],
    )
    assert r.status_code == 403


def test_endpoint_aplica_e_retorna_allows_processing(client, loja_a, db):
    loja_id = loja_a["loja_id"]
    db.query(models_db.LojaOperacionalProjecao).filter_by(loja_id=loja_id).delete()
    db.commit()

    r = client.post(
        "/v1/internal/provisioning/state",
        json=_payload(
            loja_a["slug"],
            [
                _envelope(aggregate="loja", version=2, state="ativa", event_id="api-2"),
                _envelope(aggregate="vendas", version=1, state="ativo", event_id="api-v1"),
            ],
        ),
        headers=loja_a["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reasons"] == ["applied", "applied"]
    assert body["allows_processing"] is True

    db.expire_all()
    proj = db.get(models_db.LojaOperacionalProjecao, (loja_id, "loja"))
    assert proj is not None
    assert proj.state == "ativa"
    assert proj.version == 2


def test_simular_bloqueado_sem_projecao(client, loja_sem_projecao):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json=_sim_payload(),
            headers=loja_sem_projecao["headers"],
        )
        assert r.status_code == 423
        assert r.json()["detail"]["code"] == "store_not_operational"
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_simular_bloqueado_quando_suspensa(client, loja_a, db):
    loja_id = loja_a["loja_id"]
    proj = db.get(models_db.LojaOperacionalProjecao, (loja_id, "loja"))
    proj.state = "suspensa"
    proj.version = 9
    db.commit()

    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json=_sim_payload(),
            headers=loja_a["headers"],
        )
        assert r.status_code == 423
        assert r.json()["detail"]["code"] == "store_not_operational"
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_simular_permitido_quando_loja_ativa(client, loja_a):
    app.dependency_overrides[get_simulation_provider] = lambda: MockSimulationProvider()
    try:
        r = client.post(
            "/v1/simular",
            json=_sim_payload(),
            headers=loja_a["headers"],
        )
        assert r.status_code == 200
        assert r.json()["status"] == "concluida"
    finally:
        app.dependency_overrides.pop(get_simulation_provider, None)


def test_leitura_permanece_aberta_sem_projecao(client, loja_sem_projecao):
    r = client.get("/v1/conversas", headers=loja_sem_projecao["headers"])
    assert r.status_code == 200
