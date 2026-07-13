from decimal import Decimal

from app import processamento, servico
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import ResultadoDriver
from conftest import TEST_CLIENT_ID


def _driver_multi(sol, ctx=None):
    return [
        ResultadoDriver(
            "banco_x",
            "concluida",
            valor_parcela=Decimal(str(100 + p)),
            taxa_am=Decimal("1.9"),
            prazo_meses=p,
            valor_financiado=Decimal("9000"),
        )
        for p in sol.condicoes.prazos_meses
    ]


def test_processa_job_persiste_um_resultado_por_prazo(db):
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(valor=10000, placa="ABC1D23"),
        condicoes=Condicoes(entrada=1000, prazos_meses=[24, 36, 48]),
        provedores=["banco_x"],
    )
    sim, _ = servico.criar_simulacao(db, sol, TEST_CLIENT_ID)
    # reserva manual
    sim.status = "processando"
    sim.reserva_token = "tok-test"
    db.commit()
    db.refresh(sim)

    processamento.processar_job(
        db,
        sim.id,
        drivers=[("banco_x", _driver_multi)],
        reserva_token="tok-test",
    )
    db.expire_all()
    sim = db.get(type(sim), sim.id)
    prazos = sorted(r.prazo_meses for r in sim.resultados)
    assert prazos == [24, 36, 48]
    assert sim.status == "concluida"
    db.commit()
