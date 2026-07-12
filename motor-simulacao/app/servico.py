"""Orquestração da simulação: valida, enfileira o job, persiste e aplica idempotência.

Plano #1A, Tasks 4-6: a criação apenas valida e enfileira (status ``recebida``); a
execução dos provedores, com timeout/retry e resultados parciais, fica a cargo do
worker (``app.processamento``). Nada de provedor roda de forma síncrona no POST.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import config, cripto
from app.models_db import IdempotenciaORM, SimulacaoORM
from app.motor.base import ResultadoProvedor, Simulacao, SolicitacaoSimulacao
from app.validadores import idade, parse_nascimento, valida_cpf

ESTADOS_CANCELAVEIS = {"recebida", "processando"}


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
    db: Session,
    sol: SolicitacaoSimulacao,
    cliente_id: str,
    idempotency_key: str | None = None,
) -> tuple[SimulacaoORM, bool]:
    """Retorna (simulacao, criada). `criada=False` quando reusa por idempotência."""
    _validar(sol)
    payload_hash = _hash_payload(sol)

    if idempotency_key:
        existente = db.get(IdempotenciaORM, (cliente_id, idempotency_key))
        if existente is not None:
            if existente.request_hash != payload_hash:
                raise ErroIdempotencia()
            return db.get(SimulacaoORM, existente.simulacao_id), False

    payload_pessoal = json.dumps(
        {
            "cpf": sol.pessoa.cpf,
            "nascimento": sol.pessoa.nascimento,
            "renda": sol.pessoa.renda,
        }
    )
    # Enfileira: status 'recebida'. O worker executa os provedores depois.
    sim = SimulacaoORM(
        id=str(uuid.uuid4()),
        cliente_id=cliente_id,
        referencia_externa=sol.referencia_externa,
        status="recebida",
        payload_cifrado=cripto.cifrar(payload_pessoal),
        cpf_indice_cego=cripto.indice_cego(sol.pessoa.cpf),
        categoria=sol.veiculo.categoria,
        valor=sol.veiculo.valor,
        entrada=sol.condicoes.entrada,
        prazo_meses=sol.condicoes.prazo_meses,
        provedores=sol.provedores,
    )
    db.add(sim)
    db.flush()

    if idempotency_key:
        db.add(
            IdempotenciaORM(
                cliente_id=cliente_id,
                chave=idempotency_key,
                request_hash=payload_hash,
                simulacao_id=sim.id,
            )
        )
    db.commit()
    db.refresh(sim)
    return sim, True


def obter_simulacao(db: Session, sim_id: str, cliente_id: str) -> SimulacaoORM | None:
    return db.query(SimulacaoORM).filter_by(id=sim_id, cliente_id=cliente_id).one_or_none()


def cancelar_simulacao(db: Session, sim_id: str, cliente_id: str) -> SimulacaoORM | None:
    """Cancela um job ainda não terminal. Jobs já concluídos/falhos ficam inalterados."""
    sim = obter_simulacao(db, sim_id, cliente_id)
    if sim is None:
        return None
    if sim.status in ESTADOS_CANCELAVEIS:
        sim.status = "cancelada"
        sim.atualizada_em = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sim)
    return sim


def _num(valor) -> float | None:
    return float(valor) if valor is not None else None


def para_pydantic(sim: SimulacaoORM) -> Simulacao:
    return Simulacao(
        id=sim.id,
        status=sim.status,
        criada_em=sim.criada_em.isoformat(),
        resultados=[
            ResultadoProvedor(
                provedor=r.provedor,
                status=r.status,
                valor_parcela=_num(r.valor_parcela),
                taxa_am=_num(r.taxa_am),
                prazo_meses=r.prazo_meses,
                valor_financiado=_num(r.valor_financiado),
                codigo_erro=r.codigo_erro,
            )
            for r in sim.resultados
        ],
    )
