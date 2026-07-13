from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext, resolver_drivers


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(valor=10000),
        condicoes=Condicoes(entrada=0, prazo_meses=24),
        provedores=["mock"],
    )


def test_driver_mock_aceita_contexto_opcional_e_devolve_resultado():
    pares = resolver_drivers(["mock"])
    nome, driver = pares[0]
    r = driver(_sol(), DriverContext())
    assert r.status == "concluida"
    assert r.provedor == nome
    r2 = driver(_sol(), None)
    assert r2.status == "concluida"
