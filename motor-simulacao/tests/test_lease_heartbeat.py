"""Lease com heartbeat no fan-out: sem loop, sem duplicada, terminal sempre.

Cobre a correção do loop de lease expirado no caminho por tarefa
(`processar_tarefa_provedor`): renovação de posse durante o driver,
orçamento total finito e guarda de token antes de persistir.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from app import config, servico
from app.models_db import (
    ResultadoORM,
    SimulacaoEventoORM,
    SimulacaoORM,
    SimulacaoProvedorORM,
    SimulacaoTentativaORM,
)
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
)
from app.processamento import (
    MAX_TENTATIVAS_DRIVER,
    _renovar_lease_tarefa,
    processar_tarefa_provedor,
    reencaminhar_tarefas_expiradas,
    reservar_proxima_tarefa,
)
from conftest import TEST_CLIENT_ID


def _sol(provedores=None) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[36]),
        provedores=provedores or ["bradesco"],
    )


def _tarefa_reservada(db, monkeypatch, provedor="bradesco", **cfgs):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    for chave, valor in cfgs.items():
        monkeypatch.setattr(config, chave, valor)
    sim, _ = servico.criar_simulacao(db, _sol([provedor]), TEST_CLIENT_ID)
    tarefa = reservar_proxima_tarefa(db)
    assert tarefa is not None
    assert tarefa.provedor == provedor
    return sim.id, tarefa


def _ok(nome):
    def _d(sol, ctx=None):
        return ResultadoDriver(
            nome,
            "concluida",
            valor_parcela=Decimal("100"),
            taxa_am=Decimal("1.5"),
            prazo_meses=36,
            valor_financiado=Decimal("15000"),
        )

    return _d


def _outra_sessao(db):
    return sessionmaker(bind=db.get_bind())()


# --- renovação condicional ----------------------------------------------------

def test_renovacao_condicional_exige_token_atual(db, monkeypatch):
    _, tarefa = _tarefa_reservada(db, monkeypatch, TASK_LEASE_SECONDS=60)
    antes = tarefa.reservada_ate
    assert _renovar_lease_tarefa(db, tarefa.id, tarefa.reserva_token, 60) is True
    db.refresh(tarefa)
    assert tarefa.reservada_ate >= antes
    assert _renovar_lease_tarefa(db, tarefa.id, "token-errado", 60) is False


# --- heartbeat durante driver longo -------------------------------------------

def test_heartbeat_mantem_posse_durante_driver_longo(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(
        db, monkeypatch, TASK_LEASE_SECONDS=1, TASK_HEARTBEAT_SECONDS=0.05
    )
    token = tarefa.reserva_token
    chamadas = {"n": 0}

    def lento(sol, ctx=None):
        chamadas["n"] += 1
        time.sleep(2.5)  # > lease de 1s: sem heartbeat seria reencaminhada
        outra = _outra_sessao(db)
        try:
            # nenhum outro worker consegue roubar no meio da execução
            assert reencaminhar_tarefas_expiradas(outra) == 0
            assert reservar_proxima_tarefa(outra) is None
        finally:
            outra.close()
        return _ok("bradesco")(sol)

    saida = processar_tarefa_provedor(
        db, tarefa.id, token, drivers=[("bradesco", lento)]
    )
    assert chamadas["n"] == 1
    assert saida.status == "concluida"
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 1


def test_segundo_worker_nao_duplica_com_heartbeat_ativo(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(
        db, monkeypatch, TASK_LEASE_SECONDS=1, TASK_HEARTBEAT_SECONDS=0.05
    )
    token = tarefa.reserva_token
    tid = tarefa.id
    chamadas = {"n": 0}

    def lento(sol, ctx=None):
        chamadas["n"] += 1
        time.sleep(2.0)
        return _ok("bradesco")(sol)

    erros: list[BaseException] = []

    def worker_a():
        try:
            processar_tarefa_provedor(db, tid, token, drivers=[("bradesco", lento)])
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    fio = threading.Thread(target=worker_a, name="test-worker-a")
    fio.start()
    try:
        for _ in range(6):  # ~1.8s: tenta roubar várias vezes no meio
            time.sleep(0.3)
            outra = _outra_sessao(db)
            try:
                assert reencaminhar_tarefas_expiradas(outra) == 0
                assert reservar_proxima_tarefa(outra) is None
            finally:
                outra.close()
    finally:
        fio.join(timeout=30)
    assert not erros
    assert chamadas["n"] == 1
    assert db.get(SimulacaoProvedorORM, tid).status == "concluida"
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 1


# --- recuperação de worker morto (não remover) ---------------------------------

def test_tarefa_expirada_de_worker_morto_volta_a_fila(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch)
    tid = tarefa.id
    # crash: worker morre sem heartbeat e o lease expira
    tarefa.reservada_ate = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert reencaminhar_tarefas_expiradas(db) == 1
    interrompida = db.get(SimulacaoProvedorORM, tid)
    assert interrompida.status == "recebida"
    assert interrompida.reserva_token is None
    assert interrompida.reservada_ate is None

    # outro worker recupera e conclui
    nova = reservar_proxima_tarefa(db)
    assert nova is not None and nova.id == tid
    saida = processar_tarefa_provedor(
        db, nova.id, nova.reserva_token, drivers=[("bradesco", _ok("bradesco"))]
    )
    assert saida.status == "concluida"
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 1


# --- guarda de token ------------------------------------------------------------

def test_token_antigo_nao_persiste_na_entrada(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch)
    token_antigo = tarefa.reserva_token
    tarefa.reserva_token = "token-novo"  # outro worker tomou a tarefa
    db.commit()

    saida = processar_tarefa_provedor(
        db, tarefa.id, token_antigo, drivers=[("bradesco", _ok("bradesco"))]
    )
    assert saida.status == "processando"
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 0


def test_roubo_no_meio_da_execucao_descarta_resultado(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(
        db, monkeypatch, TASK_HEARTBEAT_SECONDS=0  # heartbeat desligado
    )
    token = tarefa.reserva_token
    tid = tarefa.id

    def ladrao(sol, ctx=None):
        # reencaminhamento + tomada por outro worker no meio do driver
        outra = _outra_sessao(db)
        try:
            tomada = outra.get(SimulacaoProvedorORM, tid)
            tomada.status = "recebida"
            tomada.reserva_token = None
            tomada.reservada_ate = None
            outra.commit()
            assert reservar_proxima_tarefa(outra) is not None
        finally:
            outra.close()
        return _ok("bradesco")(sol)

    processar_tarefa_provedor(db, tid, token, drivers=[("bradesco", ladrao)])
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 0
    # a tarefa segue com o novo dono — o worker antigo não a finalizou
    atual = db.get(SimulacaoProvedorORM, tid)
    assert atual.status == "processando"
    assert atual.reserva_token != token


def test_perda_de_posse_detectada_pelo_heartbeat_aborta(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch, TASK_HEARTBEAT_SECONDS=0.05)
    token = tarefa.reserva_token
    tid = tarefa.id

    def rouba_e_demora(sol, ctx=None):
        outra = _outra_sessao(db)
        try:
            tomada = outra.get(SimulacaoProvedorORM, tid)
            tomada.status = "recebida"
            tomada.reserva_token = None
            tomada.reservada_ate = None
            outra.commit()
        finally:
            outra.close()
        time.sleep(0.3)  # dá tempo do heartbeat acusar a perda
        return _ok("bradesco")(sol)

    processar_tarefa_provedor(db, tid, token, drivers=[("bradesco", rouba_e_demora)])
    assert db.query(ResultadoORM).filter_by(simulacao_id=sim_id).count() == 0
    assert db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).count() == 0
    assert db.get(SimulacaoProvedorORM, tid).status == "recebida"


# --- orçamento total finito -----------------------------------------------------

def test_orcamento_estourado_persiste_resultado_terminal(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(
        db, monkeypatch, TASK_BUDGET_SECONDS=0.25, DRIVER_TIMEOUT_SECONDS=60
    )
    chamadas = {"n": 0}

    def sempre_transitorio(sol, ctx=None):
        chamadas["n"] += 1
        time.sleep(0.3)  # 1ª tentativa consome o orçamento; a 2ª nem começa
        raise ErroTransitorio("indisponivel")

    saida = processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=[("bradesco", sempre_transitorio)]
    )
    assert chamadas["n"] == 1  # sem retry infinito
    assert saida.status == "falhou"
    assert saida.codigo_erro == "orcamento_tempo_estourado"
    resultados = db.query(ResultadoORM).filter_by(simulacao_id=sim_id).all()
    assert len(resultados) == 1
    assert resultados[0].codigo_erro == "orcamento_tempo_estourado"
    # onde parou + duração registrados: a tentativa real + a linha do estouro
    tentativas = (
        db.query(SimulacaoTentativaORM)
        .filter_by(simulacao_id=sim_id)
        .order_by(SimulacaoTentativaORM.tentativa.asc())
        .all()
    )
    assert len(tentativas) == 2
    assert tentativas[0].status == "erro_transitorio"
    assert tentativas[0].duracao_ms >= 200
    assert tentativas[1].status == "erro"
    assert tentativas[1].codigo_erro == "orcamento_tempo_estourado"
    etapas = {
        e.etapa
        for e in db.query(SimulacaoEventoORM).filter_by(simulacao_id=sim_id).all()
    }
    assert "orcamento_tempo_estourado" in etapas


def test_timeout_persiste_terminal_com_duracao(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch, DRIVER_TIMEOUT_SECONDS=1)

    def travado(sol, ctx=None):
        time.sleep(5)
        return _ok("bradesco")(sol)

    saida = processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=[("bradesco", travado)]
    )
    assert saida.status == "falhou"
    assert saida.codigo_erro == "timeout_driver"
    resultados = db.query(ResultadoORM).filter_by(simulacao_id=sim_id).all()
    assert len(resultados) == 1
    assert resultados[0].codigo_erro == "timeout_driver"
    tentativas = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).all()
    assert len(tentativas) == 1
    assert tentativas[0].duracao_ms >= 900


# --- retry limitado ---------------------------------------------------------------

def test_transitorio_persistente_para_em_duas_tentativas(db, monkeypatch):
    assert MAX_TENTATIVAS_DRIVER == 2
    _, tarefa = _tarefa_reservada(db, monkeypatch)
    chamadas = {"n": 0}

    def transitorio(sol, ctx=None):
        chamadas["n"] += 1
        raise ErroTransitorio("indisponivel")

    saida = processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=[("bradesco", transitorio)]
    )
    assert chamadas["n"] == 2
    assert saida.status == "falhou"
    assert saida.codigo_erro == "indisponivel"


def test_rejeicao_comercial_nao_sofre_retry(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch)
    chamadas = {"n": 0}

    def rejeita(sol, ctx=None):
        chamadas["n"] += 1
        raise RejeicaoNegocio("renda_insuficiente")

    saida = processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=[("bradesco", rejeita)]
    )
    assert chamadas["n"] == 1
    assert saida.status == "rejeitada"
    assert db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).count() == 1


def test_intervencao_para_sem_retry(db, monkeypatch):
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch)
    chamadas = {"n": 0}

    def captcha(sol, ctx=None):
        chamadas["n"] += 1
        raise IntervencaoNecessaria("captcha")

    saida = processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=[("bradesco", captcha)]
    )
    assert chamadas["n"] == 1
    assert saida.status == "falhou"
    assert saida.codigo_erro == "captcha"
    tentativas = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).all()
    assert len(tentativas) == 1
    assert tentativas[0].status == "aguardando_intervencao"


def test_heartbeat_desfaz_transacao_apos_erro_de_banco(db, monkeypatch, caplog):
    # No Postgres, UPDATE que falha (lock/statement timeout) deixa a transação
    # abortada: sem rollback todo tick seguinte falha e o lease vence calado.
    from sqlalchemy import text

    from app import processamento

    monkeypatch.setattr(config, "TASK_LEASE_SECONDS", 1)
    monkeypatch.setattr(config, "TASK_HEARTBEAT_SECONDS", 0.02)
    chamadas: list[bool] = []
    segundo = threading.Event()

    def _renovar(sessao, tarefa_id, token, lease):
        if not chamadas:
            chamadas.append(True)
            sessao.execute(text("SELECT 1"))
            raise RuntimeError("canceling statement due to lock timeout")
        chamadas.append(sessao.in_transaction())
        segundo.set()
        return True

    monkeypatch.setattr(processamento, "_renovar_lease_tarefa", _renovar)
    with caplog.at_level("WARNING", logger="motor-processamento"):
        with processamento._heartbeat_tarefa(db, tarefa_id="t1", token="tok"):
            assert segundo.wait(2)
    assert chamadas[1] is False
    assert any("heartbeat" in r.getMessage() for r in caplog.records)


# --- teto de reencaminhamento (worker morto em loop) --------------------------

def _expirar(db, tarefa_id):
    t = db.get(SimulacaoProvedorORM, tarefa_id)
    t.reservada_ate = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def test_worker_morto_em_loop_para_apos_dois_reencaminhamentos(db, monkeypatch):
    # Chromium estoura memória toda vez: sem teto a tarefa voltaria à fila para sempre.
    sim_id, tarefa = _tarefa_reservada(db, monkeypatch, TASK_MAX_REQUEUES=2)
    tid = tarefa.id

    for _ in range(2):
        _expirar(db, tid)
        assert reencaminhar_tarefas_expiradas(db) == 1
        assert db.get(SimulacaoProvedorORM, tid).status == "recebida"
        assert reservar_proxima_tarefa(db).id == tid

    assert db.get(SimulacaoProvedorORM, tid).tentativa == 3
    _expirar(db, tid)
    reencaminhar_tarefas_expiradas(db)

    final = db.get(SimulacaoProvedorORM, tid)
    db.refresh(final)
    assert final.status == "falhou"
    assert final.codigo_erro == "tentativas_esgotadas"
    assert final.reserva_token is None and final.reservada_ate is None
    assert reservar_proxima_tarefa(db) is None

    resultado = db.query(ResultadoORM).filter_by(simulacao_id=sim_id).one()
    assert (resultado.status, resultado.codigo_erro) == ("erro", "tentativas_esgotadas")
    sim = db.get(SimulacaoORM, sim_id)
    db.refresh(sim)
    assert sim.status == "falhou"
    etapas = [e.etapa for e in db.query(SimulacaoEventoORM).filter_by(simulacao_id=sim_id)]
    assert "tentativas_esgotadas" in etapas


def test_teto_nao_derruba_tarefa_com_lease_valido(db, monkeypatch):
    # Heartbeat renovou: tentativa alta sozinha não encerra ninguém.
    _, tarefa = _tarefa_reservada(db, monkeypatch, TASK_MAX_REQUEUES=0)
    assert reencaminhar_tarefas_expiradas(db) == 0
    assert db.get(SimulacaoProvedorORM, tarefa.id).status == "processando"
