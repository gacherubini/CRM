"""Drivers de simulação (Plano #1A, Task 6).

Cada provedor é um adapter isolado. No incremento atual só há o mock (taxas fictícias),
mas a interface já distingue os desfechos que o worker precisa tratar:

- sucesso: devolve ``ResultadoDriver`` com status ``concluida``;
- ``RejeicaoNegocio``: rejeição de negócio — não sofre retry;
- ``ErroTransitorio`` (ou ``TimeoutError``): indisponibilidade — sofre retry limitado;
- ``IntervencaoNecessaria``: captcha/2FA — vira ``aguardando_intervencao``.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from app.motor.amortizacao import calcula_parcela_price
from app.motor.base import SolicitacaoSimulacao
from app.motor.mock import TAXAS_MOCK


class ErroTransitorio(Exception):
    def __init__(self, codigo: str = "indisponivel_temporario", mensagem: str = ""):
        super().__init__(mensagem or codigo)
        self.codigo = codigo


class RejeicaoNegocio(Exception):
    def __init__(self, codigo: str = "rejeitado", mensagem: str = ""):
        super().__init__(mensagem or codigo)
        self.codigo = codigo


class IntervencaoNecessaria(Exception):
    def __init__(self, codigo: str = "intervencao_manual", mensagem: str = ""):
        super().__init__(mensagem or codigo)
        self.codigo = codigo


@dataclass
class ResultadoDriver:
    provedor: str
    status: str  # concluida | rejeitada | erro | aguardando_intervencao
    valor_parcela: Optional[Decimal] = None
    taxa_am: Optional[Decimal] = None
    prazo_meses: Optional[int] = None
    valor_financiado: Optional[Decimal] = None
    codigo_erro: Optional[str] = None


Driver = Callable[[SolicitacaoSimulacao], ResultadoDriver]


def _driver_banco(banco: str, taxa: Decimal) -> Driver:
    def _driver(sol: SolicitacaoSimulacao) -> ResultadoDriver:
        financiado = Decimal(str(max(sol.veiculo.valor - sol.condicoes.entrada, 0)))
        parcela = calcula_parcela_price(financiado, taxa, sol.condicoes.prazo_meses)
        return ResultadoDriver(
            provedor=banco,
            status="concluida",
            valor_parcela=parcela,
            taxa_am=taxa * 100,
            prazo_meses=sol.condicoes.prazo_meses,
            valor_financiado=financiado,
        )

    return _driver


# Registro de drivers habilitados. Cada banco do mock é um provedor distinto.
DRIVERS: dict[str, Driver] = {
    banco: _driver_banco(banco, taxa) for banco, taxa in TAXAS_MOCK.items()
}


def resolver_drivers(provedores: list[str] | None) -> list[tuple[str, Driver]]:
    """Expande a lista pedida em pares (nome, driver). ``mock`` = todos os bancos mock."""
    pedidos = provedores or ["mock"]
    nomes: list[str] = []
    for p in pedidos:
        if p == "mock":
            nomes.extend(DRIVERS.keys())
        elif p in DRIVERS:
            nomes.append(p)
    vistos: set[str] = set()
    pares: list[tuple[str, Driver]] = []
    for nome in nomes:
        if nome not in vistos:
            vistos.add(nome)
            pares.append((nome, DRIVERS[nome]))
    return pares
