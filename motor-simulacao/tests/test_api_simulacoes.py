from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload():
    return {
        "referencia_externa": "lead-123",
        "pessoa": {"cpf": "529.982.247-25", "nascimento": "1990-05-20", "renda": 3000},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": 48},
        "provedores": ["mock"],
    }


def test_criar_simulacao_retorna_201():
    r = client.post("/v1/simulacoes", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "concluida"
    assert "id" in body and "criada_em" in body


def test_consultar_simulacao_traz_cinco_provedores():
    criada = client.post("/v1/simulacoes", json=_payload()).json()
    r = client.get(f"/v1/simulacoes/{criada['id']}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["resultados"]) == 5
    assert body["resultados"][0]["prazo_meses"] == 48


def test_criar_simulacao_cpf_invalido_retorna_422():
    payload = _payload()
    payload["pessoa"]["cpf"] = "111.111.111-11"
    r = client.post("/v1/simulacoes", json=payload)
    assert r.status_code == 422
    assert r.json()["erro"]["code"] == "cpf_invalido"


def test_criar_simulacao_entrada_maior_que_valor_retorna_422():
    payload = _payload()
    payload["condicoes"]["entrada"] = 999999
    r = client.post("/v1/simulacoes", json=payload)
    assert r.status_code == 422
    assert r.json()["erro"]["code"] == "entrada_invalida"


def test_consultar_simulacao_inexistente_retorna_404():
    r = client.get("/v1/simulacoes/nao-existe")
    assert r.status_code == 404
    assert r.json()["erro"]["code"] == "nao_encontrada"
