from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload():
    return {
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20"},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": 48},
    }


def test_mesma_chave_e_payload_reusa_recurso():
    headers = {"Idempotency-Key": "chave-abc"}
    r1 = client.post("/v1/simulacoes", json=_payload(), headers=headers)
    r2 = client.post("/v1/simulacoes", json=_payload(), headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_mesma_chave_payload_diferente_conflita():
    headers = {"Idempotency-Key": "chave-xyz"}
    client.post("/v1/simulacoes", json=_payload(), headers=headers)
    outro = _payload()
    outro["condicoes"]["prazo_meses"] = 36
    r = client.post("/v1/simulacoes", json=outro, headers=headers)
    assert r.status_code == 409
    assert r.json()["erro"]["code"] == "idempotency_key_conflito"


def test_persistencia_sobrevive_e_cancelamento():
    criada = client.post("/v1/simulacoes", json=_payload()).json()
    sim_id = criada["id"]

    consulta = client.get(f"/v1/simulacoes/{sim_id}")
    assert consulta.status_code == 200
    assert len(consulta.json()["resultados"]) == 5

    cancel = client.post(f"/v1/simulacoes/{sim_id}/cancelar")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelada"
    assert client.get(f"/v1/simulacoes/{sim_id}").json()["status"] == "cancelada"
