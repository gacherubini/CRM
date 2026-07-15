"""Núcleo do worker (Plano #1A Task 6 + Task 12 multi-prazo).

Estados gerais: recebida → processando → (concluida | parcial | falhou |
aguardando_intervencao). ``cancelada`` é terminal e nunca é reservada.
"""
from __future__ import annotations

import json
import signal
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import config, cripto
from app.fanout import STATUS_TERMINAIS_TAREFA, marcar_tarefa, obter_tarefa
from app.models_db import (
    ResultadoORM,
    SimulacaoEventoORM,
    SimulacaoORM,
    SimulacaoProvedorORM,
    SimulacaoTentativaORM,
)
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


class DriverDeadlineExceeded(TimeoutError):
    pass


@contextmanager
def _limite_total_driver(segundos: int):
    """Deadline duro no worker Linux; impede Playwright preso para sempre."""
    if (
        segundos <= 0
        or threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGALRM")
    ):
        yield
        return
    anterior = signal.getsignal(signal.SIGALRM)

    def _estourou(signum, frame):
        raise DriverDeadlineExceeded("driver excedeu o tempo máximo")

    signal.signal(signal.SIGALRM, _estourou)
    # Repete durante o unwind para também interromper um browser.close() travado.
    signal.setitimer(signal.ITIMER_REAL, segundos, 5)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, anterior)


def _invocar_driver(driver: Driver, sol: SolicitacaoSimulacao, ctx: DriverContext | None):
    """Aceita drivers novos ``(sol, ctx)`` e legados ``(sol,)``."""
    try:
        return driver(sol, ctx)
    except TypeError:
        return driver(sol)


