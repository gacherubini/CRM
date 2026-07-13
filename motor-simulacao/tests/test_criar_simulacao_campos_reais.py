from app.models_db import SimulacaoORM


def test_cria_job_com_campos_reais(client, db):
    body = {
        "pessoa": {"cpf": "52998224725", "nascimento": "1990-01-01", "cnh": True},
        "veiculo": {
            "placa": "ABC1D23",
            "uf_licenciamento": "SP",
            "finalidade": "comum",
            "categoria": "moto",
        },
        "condicoes": {"entrada": 1000, "prazos_meses": [24, 36, 48]},
        "provedores": ["mock"],
    }
    r = client.post("/v1/simulacoes", json=body)
    assert r.status_code in (201, 202), r.text
    sim = db.get(SimulacaoORM, r.json()["id"])
    assert sim is not None
    assert sim.placa == "ABC1D23" and sim.uf_licenciamento == "SP"
    assert sim.finalidade == "comum" and sim.cnh is True
    assert sim.prazos_meses == [24, 36, 48]
    assert sim.prazo_meses == 24


def test_cria_job_legado_prazo_unico_ainda_funciona(client, db):
    body = {
        "pessoa": {"cpf": "52998224725", "nascimento": "1990-01-01"},
        "veiculo": {"categoria": "moto", "valor": 20000},
        "condicoes": {"entrada": 5000, "prazo_meses": 48},
        "provedores": ["mock"],
    }
    r = client.post("/v1/simulacoes", json=body)
    assert r.status_code in (201, 202), r.text
    sim = db.get(SimulacaoORM, r.json()["id"])
    assert sim.valor == 20000
    assert sim.prazo_meses == 48
    assert sim.prazos_meses == [48]
