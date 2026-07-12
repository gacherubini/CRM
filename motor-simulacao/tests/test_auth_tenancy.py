import uuid

from fastapi.testclient import TestClient

from app.auth import hash_token
from app.main import app
from app.models_db import ClienteApiORM, CredencialApiORM, IdempotenciaORM, SimulacaoORM


def _payload(prazo=48):
    return {
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20"},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": prazo},
    }


def _cliente(db, nome, token):
    cliente_id = str(uuid.uuid4())
    db.add(ClienteApiORM(id=cliente_id, nome=nome))
    db.add(
        CredencialApiORM(
            id=str(uuid.uuid4()), cliente_id=cliente_id, nome="principal",
            token_hash=hash_token(token),
        )
    )
    db.commit()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"}), cliente_id


def test_rotas_de_simulacao_exigem_bearer():
    sem_auth = TestClient(app)
    assert sem_auth.post("/v1/simulacoes", json=_payload()).status_code == 401
    assert sem_auth.get("/v1/simulacoes/qualquer").status_code == 401
    assert sem_auth.post("/v1/simulacoes/qualquer/cancelar").status_code == 401
    assert sem_auth.get("/health/live").status_code == 200


def test_token_invalido_retorna_401():
    invalido = TestClient(app, headers={"Authorization": "Bearer token-invalido"})
    resposta = invalido.post("/v1/simulacoes", json=_payload())
    assert resposta.status_code == 401
    assert resposta.json()["erro"]["code"] == "nao_autorizado"


def test_dois_clientes_nao_enxergam_nem_cancelam_job_alheio(db):
    cliente_a, _ = _cliente(db, "Cliente A", "token-cliente-a")
    cliente_b, _ = _cliente(db, "Cliente B", "token-cliente-b")
    criada = cliente_a.post("/v1/simulacoes", json=_payload()).json()

    assert cliente_b.get(f"/v1/simulacoes/{criada['id']}").status_code == 404
    assert cliente_b.post(f"/v1/simulacoes/{criada['id']}/cancelar").status_code == 404
    assert cliente_a.get(f"/v1/simulacoes/{criada['id']}").status_code == 200


def test_idempotency_key_tem_escopo_por_cliente(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "token-cliente-a")
    cliente_b, id_b = _cliente(db, "Cliente B", "token-cliente-b")
    headers = {"Idempotency-Key": "mesma-chave"}

    a = cliente_a.post("/v1/simulacoes", json=_payload(), headers=headers)
    b = cliente_b.post("/v1/simulacoes", json=_payload(), headers=headers)
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] != b.json()["id"]
    assert db.get(IdempotenciaORM, (id_a, "mesma-chave")) is not None
    assert db.get(IdempotenciaORM, (id_b, "mesma-chave")) is not None
    assert db.query(SimulacaoORM).filter_by(cliente_id=id_a).count() == 1
    assert db.query(SimulacaoORM).filter_by(cliente_id=id_b).count() == 1


def test_banco_guarda_somente_hash_da_credencial(db):
    token = "token-super-secreto"
    _, cliente_id = _cliente(db, "Cliente hash", token)
    credencial = db.query(CredencialApiORM).filter_by(cliente_id=cliente_id).one()
    assert credencial.token_hash == hash_token(token)
    assert token not in credencial.token_hash
