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
    valor = sol.veiculo.valor or 0
    financiado = Decimal(str(max(valor - sol.condicoes.entrada, 0)))
    prazo = sol.condicoes.prazo_meses or (
        sol.condicoes.prazos_meses[0] if sol.condicoes.prazos_meses else 0
    )
    resultados: list[ResultadoProvedor] = []
    for banco, taxa in TAXAS_MOCK.items():
        parcela = calcula_parcela_price(financiado, taxa, prazo)
        resultados.append(
            ResultadoProvedor(
                provedor=banco,
                valor_parcela=float(parcela),
                taxa_am=float(taxa * 100),
                prazo_meses=prazo,
                valor_financiado=float(financiado),
            )
        )
    return resultados
