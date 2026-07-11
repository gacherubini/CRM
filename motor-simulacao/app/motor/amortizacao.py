"""Fórmula Price em Decimal com arredondamento explícito (Plano #1A, Task 3)."""
from decimal import Decimal, ROUND_HALF_UP

CENTAVOS = Decimal("0.01")


def calcula_parcela_price(valor_financiado, taxa_mensal, n_parcelas: int) -> Decimal:
    """Parcela fixa pelo sistema Price. `taxa_mensal` em fração (ex.: 0.0179)."""
    if n_parcelas <= 0:
        raise ValueError("n_parcelas deve ser > 0")
    valor = Decimal(str(valor_financiado))
    i = Decimal(str(taxa_mensal))
    if i == 0:
        parcela = valor / Decimal(n_parcelas)
    else:
        fator = (i * (1 + i) ** n_parcelas) / ((1 + i) ** n_parcelas - 1)
        parcela = valor * fator
    return parcela.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
