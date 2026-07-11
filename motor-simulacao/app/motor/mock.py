"""Driver mock determinístico (Plano #1A, Task 3).

As taxas são FICTÍCIAS e nunca devem ser habilitadas como oferta real.
O mock representa os 5 bancos como provedores distintos.
"""
from decimal import Decimal

from app.motor.amortizacao import calcula_parcela_price
from app.motor.base import ResultadoProvedor, SolicitacaoSimulacao

# Taxas a.m. em fração — FICTÍCIAS, apenas para demonstração/teste.
TAXAS_MOCK = {
    "Santander": Decimal("0.0189"),
    "Bradesco": Decimal("0.0185"),
    "Fontcred": Decimal("0.0210"),
    "Pan": Decimal("0.0172"),
    "BV": Decimal("0.0179"),
}


def simular_mock(sol: SolicitacaoSimulacao) -> list[ResultadoProvedor]:
    financiado = Decimal(str(max(sol.veiculo.valor - sol.condicoes.entrada, 0)))
    resultados: list[ResultadoProvedor] = []
    for banco, taxa in TAXAS_MOCK.items():
        parcela = calcula_parcela_price(financiado, taxa, sol.condicoes.prazo_meses)
        resultados.append(
            ResultadoProvedor(
                provedor=banco,
                valor_parcela=float(parcela),
                taxa_am=float(taxa * 100),
                prazo_meses=sol.condicoes.prazo_meses,
                valor_financiado=float(financiado),
            )
        )
    return resultados
