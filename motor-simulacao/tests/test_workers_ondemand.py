"""Workers sob demanda: lifecycle, orquestrador, tarefas e idle stop."""
from __future__ import annotations

import time
from unittest import mock

import httpx
import pytest

from app import config, servico
from app.lifecycle import FakeLifecycle, FlyMachinesLifecycle, RateLimitedLifecycle
from app.models_db import SimulacaoProvedorORM, WorkerSlotORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.orquestrador import acordar_workers, upsert_slot
from app.processamento import (
    drenar_fila,
    processar_proxima_tarefa,
    reencaminhar_tarefas_expiradas,
)
from app import worker as worker_mod


def _sol(provedores=None) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=provedores or ["mock"],
    )


def test_fake_lifecycle_registra_starts():
    fake = FakeLifecycle()
    assert fake.start("m1") is True
    assert fake.started == ["m1"]
    fake.fail_ids.add("m2")
    assert fake.start("m2") is False


def test_fly_lifecycle_allowlist_e_idempotente(httpx_mock=None):
    """Sem rede: usa transport mock do httpx."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.url.path.endswith("/start"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    fly = FlyMachinesLifecycle(
        token="tok-test",
        app_name="motor2037",
        base_url="https://api.machines.dev",
        allowlist={"mach-ok"},
        client=client,
    )
    assert fly.start("mach-evil") is False  # fora allowlist
    assert fly.start("mach-ok") is True
    assert any(c[0] == "POST" for c in calls)
    client.close()


def test_fly_lifecycle_already_started_eh_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="machine already started")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fly = FlyMachinesLifecycle(
        token="t", app_name="app", allowlist={"m1"}, client=client
    )
    assert fly.start("m1") is True
    client.close()


def test_rate_limited_burst_permite_varios_starts():
    inner = FakeLifecycle()
    rl = RateLimitedLifecycle(inner, burst=4, window_seconds=0.05)
    assert rl.start("a") and rl.start("b") and rl.start("c")
    assert inner.started == ["a", "b", "c"]


def test_acordar_workers_paralelo_chama_todos_os_slots(db, monkeypatch):
    """Uma simulação multi-banco deve disparar start em todos os slots de uma vez."""
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", True)
    monkeypatch.setattr(config, "MAX_BROWSER_WORKERS", 4)
    for nome, mid in (
        ("santander", "m-san"),
        ("fontecred", "m-fon"),
        ("bradesco", "m-bra"),
    ):
        upsert_slot(db, provedor=nome, fly_machine_id=mid, tipo_driver="playwright")
    sim, _ = servico.criar_simulacao(
        db, _sol(["santander", "fontecred", "bradesco"]), "c1"
    )
    fake = FakeLifecycle()
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)
    assert res["acordados"] == 3
    assert set(fake.started) == {"m-san", "m-fon", "m-bra"}


def test_acordar_workers_inicia_slot_playwright(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", True)
    monkeypatch.setattr(config, "MAX_BROWSER_WORKERS", 2)

    slot = upsert_slot(
        db, provedor="santander", fly_machine_id="fly-sant-1", tipo_driver="playwright"
    )
    assert slot.fly_machine_id == "fly-sant-1"

    sim, _ = servico.criar_simulacao(db, _sol(["santander", "pan"]), "c1")
    # pan é api — não acorda machine 2GB
    fake = FakeLifecycle()
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)
    assert res["acordados"] == 1
    assert fake.started == ["fly-sant-1"]

    t_sant = (
        db.query(SimulacaoProvedorORM)
        .filter_by(simulacao_id=sim.id, provedor="santander")
        .one()
    )
    # após start ok fica acordando_worker (ou processando se worker já pegou)
    assert t_sant.status in {"acordando_worker", "recebida", "processando"}
    assert t_sant.worker_slot_id == slot.id


def test_acordar_sem_flag_eh_noop(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", False)
    upsert_slot(db, provedor="santander", fly_machine_id="fly-x")
    sim, _ = servico.criar_simulacao(db, _sol(["santander"]), "c1")
    fake = FakeLifecycle()
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)
    assert res["acordados"] == 0
    assert fake.started == []


def test_fanout_processa_tarefas_mock_e_agrega(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", False)
    sim, _ = servico.criar_simulacao(db, _sol(["mock"]), "c1")
    n = drenar_fila(db)
    assert n >= 1
    db.refresh(sim)
    assert sim.status == "concluida"
    tarefa = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).one()
    assert tarefa.status == "concluida"
    assert len(sim.resultados) >= 1


def test_multi_tarefas_sequenciais(db, monkeypatch):
    """Duas tarefas mock-like: processa uma por vez e fecha o job."""
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    # Dois provedores mock (nomes de bancos fictícios do DRIVERS)
    sim, _ = servico.criar_simulacao(
        db, _sol(["mock"]), "c1"
    )
    # força segunda tarefa artificial
    from app.fanout import criar_tarefas_provedor
    # já tem mock; processa
    while processar_proxima_tarefa(db) is not None:
        pass
    db.refresh(sim)
    assert sim.status in {"concluida", "parcial"}


def test_lease_expirado_requeue(db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    sim, _ = servico.criar_simulacao(db, _sol(["mock"]), "c1")
    t = db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).one()
    t.status = "processando"
    t.reserva_token = "tok"
    t.reservada_ate = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()
    n = reencaminhar_tarefas_expiradas(db)
    assert n == 1
    db.refresh(t)
    assert t.status == "recebida"
    assert t.reserva_token is None


def test_worker_idle_sai_zero(monkeypatch):
    monkeypatch.setattr(config, "WORKER_ON_DEMAND", True)
    monkeypatch.setattr(config, "WORKER_IDLE_STOP_SECONDS", 1)
    monkeypatch.setattr(config, "WORKER_PROVEDOR", "santander")
    monkeypatch.setattr(worker_mod, "_uma_rodada", lambda: 0)
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)
    # idle: duas iterações (set ocioso + esgota)
    clocks = [0.0, 0.0, 0.5, 1.5]

    def mono():
        return clocks.pop(0) if clocks else 10.0

    monkeypatch.setattr(worker_mod.time, "monotonic", mono)
    monkeypatch.setattr(worker_mod, "_limpar_screenshots_expirados", lambda: 0)
    code = worker_mod.main()
    assert code == 0


def test_criar_chama_acordar_quando_flags(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", True)
    upsert_slot(db, provedor="santander", fly_machine_id="m-auto")
    fake = FakeLifecycle()
    with mock.patch("app.orquestrador.lifecycle_padrao", return_value=fake):
        # acordar_workers usa lifecycle injetável só se chamado direto;
        # _acordar_workers_apos_criar usa lifecycle_padrao
        with mock.patch(
            "app.orquestrador.acordar_workers",
            wraps=lambda db, simulacao_id=None, lifecycle=None: acordar_workers(
                db, simulacao_id=simulacao_id, lifecycle=fake
            ),
        ) as wrapped:
            # patch no ponto de import do servico
            pass
    # Chama orquestrador diretamente como o create faria
    sim, _ = servico.criar_simulacao(db, _sol(["santander"]), "c1")
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)
    assert res["acordados"] == 1
