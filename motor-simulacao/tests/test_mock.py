from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.mock import TAXAS_MOCK, simular_mock


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="529.982.247-25", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=5000, prazo_meses=48),
    )


def test_mock_retorna_todos_bancos():
    resultados = simular_mock(_sol())
    assert {r.provedor for r in resultados} == set(TAXAS_MOCK.keys())


def test_mock_valor_financiado_desconta_entrada():
    resultados = simular_mock(_sol())
    assert all(r.valor_financiado == 15000 for r in resultados)


def test_mock_parcela_positiva():
    resultados = simular_mock(_sol())
    assert all(r.valor_parcela > 0 for r in resultados)


def test_mock_taxa_am_em_percentual():
    resultados = simular_mock(_sol())
    assert all(1.0 <= r.taxa_am <= 3.0 for r in resultados)
