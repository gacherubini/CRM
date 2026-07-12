"""Núcleo do worker (Plano #1A, Task 6): reserva de job, execução por provedor,
resultados parciais, retry/timeout e máquina de estado geral.

Estados gerais: recebida → processando → (concluida | parcial | falhou |
aguardando_intervencao). ``cancelada`` é terminal e nunca é reservada.
"""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import config, cripto
from app.models_db import ResultadoORM, SimulacaoORM, SimulacaoTentativaORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    Driver,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
    resolver_drivers,
)

MAX_TENTATIVAS_DRIVER = 2


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def reencaminhar_jobs_expirados(db: Session, agora: datetime | None = None) -> int:
    """Devolve à fila reservas cujo lease expirou após queda do worker."""
    instante = agora or _agora()
    linhas = (
        db.query(SimulacaoORM)
        .filter(
            SimulacaoORM.status == "processando",
            SimulacaoORM.reservada_ate.is_not(None),
            SimulacaoORM.reservada_ate < instante,
        )
        .update(
            {
                "status": "recebida",
                "reserva_token": None,
                "reservada_ate": None,
                "atualizada_em": instante,
            },
            synchronize_session=False,
        )
    )
    if linhas:
        db.commit()
    return linhas


def reservar_proximo_job(db: Session) -> Optional[SimulacaoORM]:
    """Reserva atomicamente o próximo job ``recebida`` marcando-o ``processando``.

    O UPDATE condicional (``WHERE status='recebida'``) garante que dois workers não
    peguem o mesmo job: só quem alterar exatamente 1 linha fica com o job.
    """
    sim = (
        db.query(SimulacaoORM)
        .filter(SimulacaoORM.status == "recebida")
        .order_by(SimulacaoORM.criada_em.asc())
        .first()
    )
    if sim is None:
        return None
    token = str(uuid.uuid4())
    agora = _agora()
    linhas = (
        db.query(SimulacaoORM)
        .filter(SimulacaoORM.id == sim.id, SimulacaoORM.status == "recebida")
        .update(
            {
                "status": "processando",
                "reserva_token": token,
                "reservada_ate": agora + timedelta(seconds=config.JOB_LEASE_SECONDS),
                "atualizada_em": agora,
            }
        )
    )
    db.commit()
    if linhas != 1:
        return None  # outro worker levou o job
    db.refresh(sim)
    return sim


def _reconstruir_solicitacao(sim: SimulacaoORM) -> SolicitacaoSimulacao:
    pessoal = json.loads(cripto.decifrar(sim.payload_cifrado)) if sim.payload_cifrado else {}
    return SolicitacaoSimulacao(
        referencia_externa=sim.referencia_externa,
        pessoa=Pessoa(
            cpf=pessoal.get("cpf", ""),
            nascimento=pessoal.get("nascimento", ""),
            renda=pessoal.get("renda"),
        ),
        veiculo=Veiculo(categoria=sim.categoria or "moto", valor=float(sim.valor or 0)),
        condicoes=Condicoes(entrada=float(sim.entrada or 0), prazo_meses=sim.prazo_meses or 0),
        provedores=sim.provedores or ["mock"],
    )


def _registrar_tentativa(
    db: Session, sim_id: str, provedor: str, tentativa: int,
    duracao_ms: int, status: str, codigo_erro: Optional[str],
) -> None:
    db.add(
        SimulacaoTentativaORM(
            simulacao_id=sim_id, provedor=provedor, tentativa=tentativa,
            duracao_ms=duracao_ms, status=status, codigo_erro=codigo_erro,
        )
    )


