"""Orquestração da simulação: valida, executa provedores, persiste e aplica idempotência.

Milestone 2 (Plano #1A, Tasks 4-5): resultado gravado em Postgres/SQLite e
`Idempotency-Key` por requisição. O mock ainda conclui de forma síncrona; o worker
assíncrono com timeout/retry e resultados parciais entra na Task 6.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import IdempotenciaORM, ResultadoORM, SimulacaoORM
from app.motor.base import ResultadoProvedor, Simulacao, SolicitacaoSimulacao
from app.motor.mock import simular_mock
from app.validadores import idade, parse_nascimento, valida_cpf


class ErroValidacao(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ErroIdempotencia(Exception):
    code = "idempotency_key_conflito"
    message = "Idempotency-Key já usada com um payload diferente"


def _hash_payload(sol: SolicitacaoSimulacao) -> str:
    dados = json.dumps(sol.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(dados.encode()).hexdigest()


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


def criar_simulacao(
    db: Session, sol: SolicitacaoSimulacao, idempotency_key: str | None = None
) -> tuple[SimulacaoORM, bool]:
    """Retorna (simulacao, criada). `criada=False` quando reusa por idempotência."""
    _validar(sol)
    payload_hash = _hash_payload(sol)

    if idempotency_key:
        existente = db.get(IdempotenciaORM, idempotency_key)
        if existente is not None:
            if existente.request_hash != payload_hash:
                raise ErroIdempotencia()
            return db.get(SimulacaoORM, existente.simulacao_id), False

    sim = SimulacaoORM(
        id=str(uuid.uuid4()),
        referencia_externa=sol.referencia_externa,
        status="concluida",
    )
    for r in simular_mock(sol):
        sim.resultados.append(
            ResultadoORM(
                provedor=r.provedor,
                status=r.status,
                valor_parcela=r.valor_parcela,
                taxa_am=r.taxa_am,
                prazo_meses=r.prazo_meses,
                valor_financiado=r.valor_financiado,
                codigo_erro=r.codigo_erro,
            )
        )
    db.add(sim)
    db.flush()

    if idempotency_key:
        db.add(
            IdempotenciaORM(
                chave=idempotency_key, request_hash=payload_hash, simulacao_id=sim.id
            )
        )
    db.commit()
    db.refresh(sim)
    return sim, True


def obter_simulacao(db: Session, sim_id: str) -> SimulacaoORM | None:
    return db.get(SimulacaoORM, sim_id)


def cancelar_simulacao(db: Session, sim_id: str) -> SimulacaoORM | None:
    sim = db.get(SimulacaoORM, sim_id)
    if sim is None:
        return None
    if sim.status != "cancelada":
        sim.status = "cancelada"
        sim.atualizada_em = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sim)
    return sim


def para_pydantic(sim: SimulacaoORM) -> Simulacao:
    return Simulacao(
        id=sim.id,
        status=sim.status,
        criada_em=sim.criada_em.isoformat(),
        resultados=[
            ResultadoProvedor(
                provedor=r.provedor,
                status=r.status,
                valor_parcela=float(r.valor_parcela),
                taxa_am=float(r.taxa_am),
                prazo_meses=r.prazo_meses,
                valor_financiado=float(r.valor_financiado),
                codigo_erro=r.codigo_erro,
            )
            for r in sim.resultados
        ],
    )
