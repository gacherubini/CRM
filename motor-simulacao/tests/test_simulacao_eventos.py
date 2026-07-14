import time
import os
from pathlib import Path

from app import config, servico
from app.models_db import SimulacaoEventoORM, SimulacaoORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.processamento import processar_job, reservar_proximo_job
from conftest import TEST_CLIENT_ID


def _enfileirar(db):
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=5000, prazo_meses=48),
    )
    sim, _ = servico.criar_simulacao(db, sol, TEST_CLIENT_ID)
    return sim.id


def test_reserva_e_finalizacao_geram_timeline(client, db):
    sim_id = _enfileirar(db)
    reservar_proximo_job(db)

    def driver(sol, ctx):
        ctx.registrar_evento("etapa_teste", "Executando etapa segura.")
        from app.motor.drivers import ResultadoDriver

        return ResultadoDriver("teste", "concluida", prazo_meses=48)

    processar_job(db, sim_id, drivers=[("teste", driver)])
    resposta = client.get(f"/v1/simulacoes/{sim_id}/eventos")
    assert resposta.status_code == 200
    eventos = resposta.json()["eventos"]
    etapas = [e["etapa"] for e in eventos]
    assert etapas[0] == "job_reservado"
    assert "driver_iniciado" in etapas
    assert "etapa_teste" in etapas
    assert etapas[-1] == "job_finalizado"
    assert all("screenshot_path" not in e for e in eventos)


def test_print_so_e_servido_dentro_da_raiz_configurada(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCREENSHOT_DIR", str(tmp_path))
    sim_id = _enfileirar(db)
    arquivo = tmp_path / sim_id / "falha.png"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(b"PNG")
    evento = SimulacaoEventoORM(
        simulacao_id=sim_id,
        etapa="falha_portal",
        nivel="erro",
        mensagem="Falha segura.",
        screenshot_path=str(arquivo),
    )
    db.add(evento)
    db.commit()
    resposta = client.get(f"/v1/simulacoes/{sim_id}/eventos/{evento.id}/print")
    assert resposta.status_code == 200
    assert resposta.content == b"PNG"


def test_driver_tem_deadline_duro_e_job_nao_fica_processando(db, monkeypatch):
    monkeypatch.setattr(config, "DRIVER_TIMEOUT_SECONDS", 1)
    sim_id = _enfileirar(db)
    reservar_proximo_job(db)

    def travado(sol, ctx):
        time.sleep(5)

    inicio = time.monotonic()
    sim = processar_job(db, sim_id, drivers=[("travado", travado)])
    assert time.monotonic() - inicio < 4
    assert sim.status == "falhou"
    assert sim.resultados[0].codigo_erro == "timeout_driver"
    assert db.get(SimulacaoORM, sim_id).reservada_ate is None


def test_limpeza_remove_print_expirado(tmp_path, monkeypatch):
    from app.worker import _limpar_screenshots_expirados

    antigo = tmp_path / "job" / "antigo.png"
    antigo.parent.mkdir()
    antigo.write_bytes(b"PNG")
    oito_dias = time.time() - 8 * 86400
    os.utime(antigo, (oito_dias, oito_dias))
    monkeypatch.setattr(config, "SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "SCREENSHOT_RETENTION_DAYS", 7)
    assert _limpar_screenshots_expirados() == 1
    assert not antigo.exists()
