"""Orquestração da simulação: valida, executa provedores e guarda o resultado.

Milestone 1: execução síncrona do mock e armazenamento em memória. O pipeline
assíncrono (worker + Postgres + idempotência) entra nas Tasks 4-6 do Plano #1A.
"""
import uuid
from datetime import datetime, timezone

from app import config
from app.motor.base import SolicitacaoSimulacao, Simulacao
from app.motor.mock import simular_mock
from app.validadores import idade, parse_nascimento, valida_cpf


class ErroValidacao(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_STORE: dict[str, Simulacao] = {}


def _validar(sol: SolicitacaoSimulacao) -> None:
    if not valida_cpf(sol.pessoa.cpf):
        raise ErroValidacao("cpf_invalido", "CPF inválido")
    nasc = parse_nascimento(sol.pessoa.nascimento)
    if nasc is None:
        raise ErroValidacao("nascimento_invalido", "Data de nascimento inválida")
    if idade(nasc) < config.IDADE_MINIMA:
        raise ErroValidacao("idade_minima", f"Idade mínima é {config.IDADE_MINIMA} anos")
    if sol.veiculo.categoria not in config.CATEGORIAS:
        raise ErroValidacao("categoria_invalida", "Categoria de veículo não suportada")
    if sol.condicoes.entrada < 0 or sol.condicoes.entrada > sol.veiculo.valor:
        raise ErroValidacao("entrada_invalida", "Entrada deve estar entre 0 e o valor do veículo")
    if not (config.PRAZO_MIN <= sol.condicoes.prazo_meses <= config.PRAZO_MAX):
        raise ErroValidacao(
            "prazo_invalido",
            f"Prazo deve estar entre {config.PRAZO_MIN} e {config.PRAZO_MAX} meses",
        )


def criar_simulacao(sol: SolicitacaoSimulacao) -> Simulacao:
    _validar(sol)
    resultados = simular_mock(sol)
    sim = Simulacao(
        id=str(uuid.uuid4()),
        status="concluida",
        criada_em=datetime.now(timezone.utc).isoformat(),
        resultados=resultados,
    )
    _STORE[sim.id] = sim
    return sim


def obter_simulacao(sim_id: str) -> Simulacao | None:
    return _STORE.get(sim_id)