def _executar_driver(
    db: Session, sim: SimulacaoORM, nome: str, driver: Driver, sol: SolicitacaoSimulacao
) -> ResultadoDriver:
    """Roda um provedor com retry para erros transitórios; devolve o resultado final."""
    prazo = sol.condicoes.prazo_meses
    for tentativa in range(1, MAX_TENTATIVAS_DRIVER + 1):
        inicio = time.perf_counter()
        try:
            res = driver(sol)
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "concluida", None)
            return res
        except IntervencaoNecessaria as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "aguardando_intervencao", e.codigo)
            return ResultadoDriver(nome, "aguardando_intervencao", prazo_meses=prazo, codigo_erro=e.codigo)
        except RejeicaoNegocio as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "rejeitada", e.codigo)
            return ResultadoDriver(nome, "rejeitada", prazo_meses=prazo, codigo_erro=e.codigo)
        except (ErroTransitorio, TimeoutError) as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            codigo = getattr(e, "codigo", "timeout")
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "erro_transitorio", codigo)
            if tentativa >= MAX_TENTATIVAS_DRIVER:
                return ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)
            # senão, tenta de novo
    # inalcançável, mas mantém o tipo
    return ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro="desconhecido")


def _status_geral(resultados: list[ResultadoDriver]) -> str:
    if not resultados:
        return "falhou"
    ok = [r for r in resultados if r.status == "concluida"]
    if len(ok) == len(resultados):
        return "concluida"
    if ok:
        return "parcial"
    if any(r.status == "aguardando_intervencao" for r in resultados):
        return "aguardando_intervencao"
    return "falhou"


def processar_job(
    db: Session,
    sim_id: str,
    drivers: Optional[list[tuple[str, Driver]]] = None,
    reserva_token: str | None = None,
) -> Optional[SimulacaoORM]:
    """Executa cada provedor, grava resultados parciais e define o estado final."""
    sim = db.get(SimulacaoORM, sim_id)
    if sim is None or sim.status != "processando":
        return sim  # cancelado/terminal: não processa
    token = reserva_token or sim.reserva_token
    if not token or sim.reserva_token != token:
        return sim
    sol = _reconstruir_solicitacao(sim)
    pares = drivers if drivers is not None else resolver_drivers(sol.provedores)

    existentes = {resultado.provedor: resultado for resultado in sim.resultados}
    resultados: list[ResultadoDriver] = [
        ResultadoDriver(
            resultado.provedor,
            resultado.status,
            valor_parcela=resultado.valor_parcela,
            taxa_am=resultado.taxa_am,
            prazo_meses=resultado.prazo_meses,
            valor_financiado=resultado.valor_financiado,
            codigo_erro=resultado.codigo_erro,
        )
        for resultado in existentes.values()
    ]
    for nome, driver in pares:
        if nome in existentes:
            continue
        sim.reservada_ate = _agora() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        sim.atualizada_em = _agora()
        db.commit()
        res = _executar_driver(db, sim, nome, driver, sol)
        db.refresh(sim)
        if sim.status != "processando" or sim.reserva_token != token:
            db.rollback()
            return sim
        db.add(
            ResultadoORM(
                simulacao_id=sim.id, provedor=res.provedor, status=res.status,
                valor_parcela=res.valor_parcela, taxa_am=res.taxa_am,
                prazo_meses=res.prazo_meses if res.prazo_meses is not None else sol.condicoes.prazo_meses,
                valor_financiado=res.valor_financiado, codigo_erro=res.codigo_erro,
            )
        )
        db.commit()  # checkpoint: retomada não repete provedor já persistido
        resultados.append(res)

    sim.status = _status_geral(resultados)
    sim.atualizada_em = _agora()
    sim.reserva_token = None
    sim.reservada_ate = None
    db.commit()
    db.refresh(sim)
    return sim


def processar_proximo(db: Session, drivers=None) -> Optional[SimulacaoORM]:
    """Reserva e processa um job. Retorna a simulação processada ou None se a fila vazia."""
    reencaminhar_jobs_expirados(db)
    sim = reservar_proximo_job(db)
    if sim is None:
        return None
    return processar_job(db, sim.id, drivers, sim.reserva_token)


def drenar_fila(db: Session, drivers=None, limite: int = 1000) -> int:
    """Processa toda a fila pendente. Retorna quantos jobs foram processados."""
    processados = 0
    while processados < limite and processar_proximo(db, drivers) is not None:
        processados += 1
    return processados
