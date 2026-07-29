"""Projeção operacional do Control e gate de novas simulações no Motor."""
from app import models_db, provisioning

# Espelha conftest sem reimportar o módulo (reimport recria o engine de teste).
TEST_CLIENT_ID = "10000000-0000-0000-0000-000000000001"


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
        "referencia_externa": "lead-prov",
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20", "renda": 3000},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": 48},
        "provedores": ["mock"],
    }


def test_apply_monotonico_stale_e_idempotente(db):
    cliente_id = TEST_CLIENT_ID
    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=cliente_id
    ).delete()
    db.commit()

    active = _payload(
        "loja-motor",
        [
            _envelope(aggregate="loja", version=3, state="ativa", event_id="e-loja-3"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    reasons = provisioning.apply_payload(db, cliente_id, active)
    db.commit()
    assert reasons == ["applied", "applied", "applied"]
    assert provisioning.allows_processing(db, cliente_id) is True
    assert provisioning.allows_processing(db, cliente_id, module="vendas") is True

    same = provisioning.apply_payload(db, cliente_id, active)
    db.commit()
    assert same == ["idempotent", "idempotent", "idempotent"]

    suspended = _payload(
        "loja-motor",
        [
            _envelope(aggregate="loja", version=4, state="suspensa", event_id="e-loja-4"),
            _envelope(aggregate="vendas", version=1, state="ativo", event_id="e-vendas-1"),
            _envelope(aggregate="estoque", version=1, state="ativo", event_id="e-estoque-1"),
        ],
    )
    suspend_reasons = provisioning.apply_payload(db, cliente_id, suspended)
    db.commit()
    assert "applied" in suspend_reasons
    assert provisioning.allows_processing(db, cliente_id) is False
    assert provisioning.allows_processing(db, cliente_id, module="vendas") is False

    stale_reasons = provisioning.apply_payload(db, cliente_id, active)
    db.commit()
    assert stale_reasons == ["stale", "idempotent", "idempotent"]
    assert provisioning.allows_processing(db, cliente_id) is False
    loja_proj = db.get(models_db.ClienteOperacionalProjecao, (cliente_id, "loja"))
    assert loja_proj is not None
    assert loja_proj.state == "suspensa"
    assert loja_proj.version == 4


def test_allows_processing_fail_closed_sem_projecao(db):
    cliente_id = TEST_CLIENT_ID
    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=cliente_id
    ).delete()
    db.commit()
    assert provisioning.allows_processing(db, cliente_id) is False
    assert provisioning.allows_processing(db, cliente_id, module="vendas") is False


def test_allows_processing_modulo_vendas_ausente_bloqueia_so_modulo(db):
    cliente_id = TEST_CLIENT_ID
    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=cliente_id, aggregate="vendas"
    ).delete()
    db.commit()
    assert provisioning.allows_processing(db, cliente_id) is True
    assert provisioning.allows_processing(db, cliente_id, module="vendas") is False


def test_endpoint_exige_auth(client):
    r = client.post(
        "/v1/internal/provisioning/state",
        json=_payload("loja-motor", []),
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert r.status_code == 401


def test_endpoint_aplica_e_retorna_allows_processing(client, db):
    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=TEST_CLIENT_ID
    ).delete()
    db.commit()

    r = client.post(
        "/v1/internal/provisioning/state",
        json=_payload(
            "loja-motor",
            [
                _envelope(aggregate="loja", version=2, state="ativa", event_id="api-2"),
                _envelope(aggregate="vendas", version=1, state="ativo", event_id="api-v1"),
            ],
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["reasons"] == ["applied", "applied"]
    assert body["allows_processing"] is True

    db.expire_all()
    proj = db.get(models_db.ClienteOperacionalProjecao, (TEST_CLIENT_ID, "loja"))
    assert proj is not None
    assert proj.state == "ativa"
    assert proj.version == 2
    assert proj.cliente_id == TEST_CLIENT_ID


def test_criar_simulacao_bloqueado_sem_projecao(client, db):
    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=TEST_CLIENT_ID
    ).delete()
    db.commit()

    r = client.post("/v1/simulacoes", json=_sim_payload())
    assert r.status_code == 423
    assert r.json()["erro"]["code"] == "store_not_operational"


def test_criar_simulacao_bloqueado_quando_suspensa(client, db):
    proj = db.get(models_db.ClienteOperacionalProjecao, (TEST_CLIENT_ID, "loja"))
    proj.state = "suspensa"
    proj.version = 9
    db.commit()

    r = client.post("/v1/simulacoes", json=_sim_payload())
    assert r.status_code == 423
    assert r.json()["erro"]["code"] == "store_not_operational"


def test_criar_simulacao_permitido_quando_loja_ativa(client):
    r = client.post("/v1/simulacoes", json=_sim_payload())
    assert r.status_code == 202
    assert r.json()["status"] == "recebida"


def test_leitura_permanece_aberta_sem_projecao(client, db):
    # Cria job com projeção ativa, depois remove projeção e lê.
    criada = client.post("/v1/simulacoes", json=_sim_payload())
    assert criada.status_code == 202
    sim_id = criada.json()["id"]

    db.query(models_db.ClienteOperacionalProjecao).filter_by(
        cliente_id=TEST_CLIENT_ID
    ).delete()
    db.commit()

    r = client.get(f"/v1/simulacoes/{sim_id}")
    assert r.status_code == 200
    assert r.json()["id"] == sim_id

    lista = client.get("/v1/simulacoes")
    assert lista.status_code == 200


def test_cancelar_permanece_aberto_quando_suspensa(client, db):
    criada = client.post("/v1/simulacoes", json=_sim_payload())
    assert criada.status_code == 202
    sim_id = criada.json()["id"]

    proj = db.get(models_db.ClienteOperacionalProjecao, (TEST_CLIENT_ID, "loja"))
    proj.state = "suspensa"
    proj.version = 9
    db.commit()

    r = client.post(f"/v1/simulacoes/{sim_id}/cancelar")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelada"
