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
    # Entrada necessaria devolvida pelo banco (ex.: Santander calcula e retorna).
    entrada: Optional[Decimal] = None
    codigo_erro: Optional[str] = None


@dataclass
class DriverContext:
    """Contexto opcional passado aos drivers (DB, cliente, screenshots)."""

    db: Session | None = None
    cliente_id: str | None = None
    screenshot_dir: str | None = None
    simulacao_id: str | None = None
    evento: Callable[[str, str, str, str | None], None] | None = None

    def registrar_evento(
        self,
        etapa: str,
        mensagem: str,
        nivel: str = "info",
        screenshot_path: str | None = None,
    ) -> None:
        if self.evento is not None:
            self.evento(etapa, mensagem, nivel, screenshot_path)


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
# Mock usa "Santander" (S maiúsculo); real usa "santander" (minúsculo) para não
# sombrear o provedor mock homônimo.
REAL_DRIVERS: dict[str, Driver] = {}


def _registrar_drivers_reais() -> None:
    """Import tardio evita ciclos com os adapters concretos."""
    if {"santander", "pan", "fontecred", "bradesco"}.issubset(REAL_DRIVERS):
        return
    from app.motor.santander import fabrica_santander
    from app.motor.pan import fabrica_pan
    from app.motor.fontecred import fabrica_fontecred
    from app.motor.bradesco import fabrica_bradesco

    driver = fabrica_santander()
    # Registrado apenas em minúsculo ("santander"): é o nome canônico usado para
    # pedidos explícitos do driver real. NÃO registrar também "Santander" (maiúsculo)
    # aqui — esse é o nome do provedor mock (ver TAXAS_MOCK) e, se o real também
    # ocupasse essa chave, ele sombrearia o mock em `resolver_drivers` (pedido
    # "mock" resolveria "Santander" para REAL_DRIVERS e, sem credencial, o
    # provedor seria descartado silenciosamente — quebrando os 5 mocks).
    REAL_DRIVERS["santander"] = driver
    # Pan dual-path: API quando a config OpenAPI esta completa; senao portal web.
    REAL_DRIVERS["pan"] = _pan_dispatch
    # Fontecred: nome canônico minúsculo (mock homônimo é "Fontcred", sem 'e').
    REAL_DRIVERS["fontecred"] = fabrica_fontecred()
    # Bradesco (Turbo Lojista): banco novo, sem homônimo mock.
    REAL_DRIVERS["bradesco"] = fabrica_bradesco()


def _pan_dispatch(
    sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
) -> list[ResultadoDriver]:
    """Escolhe o caminho Pan por credencial: API (OpenAPI completa) ou portal web.

    Se a config tiver todos os campos OpenAPI (api_key/secret/id_loja/...), usa o
    ``PanDriver`` HTTP. Senao (so usuario+senha de lojista), cai no
    ``PanPortalDriver`` (Playwright). Instancia sob demanda para nao abrir browser
    quando a API resolve.
    """
    from app.motor.pan import _CAMPOS_CONFIG, fabrica_pan
    from app.motor.pan_portal import fabrica_pan_portal

    cfg: dict = {}
    if ctx is not None and ctx.db is not None and ctx.cliente_id:
        from app.credenciais import obter_configuracao_para_uso

        cfg = obter_configuracao_para_uso(ctx.db, ctx.cliente_id, "pan") or {}
    tem_api = all(str(cfg.get(c, "")).strip() for c in _CAMPOS_CONFIG)
    driver = fabrica_pan() if tem_api else fabrica_pan_portal()
    return driver(sol, ctx)


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
        elif p in REAL_DRIVERS or p in {"santander", "pan", "fontecred", "bradesco"}:
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
    from app.credenciais import configuracao_completa

    return configuracao_completa(db, cliente_id, provedor)
