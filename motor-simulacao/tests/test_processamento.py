"""Worker: reserva sem dupla execução, resultados parciais, retry/timeout e estados."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import servico
from app.models_db import ResultadoORM, SimulacaoORM, SimulacaoTentativaORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
)
from app.processamento import (
    MAX_TENTATIVAS_DRIVER,
    processar_job,
    reencaminhar_jobs_expirados,
    reservar_proximo_job,
)
from conftest import TEST_CLIENT_ID


def _enfileirar(db, prazo=48):
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="529.982.247-25", nascimento="1990-05-20", renda=3000),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=5000, prazo_meses=prazo),
    )
    sim, _ = servico.criar_simulacao(db, sol, TEST_CLIENT_ID)
    return sim.id


def _reservar(db):
    sim = reservar_proximo_job(db)
    assert sim is not None
    return sim.id


# --- drivers falsos -----------------------------------------------------------

def _ok(nome, parcela="100"):
    def _d(sol):
        return ResultadoDriver(
            nome, "concluida", valor_parcela=Decimal(parcela), taxa_am=Decimal("1.5"),
            prazo_meses=sol.condicoes.prazo_meses, valor_financiado=Decimal("15000"),
        )
    return _d


def _rejeita(nome):
    def _d(sol):
        raise RejeicaoNegocio("renda_insuficiente")
    return _d


def _transitorio_sempre(nome):
    def _d(sol):
        raise ErroTransitorio("indisponivel")
    return _d


def _timeout_depois_ok(nome):
    estado = {"n": 0}

    def _d(sol):
        estado["n"] += 1
        if estado["n"] == 1:
            raise TimeoutError("estourou")
        return ResultadoDriver(
            nome, "concluida", valor_parcela=Decimal("120"), taxa_am=Decimal("1.9"),
            prazo_meses=sol.condicoes.prazo_meses, valor_financiado=Decimal("15000"),
        )
    return _d


def _intervencao(nome):
    def _d(sol):
        raise IntervencaoNecessaria("captcha")
    return _d


# --- reserva ------------------------------------------------------------------

def test_reserva_marca_processando(db):
    _enfileirar(db)
    sim = reservar_proximo_job(db)
    assert sim.status == "processando"


def test_reserva_nao_pega_o_mesmo_job_duas_vezes(db):
    _enfileirar(db)
    primeiro = reservar_proximo_job(db)
    segundo = reservar_proximo_job(db)  # já não há 'recebida'
    assert primeiro is not None
    assert segundo is None


def test_fila_vazia_retorna_none(db):
    assert reservar_proximo_job(db) is None


def test_lease_expirado_reencaminha_job_para_fila(db):
    sim_id = _enfileirar(db)
    reservado = reservar_proximo_job(db)
    reservado.reservada_ate = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert reencaminhar_jobs_expirados(db) == 1
    sim = db.get(SimulacaoORM, sim_id)
    assert sim.status == "recebida"
    assert sim.reserva_token is None
    assert sim.reservada_ate is None


def test_token_antigo_nao_finaliza_reserva_nova(db):
    sim_id = _enfileirar(db)
    reservado = reservar_proximo_job(db)
    token_antigo = reservado.reserva_token
    reservado.reserva_token = "token-novo"
    db.commit()

    sim = processar_job(
        db, sim_id, drivers=[("A", _ok("A"))], reserva_token=token_antigo
    )
    assert sim.status == "processando"
    assert sim.resultados == []


# --- estados gerais -----------------------------------------------------------

def test_todos_ok_conclui(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _ok("A")), ("B", _ok("B"))])
    assert sim.status == "concluida"
    assert len(sim.resultados) == 2
    assert all(r.status == "concluida" for r in sim.resultados)


def test_um_falha_vira_parcial(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _ok("A")), ("B", _rejeita("B"))])
    assert sim.status == "parcial"
    por_provedor = {r.provedor: r for r in sim.resultados}
    assert por_provedor["A"].status == "concluida"
    assert por_provedor["B"].status == "rejeitada"
    assert por_provedor["B"].codigo_erro == "renda_insuficiente"
    assert por_provedor["B"].valor_parcela is None  # falha não tem parcela


def test_todos_falham_vira_falhou(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _rejeita("A")), ("B", _rejeita("B"))])
    assert sim.status == "falhou"


def test_intervencao_manual(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _intervencao("A"))])
    assert sim.status == "aguardando_intervencao"
    assert sim.resultados[0].status == "aguardando_intervencao"
    assert sim.resultados[0].codigo_erro == "captcha"


# --- retry / timeout ----------------------------------------------------------

def test_retry_transitorio_acaba_concluindo(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _timeout_depois_ok("A"))])
    assert sim.status == "concluida"
    tentativas = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id, provedor="A").all()
    assert len(tentativas) == 2  # 1ª timeout, 2ª concluída
    assert tentativas[0].status == "erro_transitorio"
    assert tentativas[1].status == "concluida"


def test_transitorio_persistente_esgota_e_erra(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    sim = processar_job(db, sim_id, drivers=[("A", _transitorio_sempre("A"))])
    assert sim.status == "falhou"
    assert sim.resultados[0].status == "erro"
    tentativas = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).count()
    assert tentativas == MAX_TENTATIVAS_DRIVER


def test_rejeicao_de_negocio_nao_sofre_retry(db):
    sim_id = _enfileirar(db)
    _reservar(db)
    processar_job(db, sim_id, drivers=[("A", _rejeita("A"))])
    tentativas = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim_id).count()
    assert tentativas == 1


def test_job_cancelado_nao_processa(db):
    sim_id = _enfileirar(db)
    servico.cancelar_simulacao(db, sim_id, TEST_CLIENT_ID)
    # nem reserva (não está 'recebida')
    assert reservar_proximo_job(db) is None
    # e processar direto também não mexe
    sim = processar_job(db, sim_id, drivers=[("A", _ok("A"))])
    assert sim.status == "cancelada"
    assert sim.resultados == []


def test_retomada_nao_repete_provedor_ja_persistido(db):
    sim_id = _enfileirar(db)
    reservado = reservar_proximo_job(db)
    db.add(
        ResultadoORM(
            simulacao_id=sim_id,
            provedor="A",
            status="concluida",
            valor_parcela=100,
            taxa_am=1.5,
            prazo_meses=48,
            valor_financiado=15000,
        )
    )
    db.commit()
    chamadas = {"A": 0, "B": 0}

    def _contado(nome):
        def _driver(sol):
            chamadas[nome] += 1
            return _ok(nome)(sol)

        return _driver

    sim = processar_job(
        db,
        sim_id,
        drivers=[("A", _contado("A")), ("B", _contado("B"))],
        reserva_token=reservado.reserva_token,
    )
    assert sim.status == "concluida"
    assert chamadas == {"A": 0, "B": 1}
    assert len(sim.resultados) == 2
