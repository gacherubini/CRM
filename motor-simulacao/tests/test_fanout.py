"""Fan-out multi-banco: flags, tarefas por provedor e idempotência."""
from __future__ import annotations

import pytest

from app import config, servico
from app.fanout import criar_tarefas_provedor, tipo_driver_provedor
from app.models_db import SimulacaoProvedorORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.processamento import drenar_fila


def _sol(provedores=None) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24, 36]),
        provedores=provedores or ["mock"],
    )


def test_flags_fanout_defaults_desligados():
    assert config.FANOUT_ENABLED is False
    assert config.FLY_AUTOSCALE_ENABLED is False
    assert config.MAX_BROWSER_WORKERS >= 1
    assert config.WORKER_IDLE_STOP_SECONDS >= 1


def test_tipo_driver_provedor():
    assert tipo_driver_provedor("mock") == "mock"
    assert tipo_driver_provedor("santander") == "playwright"
    assert tipo_driver_provedor("fontecred") == "playwright"
    assert tipo_driver_provedor("bradesco") == "playwright"
    # pan dual-path: slot Playwright sob demanda (não no orquestrador 512MB)
    assert tipo_driver_provedor("pan") == "playwright"
    assert tipo_driver_provedor("Santander") == "playwright"  # normaliza


def test_sem_fanout_nao_cria_tarefas(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", False)
    sim, criada = servico.criar_simulacao(db, _sol(["santander", "pan"]), "c1")
    assert criada is True
    n = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).count()
    assert n == 0


def test_com_fanout_cria_uma_tarefa_por_banco(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    sim, _ = servico.criar_simulacao(
        db, _sol(["santander", "pan", "bradesco"]), "c1"
    )
    tarefas = (
        db.query(SimulacaoProvedorORM)
        .filter_by(simulacao_id=sim.id)
        .order_by(SimulacaoProvedorORM.provedor)
        .all()
    )
    assert [t.provedor for t in tarefas] == ["bradesco", "pan", "santander"]
    by_p = {t.provedor: t for t in tarefas}
    assert by_p["santander"].tipo_driver == "playwright"
    assert by_p["pan"].tipo_driver == "playwright"
    assert by_p["bradesco"].status == "recebida"


def test_criar_tarefas_idempotente(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    sim, _ = servico.criar_simulacao(db, _sol(["pan", "pan", "santander"]), "c1")
    n1 = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).count()
    assert n1 == 2
    # segunda chamada não duplica
    criar_tarefas_provedor(db, sim, ["pan", "santander", "fontecred"])
    db.commit()
    n2 = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).count()
    assert n2 == 3  # só fontecred nova


def test_idempotency_key_nao_duplica_tarefas(client, db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    body = {
        "pessoa": {"cpf": "52998224725", "nascimento": "1990-05-20"},
        "veiculo": {"categoria": "moto", "valor": 15000},
        "condicoes": {"entrada": 1000, "prazos_meses": [36]},
        "provedores": ["mock", "santander"],
    }
    headers = {"Idempotency-Key": "fanout-key-1"}
    r1 = client.post("/v1/simulacoes", json=body, headers=headers)
    r2 = client.post("/v1/simulacoes", json=body, headers=headers)
    assert r1.status_code == 202
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    sim_id = r1.json()["id"]
    n = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim_id).count()
    assert n == 2


def test_worker_marca_tarefas_ao_processar_mock(client, db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    body = {
        "pessoa": {"cpf": "52998224725", "nascimento": "1990-05-20"},
        "veiculo": {"categoria": "moto", "valor": 15000},
        "condicoes": {"entrada": 1000, "prazo_meses": 36},
        "provedores": ["mock"],
    }
    r = client.post("/v1/simulacoes", json=body)
    assert r.status_code == 202
    sim_id = r.json()["id"]
    drenar_fila(db)
    tarefas = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim_id).all()
    assert len(tarefas) == 1
    assert tarefas[0].status == "concluida"
    assert tarefas[0].finalizada_em is not None

    detalhe = client.get(f"/v1/simulacoes/{sim_id}").json()
    assert detalhe["provedores"] == ["mock"]
    assert len(detalhe["tarefas"]) == 1
    assert detalhe["tarefas"][0]["status"] == "concluida"


def test_cancelar_cancela_tarefas_abertas(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    sim, _ = servico.criar_simulacao(db, _sol(["mock", "santander"]), "c1")
    cancelada = servico.cancelar_simulacao(db, sim.id, "c1")
    assert cancelada is not None
    assert cancelada.status == "cancelada"
    statuses = {
        t.provedor: t.status
        for t in db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id)
    }
    assert statuses == {"mock": "cancelada", "santander": "cancelada"}
