"""Drivers de simulação (Plano #1A Task 6 + Task 12).

Cada provedor é um adapter isolado. No incremento atual há o mock (taxas fictícias);
drivers reais (Playwright/API) entram com ``real: true`` e credencial.

Desfechos:
- sucesso: ``ResultadoDriver`` ou lista (multi-prazo);
- ``RejeicaoNegocio``: sem retry;
- ``ErroTransitorio`` / ``TimeoutError``: retry limitado;
- ``IntervencaoNecessaria``: captcha/2FA → ``aguardando_intervencao``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional, Union

from sqlalchemy.orm import Session

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


@dataclass
class DriverContext:
    """Contexto opcional passado aos drivers (DB, cliente, screenshots)."""

    db: Session | None = None
    cliente_id: str | None = None
    screenshot_dir: str | None = None


# Driver pode devolver um resultado ou lista (multi-prazo).
Driver = Callable[
    [SolicitacaoSimulacao, Optional[DriverContext]],
    Union[ResultadoDriver, list[ResultadoDriver]],
]


def _prazo_unico(sol: SolicitacaoSimulacao) -> int:
    if sol.condicoes.prazo_meses is not None:
        return sol.condicoes.prazo_meses
    if sol.condicoes.prazos_meses:
        return sol.condicoes.prazos_meses[0]
    return 0


def _driver_banco(banco: str, taxa: Decimal) -> Driver:
    def _driver(
        sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> ResultadoDriver:
        valor = sol.veiculo.valor or 0
        financiado = Decimal(str(max(valor - sol.condicoes.entrada, 0)))
        prazo = _prazo_unico(sol)
        parcela = calcula_parcela_price(financiado, taxa, prazo)
        return ResultadoDriver(
            provedor=banco,
            status="concluida",
            valor_parcela=parcela,
            taxa_am=taxa * 100,
            prazo_meses=prazo,
            valor_financiado=financiado,
        )

    return _driver


# Registro de drivers mock. Cada banco fictício é um provedor distinto.
DRIVERS: dict[str, Driver] = {
    banco: _driver_banco(banco, taxa) for banco, taxa in TAXAS_MOCK.items()
}

# Drivers reais (Task 12+): nome -> Driver. Só resolvidos com credencial.
# Mock usa "Santander" (S maiúsculo); real usa "santander".
REAL_DRIVERS: dict[str, Driver] = {}


def _registrar_drivers_reais() -> None:
    """Import tardio evita ciclo com santander.py."""
    if REAL_DRIVERS:
        return
    from app.motor.santander import fabrica_santander

    REAL_DRIVERS["santander"] = fabrica_santander()


def resolver_drivers(
    provedores: list[str] | None,
    *,
    cliente_id: str | None = None,
    db: Session | None = None,
) -> list[tuple[str, Driver]]:
    """Expande a lista pedida em pares (nome, driver). ``mock`` = todos os bancos mock.

    Drivers em ``REAL_DRIVERS`` só entram se houver credencial habilitada
    (``obter_segredo_para_uso``). Sem credencial: **não** cai no mock silencioso.
    """
    _registrar_drivers_reais()
    pedidos = provedores or ["mock"]
    nomes: list[str] = []
    for p in pedidos:
        if p == "mock":
            nomes.extend(DRIVERS.keys())
        elif p in DRIVERS:
            nomes.append(p)
        elif p in REAL_DRIVERS or p == "santander":
            nomes.append(p)
    vistos: set[str] = set()
    pares: list[tuple[str, Driver]] = []
    for nome in nomes:
        if nome in vistos:
            continue
        vistos.add(nome)
        # Real tem prioridade sobre homônimo mock (não é o caso: Santander vs santander)
        if nome in REAL_DRIVERS:
            if db is not None and cliente_id and _tem_credencial_real(db, cliente_id, nome):
                pares.append((nome, REAL_DRIVERS[nome]))
            continue
        if nome in DRIVERS:
            pares.append((nome, DRIVERS[nome]))
    return pares


def _tem_credencial_real(db: Session, cliente_id: str, provedor: str) -> bool:
    from app.credenciais import obter_segredo_para_uso

    return obter_segredo_para_uso(db, cliente_id, provedor) is not None