def _invocar_driver_com_deadline(
    driver: Driver,
    sol: SolicitacaoSimulacao,
    ctx: DriverContext | None,
    segundos: int,
):
    """Aplica deadline também onde SIGALRM não existe, como no Windows."""
    if segundos <= 0:
        return _invocar_driver(driver, sol, ctx)
    if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGALRM"):
        with _limite_total_driver(segundos):
            return _invocar_driver(driver, sol, ctx)

    resultado: list[object] = []
    erro: list[BaseException] = []
    concluido = threading.Event()

    def executar() -> None:
        try:
            resultado.append(_invocar_driver(driver, sol, ctx))
        except BaseException as exc:
            erro.append(exc)
        finally:
            concluido.set()

    thread = threading.Thread(target=executar, name="motor-driver-deadline", daemon=True)
    thread.start()
    if not concluido.wait(segundos):
        raise DriverDeadlineExceeded("driver excedeu o tempo máximo")
    if erro:
        raise erro[0]
    return resultado[0]


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
    _registrar_evento(
        db, sim, "job_reservado", "Job reservado pelo worker para processamento."
    )
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
            ddd=pessoal.get("ddd"),
            celular=pessoal.get("celular"),
            codigo_natureza_ocupacao=pessoal.get("codigo_natureza_ocupacao"),
        ),
        veiculo=Veiculo(
            categoria=sim.categoria or "moto",
            valor=float(sim.valor) if sim.valor is not None else None,
            placa=sim.placa,
            uf_licenciamento=sim.uf_licenciamento,
            finalidade=sim.finalidade,
            codigo_provedor=sim.codigo_veiculo_provedor,
            ano_modelo=sim.ano_modelo,
            zero_km=sim.zero_km,
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


def _registrar_evento(
    db: Session,
    sim: SimulacaoORM,
    etapa: str,
    mensagem: str,
    nivel: str = "info",
    screenshot_path: str | None = None,
    provedor: str | None = None,
) -> None:
    """Persiste evento imediatamente para o Portal enxergar durante o job."""
    seguro = " ".join(str(mensagem).replace("\n", " ").split())[:240]
    db.add(
        SimulacaoEventoORM(
            simulacao_id=sim.id,
            provedor=provedor,
            etapa=str(etapa)[:80],
            nivel=nivel if nivel in {"info", "sucesso", "aviso", "erro"} else "info",
            mensagem=seguro,
            screenshot_path=screenshot_path,
        )
    )
    if sim.status == "processando":
        sim.reservada_ate = _agora() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        sim.atualizada_em = _agora()
    db.commit()


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
            res = _invocar_driver_com_deadline(
                driver, sol, ctx, config.DRIVER_TIMEOUT_SECONDS
            )
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "concluida", None)
            return res if isinstance(res, list) else [res]
        except DriverDeadlineExceeded:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(
                db, sim.id, nome, tentativa, dur, "erro", "timeout_driver"
            )
            if ctx is not None:
                ctx.registrar_evento(
                    "timeout_driver",
                    "O banco excedeu o tempo máximo e a execução foi encerrada.",
                    "erro",
                )
            return [
                ResultadoDriver(
                    nome, "erro", prazo_meses=prazo, codigo_erro="timeout_driver"
                )
            ]
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
        falha_prov = (sol.provedores or ["?"])[0]
        db.add(
            ResultadoORM(
                simulacao_id=sim.id,
                provedor=falha_prov,
                status="erro",
                codigo_erro="sem_driver_ou_credencial",
            )
        )
        db.add(
            SimulacaoEventoORM(
                simulacao_id=sim.id,
                provedor=falha_prov if falha_prov != "?" else None,
                etapa="sem_driver",
                nivel="erro",
                mensagem="Nenhum driver habilitado ou credencial válida foi encontrado.",
            )
        )
        for nome_p in sol.provedores or []:
            marcar_tarefa(
                db, sim.id, nome_p, "falhou", codigo_erro="sem_driver_ou_credencial"
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
    def _evento_ctx(etapa, mensagem, nivel="info", screenshot_path=None, provedor=None):
        _registrar_evento(
            db, sim, etapa, mensagem, nivel, screenshot_path, provedor=provedor
        )

    def _nome_tarefa(nome_driver: str) -> str | None:
        """Mock expande em vários bancos; a tarefa pedida pode ser só ``mock``."""
        if obter_tarefa(db, sim.id, nome_driver) is not None:
            return nome_driver
        if obter_tarefa(db, sim.id, "mock") is not None:
            return "mock"
        return None

    ctx = DriverContext(
        db=db,
        cliente_id=sim.cliente_id,
        screenshot_dir=config.SCREENSHOT_DIR,
        simulacao_id=sim.id,
        evento=_evento_ctx,
    )
    for nome, driver in pares:
        if nome in existentes_por_prov:
            continue
        sim.reservada_ate = _agora() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        sim.atualizada_em = _agora()
        tarefa_nome = _nome_tarefa(nome)
        if tarefa_nome:
            tarefa = obter_tarefa(db, sim.id, tarefa_nome)
            if tarefa is not None and tarefa.status == "recebida":
                marcar_tarefa(
                    db, sim.id, tarefa_nome, "processando", incrementar_tentativa=True
                )
        db.commit()
        _registrar_evento(
            db,
            sim,
            "driver_iniciado",
            f"Conector {nome} iniciado (tentativas limitadas).",
            provedor=nome,
        )
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

    # Consolida tarefas fan-out a partir dos resultados (inclui mock expandido).
    _sincronizar_tarefas_com_resultados(db, sim, resultados)

    sim.status = _status_geral(resultados)
    sim.atualizada_em = _agora()
    sim.reserva_token = None
    sim.reservada_ate = None
    db.add(
        SimulacaoEventoORM(
            simulacao_id=sim.id,
            etapa="job_finalizado",
            nivel="sucesso" if sim.status in {"concluida", "parcial"} else "erro",
            mensagem=f"Simulação finalizada com status {sim.status}.",
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def _status_de_resultados_tarefa(
    linhas: list[ResultadoDriver],
) -> tuple[str, str | None]:
    if not linhas:
        return "falhou", "sem_resultado"
    statuses = {r.status for r in linhas}
    codigo = next((r.codigo_erro for r in linhas if r.codigo_erro), None)
    if "concluida" in statuses:
        return "concluida", codigo
    if "aguardando_intervencao" in statuses:
        return "falhou", codigo or "aguardando_intervencao"
    if "rejeitada" in statuses:
        return "rejeitada", codigo
    return "falhou", codigo


def _sincronizar_tarefas_com_resultados(
    db: Session, sim: SimulacaoORM, resultados: list[ResultadoDriver]
) -> None:
    """Fecha tarefas abertas com base nos resultados do job (fan-out)."""
    tarefas = (
        db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim.id).all()
    )
    if not tarefas:
        return
    por_prov: dict[str, list[ResultadoDriver]] = {}
    for r in resultados:
        por_prov.setdefault(r.provedor, []).append(r)
        # nomes canônicos minúsculos também (driver real)
        por_prov.setdefault((r.provedor or "").lower(), []).append(r)

    for tarefa in tarefas:
        if tarefa.status in STATUS_TERMINAIS_TAREFA:
            continue
        if tarefa.provedor == "mock":
            linhas = list(resultados)
        else:
            linhas = por_prov.get(tarefa.provedor) or por_prov.get(
                tarefa.provedor.lower(), []
            )
        status_t, codigo = _status_de_resultados_tarefa(linhas)
        marcar_tarefa(db, sim.id, tarefa.provedor, status_t, codigo_erro=codigo)


# --- Fan-out: reserva e execução por tarefa (um banco) -------------------------

STATUS_TAREFA_FILA = frozenset({"recebida", "acordando_worker"})
STATUS_TAREFA_EM_VOO = frozenset({"reservada", "processando", "acordando_worker"})


def reencaminhar_tarefas_expiradas(db: Session, agora: datetime | None = None) -> int:
    """Devolve à fila tarefas cujo lease expirou (crash do worker)."""
    instante = agora or _agora()
    linhas = (
        db.query(SimulacaoProvedorORM)
        .filter(
            SimulacaoProvedorORM.status.in_(("reservada", "processando")),
            SimulacaoProvedorORM.reservada_ate.is_not(None),
            SimulacaoProvedorORM.reservada_ate < instante,
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


def _filtro_tipos_worker() -> frozenset[str] | None:
    return config.WORKER_TIPOS


def reservar_proxima_tarefa(
    db: Session,
    *,
    provedor: str | None = None,
    tipos: frozenset[str] | None = None,
) -> Optional[SimulacaoProvedorORM]:
    """Reserva atomicamente a próxima tarefa pendente (FIFO)."""
    reencaminhar_tarefas_expiradas(db)
    q = (
        db.query(SimulacaoProvedorORM)
        .filter(SimulacaoProvedorORM.status.in_(tuple(STATUS_TAREFA_FILA)))
        .order_by(SimulacaoProvedorORM.criada_em.asc())
    )
    filtro_prov = provedor or config.WORKER_PROVEDOR
    if filtro_prov:
        q = q.filter(SimulacaoProvedorORM.provedor == filtro_prov)
    tipos_ok = tipos if tipos is not None else _filtro_tipos_worker()
    if tipos_ok:
        q = q.filter(SimulacaoProvedorORM.tipo_driver.in_(tuple(tipos_ok)))
    tarefa = q.first()
    if tarefa is None:
        return None
    token = str(uuid.uuid4())
    agora = _agora()
    lease = agora + timedelta(seconds=config.TASK_LEASE_SECONDS)
    nova_tentativa = int(tarefa.tentativa or 0) + 1
    linhas = (
        db.query(SimulacaoProvedorORM)
        .filter(
            SimulacaoProvedorORM.id == tarefa.id,
            SimulacaoProvedorORM.status.in_(tuple(STATUS_TAREFA_FILA)),
        )
        .update(
            {
                "status": "processando",
                "reserva_token": token,
                "reservada_ate": lease,
                "iniciada_em": agora,
                "tentativa": nova_tentativa,
                "atualizada_em": agora,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if linhas != 1:
        return None
    db.refresh(tarefa)
    # Job-pai em processando
    sim = db.get(SimulacaoORM, tarefa.simulacao_id)
    if sim is not None and sim.status in ("recebida",):
        sim.status = "processando"
        sim.atualizada_em = agora
        db.commit()
    if sim is not None:
        _registrar_evento(
            db,
            sim,
            "tarefa_reservada",
            f"Tarefa {tarefa.provedor} reservada pelo worker.",
            provedor=tarefa.provedor,
        )
    return tarefa


def _persistir_resultados_tarefa(
    db: Session,
    sim: SimulacaoORM,
    sol: SolicitacaoSimulacao,
    res_lista: list[ResultadoDriver],
) -> None:
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


def agregar_status_job_pai(db: Session, sim_id: str) -> Optional[SimulacaoORM]:
    """Recalcula status do job-pai a partir das tarefas (não apaga resultados)."""
    sim = db.get(SimulacaoORM, sim_id)
    if sim is None:
        return None
    tarefas = (
        db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim_id).all()
    )
    if not tarefas:
        return sim
    if any(t.status not in STATUS_TERMINAIS_TAREFA for t in tarefas):
        if sim.status not in STATUS_TERMINAIS_TAREFA | {"processando", "recebida", "aguardando_intervencao"}:
            pass
        if sim.status in ("recebida",) or sim.status not in (
            "concluida",
            "parcial",
            "falhou",
            "cancelada",
            "aguardando_intervencao",
        ):
            # Mantém processando enquanto houver tarefa aberta
            if sim.status != "cancelada":
                sim.status = "processando"
                sim.atualizada_em = _agora()
                db.commit()
        return sim

    # Todas terminais: agrega pelos resultados (fonte canônica de oferta)
    resultados = [
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
        for r in sim.resultados
    ]
    if not resultados:
        # Sem linhas de resultado: usa status das tarefas
        if all(t.status == "cancelada" for t in tarefas):
            final = "cancelada"
        elif any(t.status == "concluida" for t in tarefas):
            final = "parcial" if any(t.status != "concluida" for t in tarefas) else "concluida"
        else:
            final = "falhou"
    else:
        final = _status_geral(resultados)
    sim.status = final
    sim.atualizada_em = _agora()
    sim.reserva_token = None
    sim.reservada_ate = None
    db.add(
        SimulacaoEventoORM(
            simulacao_id=sim.id,
            etapa="job_finalizado",
            nivel="sucesso" if final in {"concluida", "parcial"} else "erro",
            mensagem=f"Simulação finalizada com status {final}.",
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def processar_tarefa_provedor(
    db: Session,
    tarefa_id: str,
    reserva_token: str | None = None,
    drivers: Optional[list[tuple[str, Driver]]] = None,
) -> Optional[SimulacaoProvedorORM]:
    """Executa um único banco (tarefa-filha) e agrega o job-pai se completo."""
    tarefa = db.get(SimulacaoProvedorORM, tarefa_id)
    if tarefa is None or tarefa.status != "processando":
        return tarefa
    token = reserva_token or tarefa.reserva_token
    if not token or tarefa.reserva_token != token:
        return tarefa

    sim = db.get(SimulacaoORM, tarefa.simulacao_id)
    if sim is None:
        marcar_tarefa(db, tarefa.simulacao_id, tarefa.provedor, "falhou", codigo_erro="sim_ausente")
        db.commit()
        return tarefa
    if sim.status == "cancelada":
        marcar_tarefa(db, sim.id, tarefa.provedor, "cancelada")
        db.commit()
        return tarefa

    sol = _reconstruir_solicitacao(sim)
    # Só este provedor (mock expande internamente em resolver_drivers)
    pedidos = [tarefa.provedor]
    pares = (
        drivers
        if drivers is not None
        else resolver_drivers(pedidos, cliente_id=sim.cliente_id, db=db)
    )

    existentes = {r.provedor for r in sim.resultados}
    # Se já há resultado para este provedor canônico, fecha tarefa sem reexecutar
    if tarefa.provedor != "mock" and tarefa.provedor in existentes:
        marcar_tarefa(db, sim.id, tarefa.provedor, "concluida")
        db.commit()
        agregar_status_job_pai(db, sim.id)
        db.refresh(tarefa)
        return tarefa

    if not pares:
        db.add(
            ResultadoORM(
                simulacao_id=sim.id,
                provedor=tarefa.provedor,
                status="erro",
                codigo_erro="sem_driver_ou_credencial",
            )
        )
        marcar_tarefa(
            db, sim.id, tarefa.provedor, "falhou", codigo_erro="sem_driver_ou_credencial"
        )
        _registrar_evento(
            db,
            sim,
            "sem_driver",
            f"Sem driver/credencial para {tarefa.provedor}.",
            "erro",
            provedor=tarefa.provedor,
        )
        db.commit()
        agregar_status_job_pai(db, sim.id)
        db.refresh(tarefa)
        return tarefa

    def _evento_ctx(etapa, mensagem, nivel="info", screenshot_path=None, provedor=None):
        _registrar_evento(
            db,
            sim,
            etapa,
            mensagem,
            nivel,
            screenshot_path,
            provedor=provedor or tarefa.provedor,
        )

    ctx = DriverContext(
        db=db,
        cliente_id=sim.cliente_id,
        screenshot_dir=config.SCREENSHOT_DIR,
        simulacao_id=sim.id,
        evento=_evento_ctx,
    )

    todos_res: list[ResultadoDriver] = []
    for nome, driver in pares:
        if nome in existentes and tarefa.provedor != "mock":
            continue
        tarefa.reservada_ate = _agora() + timedelta(seconds=config.TASK_LEASE_SECONDS)
        tarefa.atualizada_em = _agora()
        db.commit()
        _registrar_evento(
            db,
            sim,
            "driver_iniciado",
            f"Conector {nome} iniciado (tentativas limitadas).",
            provedor=nome,
        )
        res_lista = _executar_driver(db, sim, nome, driver, sol, ctx)
        db.refresh(tarefa)
        if tarefa.reserva_token != token or tarefa.status != "processando":
            db.rollback()
            return tarefa
        db.refresh(sim)
        if sim.status == "cancelada":
            marcar_tarefa(db, sim.id, tarefa.provedor, "cancelada")
            db.commit()
            return tarefa
        _persistir_resultados_tarefa(db, sim, sol, res_lista)
        db.commit()
        todos_res.extend(res_lista)

    status_t, codigo = _status_de_resultados_tarefa(todos_res)
    marcar_tarefa(db, sim.id, tarefa.provedor, status_t, codigo_erro=codigo)
    tarefa.reserva_token = None
    tarefa.reservada_ate = None
    db.commit()
    agregar_status_job_pai(db, sim.id)
    db.refresh(tarefa)
    return tarefa


def processar_proxima_tarefa(
    db: Session,
    drivers=None,
    *,
    provedor: str | None = None,
) -> Optional[SimulacaoProvedorORM]:
    """Reserva e processa uma tarefa. None se fila vazia para este worker."""
    tarefa = reservar_proxima_tarefa(db, provedor=provedor)
    if tarefa is None:
        return None
    return processar_tarefa_provedor(
        db, tarefa.id, tarefa.reserva_token, drivers=drivers
    )


def processar_proximo(db: Session, drivers=None) -> Optional[SimulacaoORM]:
    """Reserva e processa: tarefas (fan-out) ou job legado.

    Com ``FANOUT_ENABLED`` e tarefas na fila, prefere o caminho por banco.
    Jobs antigos sem tarefas continuam no pipeline sequential.
    """
    reencaminhar_jobs_expirados(db)
    reencaminhar_tarefas_expiradas(db)

    if config.FANOUT_ENABLED:
        tarefa = processar_proxima_tarefa(db, drivers=drivers)
        if tarefa is not None:
            return db.get(SimulacaoORM, tarefa.simulacao_id)
        # Jobs com tarefas-filhas não entram no monólito; só legados sem tarefas.
        ids_com_tarefa = {
            row[0]
            for row in db.query(SimulacaoProvedorORM.simulacao_id).distinct().all()
        }
        if ids_com_tarefa:
            # Reserva seletiva: primeiro "recebida" fora do conjunto fan-out
            candidatos = (
                db.query(SimulacaoORM)
                .filter(
                    SimulacaoORM.status == "recebida",
                    ~SimulacaoORM.id.in_(ids_com_tarefa),
                )
                .order_by(SimulacaoORM.criada_em.asc())
                .all()
            )
            for cand in candidatos:
                sim = reservar_proximo_job_id(db, cand.id)
                if sim is not None:
                    return processar_job(db, sim.id, drivers, sim.reserva_token)
            return None

    sim = reservar_proximo_job(db)
    if sim is None:
        return None
    return processar_job(db, sim.id, drivers, sim.reserva_token)


def reservar_proximo_job_id(db: Session, sim_id: str) -> Optional[SimulacaoORM]:
    """Reserva um job específico se ainda estiver ``recebida``."""
    token = str(uuid.uuid4())
    agora = _agora()
    linhas = (
        db.query(SimulacaoORM)
        .filter(SimulacaoORM.id == sim_id, SimulacaoORM.status == "recebida")
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
    sim = db.get(SimulacaoORM, sim_id)
    if sim is None:
        return None
    _registrar_evento(
        db, sim, "job_reservado", "Job reservado pelo worker para processamento."
    )
    return sim


def drenar_fila(db: Session, drivers=None, limite: int = 1000) -> int:
    """Processa toda a fila pendente. Retorna quantos jobs/tarefas processou."""
    processados = 0
    while processados < limite and processar_proximo(db, drivers) is not None:
        processados += 1
    return processados
