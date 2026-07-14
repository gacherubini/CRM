"""Núcleo do worker (Plano #1A Task 6 + Task 12 multi-prazo).

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
    DriverContext,
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
    """Reserva atomicamente o próximo job ``recebida`` marcando-o ``processando``."""
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
        return None
    db.refresh(sim)
    return sim


def _reconstruir_solicitacao(sim: SimulacaoORM) -> SolicitacaoSimulacao:
    pessoal = json.loads(cripto.decifrar(sim.payload_cifrado)) if sim.payload_cifrado else {}
    prazos = list(sim.prazos_meses) if sim.prazos_meses else (
        [sim.prazo_meses] if sim.prazo_meses else []
    )
    return SolicitacaoSimulacao(
        referencia_externa=sim.referencia_externa,
        pessoa=Pessoa(
            cpf=pessoal.get("cpf", ""),
            nascimento=pessoal.get("nascimento", ""),
            renda=pessoal.get("renda"),
            cnh=sim.cnh,
        ),
        veiculo=Veiculo(
            categoria=sim.categoria or "moto",
            valor=float(sim.valor) if sim.valor is not None else None,
            placa=sim.placa,
            uf_licenciamento=sim.uf_licenciamento,
            finalidade=sim.finalidade,
        ),
        condicoes=Condicoes(entrada=float(sim.entrada or 0), prazos_meses=prazos),
        provedores=sim.provedores or ["mock"],
    )


def _registrar_tentativa(
    db: Session,
    sim_id: str,
    provedor: str,
    tentativa: int,
    duracao_ms: int,
    status: str,
    codigo_erro: Optional[str],
) -> None:
    db.add(
        SimulacaoTentativaORM(
            simulacao_id=sim_id,
            provedor=provedor,
            tentativa=tentativa,
            duracao_ms=duracao_ms,
            status=status,
            codigo_erro=codigo_erro,
        )
    )


def _executar_driver(
    db: Session,
    sim: SimulacaoORM,
    nome: str,
    driver: Driver,
    sol: SolicitacaoSimulacao,
    ctx: DriverContext | None = None,
) -> list[ResultadoDriver]:
    """Roda um provedor com retry; devolve lista (normaliza único → lista)."""
    prazo = sol.condicoes.prazo_meses
    for tentativa in range(1, MAX_TENTATIVAS_DRIVER + 1):
        inicio = time.perf_counter()
        try:
            # Drivers novos: (sol, ctx). Legados de teste: (sol,) apenas.
            try:
                res = driver(sol, ctx)
            except TypeError:
                res = driver(sol)
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "concluida", None)
            return res if isinstance(res, list) else [res]
        except IntervencaoNecessaria as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(
                db, sim.id, nome, tentativa, dur, "aguardando_intervencao", e.codigo
            )
            return [
                ResultadoDriver(
                    nome, "aguardando_intervencao", prazo_meses=prazo, codigo_erro=e.codigo
                )
            ]
        except RejeicaoNegocio as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "rejeitada", e.codigo)
            return [ResultadoDriver(nome, "rejeitada", prazo_meses=prazo, codigo_erro=e.codigo)]
        except (ErroTransitorio, TimeoutError) as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            codigo = getattr(e, "codigo", "timeout")
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "erro_transitorio", codigo)
            if tentativa >= MAX_TENTATIVAS_DRIVER:
                return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)]
        except Exception as e:
            # Playwright Error, import quebrado, browser ausente, etc. —
            # nunca deixar o job eterno em "processando".
            dur = int((time.perf_counter() - inicio) * 1000)
            msg = str(e).replace("\n", " ")[:200].lower()
            if "executable doesn't exist" in msg or "playwright install" in msg:
                codigo = "browser_ausente"
            elif (
                "missing x server" in msg
                or "xserver" in msg
                or ("display" in msg and "not" in msg)
            ):
                # Xvfb morto / lock órfão após restart do worker.
                codigo = "display_ausente"
            else:
                codigo = "erro_inesperado"
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "erro", codigo)
            if tentativa >= MAX_TENTATIVAS_DRIVER:
                return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)]
    return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro="desconhecido")]


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
    """Executa cada provedor, grava resultados (N por multi-prazo) e define o estado final."""
    sim = db.get(SimulacaoORM, sim_id)
    if sim is None or sim.status != "processando":
        return sim
    token = reserva_token or sim.reserva_token
    if not token or sim.reserva_token != token:
        return sim
    sol = _reconstruir_solicitacao(sim)
    pares = (
        drivers
        if drivers is not None
        else resolver_drivers(sol.provedores, cliente_id=sim.cliente_id, db=db)
    )
    if not pares:
        # Nenhum driver resolvido (ex.: santander sem credencial / nome divergente).
        sim.status = "falhou"
        sim.atualizada_em = _agora()
        sim.reserva_token = None
        sim.reservada_ate = None
        db.add(
            ResultadoORM(
                simulacao_id=sim.id,
                provedor=(sol.provedores or ["?"])[0],
                status="erro",
                codigo_erro="sem_driver_ou_credencial",
            )
        )
        db.commit()
        db.refresh(sim)
        return sim

    existentes_por_prov: dict[str, list] = {}
    for resultado in sim.resultados:
        existentes_por_prov.setdefault(resultado.provedor, []).append(resultado)

    resultados: list[ResultadoDriver] = [
        ResultadoDriver(
            r.provedor,
            r.status,
            valor_parcela=r.valor_parcela,
            taxa_am=r.taxa_am,
            prazo_meses=r.prazo_meses,
            valor_financiado=r.valor_financiado,
            entrada=r.entrada,
            codigo_erro=r.codigo_erro,
        )
        for linhas in existentes_por_prov.values()
        for r in linhas
    ]
    ctx = DriverContext(
        db=db,
        cliente_id=sim.cliente_id,
        screenshot_dir=config.SCREENSHOT_DIR,
    )
    for nome, driver in pares:
        if nome in existentes_por_prov:
            continue
        sim.reservada_ate = _agora() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        sim.atualizada_em = _agora()
        db.commit()
        res_lista = _executar_driver(db, sim, nome, driver, sol, ctx)
        db.refresh(sim)
        if sim.status != "processando" or sim.reserva_token != token:
            db.rollback()
            return sim
        for res in res_lista:
            db.add(
                ResultadoORM(
                    simulacao_id=sim.id,
                    provedor=res.provedor,
                    status=res.status,
                    valor_parcela=res.valor_parcela,
                    taxa_am=res.taxa_am,
                    prazo_meses=(
                        res.prazo_meses
                        if res.prazo_meses is not None
                        else sol.condicoes.prazo_meses
                    ),
                    valor_financiado=res.valor_financiado,
                    entrada=res.entrada,
                    codigo_erro=res.codigo_erro,
                )
            )
        db.commit()
        resultados.extend(res_lista)

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
