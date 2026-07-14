"""GET /v1/simulacoes — histórico por cliente/ator (Task 16).

Listagem escopada por cliente (tenancy), com filtros (status, solicitado_por,
desde/ate) e paginação. Nunca decifra payload pessoal; expõe só campos não
sensíveis (placa, referencia_externa, provedores, prazos).
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth import hash_token
from app.main import app
from app.models_db import ClienteApiORM, CredencialApiORM, SimulacaoORM


def _payload(prazo=48):
    return {
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20"},
        "veiculo": {"categoria": "moto", "valor": 20000, "placa": "ABC1D23"},
        "condicoes": {"entrada": 5000, "prazo_meses": prazo},
        "provedores": ["mock"],
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


def _semear(db, cliente_id, *, n=1, status="recebida", solicitado_por=None, base=None):
    base = base or datetime(2026, 7, 1, tzinfo=timezone.utc)
    ids = []
    for i in range(n):
        sim = SimulacaoORM(
            id=str(uuid.uuid4()),
            cliente_id=cliente_id,
            status=status,
            solicitado_por=solicitado_por,
            criada_em=base + timedelta(minutes=i),
            placa="ABC1D23",
            provedores=["mock"],
            prazos_meses=[48],
        )
        db.add(sim)
        ids.append(sim.id)
    db.commit()
    return ids


# --- criação grava solicitado_por a partir do X-Ator ---

def test_criar_simulacao_grava_solicitado_por(client, db):
    r = client.post(
        "/v1/simulacoes", json=_payload(), headers={"X-Ator": "ana@loja.test"}
    )
    assert r.status_code == 202, r.text
    sim = db.get(SimulacaoORM, r.json()["id"])
    assert sim.solicitado_por == "ana@loja.test"


def test_criar_simulacao_sem_ator_deixa_solicitado_por_nulo(client, db):
    r = client.post("/v1/simulacoes", json=_payload())
    assert r.status_code == 202
    sim = db.get(SimulacaoORM, r.json()["id"])
    assert sim.solicitado_por is None


# --- autenticação ---

def test_listagem_exige_bearer():
    sem_auth = TestClient(app)
    assert sem_auth.get("/v1/simulacoes").status_code == 401


# --- tenancy ---

def test_listagem_escopada_por_cliente(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    cliente_b, id_b = _cliente(db, "Cliente B", "tok-b")
    _semear(db, id_a, n=2)
    _semear(db, id_b, n=3)

    corpo = cliente_a.get("/v1/simulacoes").json()
    assert corpo["total"] == 2
    assert all(item["id"] for item in corpo["itens"])
    # Nenhuma sim do cliente B aparece para o A.
    ids_b = set(_semear(db, id_b, n=0))  # noqa: F841 (sanity)
    assert cliente_b.get("/v1/simulacoes").json()["total"] == 3


def test_listagem_nunca_expoe_cpf_em_claro(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=1)
    item = cliente_a.get("/v1/simulacoes").json()["itens"][0]
    assert "cpf" not in item
    assert "payload_cifrado" not in item
    assert item["placa"] == "ABC1D23"


# --- filtros ---

def test_listagem_filtra_por_status(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=2, status="concluida")
    _semear(db, id_a, n=1, status="falhou")

    corpo = cliente_a.get("/v1/simulacoes?status=concluida").json()
    assert corpo["total"] == 2
    assert {i["status"] for i in corpo["itens"]} == {"concluida"}


def test_listagem_filtra_por_solicitado_por(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=2, solicitado_por="ana@loja.test")
    _semear(db, id_a, n=1, solicitado_por="bruno@loja.test")

    corpo = cliente_a.get("/v1/simulacoes?solicitado_por=ana@loja.test").json()
    assert corpo["total"] == 2
    assert {i["solicitado_por"] for i in corpo["itens"]} == {"ana@loja.test"}


def test_listagem_filtra_por_janela_de_data(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=1, base=datetime(2026, 6, 1, tzinfo=timezone.utc))
    _semear(db, id_a, n=1, base=datetime(2026, 7, 15, tzinfo=timezone.utc))

    corpo = cliente_a.get("/v1/simulacoes?desde=2026-07-01").json()
    assert corpo["total"] == 1


# --- ordenação e paginação ---

def test_listagem_ordena_por_criada_em_desc(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=3, base=datetime(2026, 7, 1, tzinfo=timezone.utc))
    itens = cliente_a.get("/v1/simulacoes").json()["itens"]
    datas = [i["criada_em"] for i in itens]
    assert datas == sorted(datas, reverse=True)


def test_listagem_paginacao(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    _semear(db, id_a, n=5, base=datetime(2026, 7, 1, tzinfo=timezone.utc))

    pagina1 = cliente_a.get("/v1/simulacoes?limite=2&offset=0").json()
    assert pagina1["total"] == 5
    assert len(pagina1["itens"]) == 2

    pagina3 = cliente_a.get("/v1/simulacoes?limite=2&offset=4").json()
    assert len(pagina3["itens"]) == 1
    # Sem sobreposição entre páginas.
    assert pagina1["itens"][0]["id"] != pagina3["itens"][0]["id"]


def test_listagem_limite_tem_teto(db):
    cliente_a, id_a = _cliente(db, "Cliente A", "tok-a")
    corpo = cliente_a.get("/v1/simulacoes?limite=99999").json()
    assert corpo["limite"] <= 100
