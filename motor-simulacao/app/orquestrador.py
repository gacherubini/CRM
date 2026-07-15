"""Acorda workers sob demanda para tarefas Playwright enfileiradas."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import config
from app.lifecycle import WorkerLifecycle, lifecycle_padrao
from app.models_db import SimulacaoEventoORM, SimulacaoProvedorORM, WorkerSlotORM

log = logging.getLogger("motor-orquestrador")

STATUS_PENDENTES = frozenset({"recebida", "acordando_worker"})


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _allowlist_slots(db: Session) -> set[str]:
    rows = (
        db.query(WorkerSlotORM)
        .filter(WorkerSlotORM.habilitado.is_(True))
        .all()
    )
    return {r.fly_machine_id for r in rows if r.fly_machine_id}


def _registrar_evento_sim(
    db: Session, simulacao_id: str, etapa: str, mensagem: str, nivel: str = "info",
    provedor: str | None = None,
) -> None:
    db.add(
        SimulacaoEventoORM(
            simulacao_id=simulacao_id,
            provedor=provedor,
            etapa=etapa[:80],
            nivel=nivel if nivel in {"info", "sucesso", "aviso", "erro"} else "info",
            mensagem=" ".join(str(mensagem).split())[:240],
        )
    )


def slots_para_provedor(db: Session, provedor: str) -> list[WorkerSlotORM]:
    return (
        db.query(WorkerSlotORM)
        .filter(
            WorkerSlotORM.provedor == provedor,
            WorkerSlotORM.habilitado.is_(True),
        )
        .order_by(WorkerSlotORM.criado_em.asc())
        .all()
    )


def acordar_workers(
    db: Session,
    *,
    simulacao_id: str | None = None,
    lifecycle: WorkerLifecycle | None = None,
) -> dict:
    """Inicia Machines para tarefas Playwright pendentes.

    Retorna contadores: acordados, falhas, sem_slot, ignorados.
    Sem ``FLY_AUTOSCALE_ENABLED`` ou sem fan-out: no-op.
    """
    resultado = {"acordados": 0, "falhas": 0, "sem_slot": 0, "ignorados": 0}
    if not config.FANOUT_ENABLED or not config.FLY_AUTOSCALE_ENABLED:
        return resultado

    q = db.query(SimulacaoProvedorORM).filter(
        SimulacaoProvedorORM.status.in_(STATUS_PENDENTES),
        SimulacaoProvedorORM.tipo_driver == "playwright",
    )
    if simulacao_id:
        q = q.filter(SimulacaoProvedorORM.simulacao_id == simulacao_id)
    tarefas = q.order_by(SimulacaoProvedorORM.criada_em.asc()).all()
    if not tarefas:
        return resultado

    allow = _allowlist_slots(db)
    lc = lifecycle or lifecycle_padrao(allowlist=allow)

    # Um wake por provedor (respeita MAX_BROWSER_WORKERS)
    por_provedor: dict[str, list[SimulacaoProvedorORM]] = {}
    for t in tarefas:
        por_provedor.setdefault(t.provedor, []).append(t)

    starts = 0
    teto = max(1, config.MAX_BROWSER_WORKERS)
    for provedor, lista in por_provedor.items():
        if starts >= teto:
            resultado["ignorados"] += len(lista)
            continue
        slots = slots_para_provedor(db, provedor)
        if not slots:
            resultado["sem_slot"] += len(lista)
            for t in lista:
                if simulacao_id or t.simulacao_id:
                    _registrar_evento_sim(
                        db,
                        t.simulacao_id,
                        "worker_indisponivel",
                        f"Sem slot Fly configurado para {provedor}; tarefa fica na fila.",
                        "aviso",
                        provedor=provedor,
                    )
            continue
        slot = slots[0]
        if slot.fly_machine_id not in allow:
            resultado["falhas"] += 1
            continue

        for t in lista:
            if t.status == "recebida":
                t.status = "acordando_worker"
                t.atualizada_em = _agora()
                t.worker_slot_id = slot.id

        _registrar_evento_sim(
            db,
            lista[0].simulacao_id,
            "worker_acordando",
            f"Acordando worker Playwright de {provedor}.",
            "info",
            provedor=provedor,
        )
        db.commit()

        ok = lc.start(slot.fly_machine_id)
        agora = _agora()
        if ok:
            slot.estado_observado = "starting"
            slot.ultimo_start_em = agora
            slot.atualizado_em = agora
            resultado["acordados"] += 1
            starts += 1
            _registrar_evento_sim(
                db,
                lista[0].simulacao_id,
                "worker_pronto",
                f"Pedido de start aceito para {provedor}.",
                "sucesso",
                provedor=provedor,
            )
        else:
            slot.ultima_falha_em = agora
            slot.atualizado_em = agora
            resultado["falhas"] += 1
            # Volta a recebida para o always-on ou retry posterior
            for t in lista:
                if t.status == "acordando_worker":
                    t.status = "recebida"
                    t.atualizada_em = agora
            _registrar_evento_sim(
                db,
                lista[0].simulacao_id,
                "worker_indisponivel",
                f"Falha ao acordar worker de {provedor}; tarefa permanece recuperável.",
                "aviso",
                provedor=provedor,
            )
        db.commit()

    return resultado


def upsert_slot(
    db: Session,
    *,
    provedor: str,
    fly_machine_id: str,
    tipo_driver: str = "playwright",
    memory_mb: int = 2048,
    regiao: str = "gru",
    slot_id: str | None = None,
) -> WorkerSlotORM:
    """Cria ou atualiza inventário de slot (script de sync / ops)."""
    import uuid

    existente = (
        db.query(WorkerSlotORM)
        .filter(WorkerSlotORM.fly_machine_id == fly_machine_id)
        .one_or_none()
    )
    if existente:
        existente.provedor = provedor
        existente.tipo_driver = tipo_driver
        existente.memory_mb = memory_mb
        existente.regiao = regiao
        existente.habilitado = True
        existente.atualizado_em = _agora()
        db.commit()
        db.refresh(existente)
        return existente
    slot = WorkerSlotORM(
        id=slot_id or str(uuid.uuid4()),
        provedor=provedor,
        tipo_driver=tipo_driver,
        fly_machine_id=fly_machine_id,
        regiao=regiao,
        memory_mb=memory_mb,
        habilitado=True,
        estado_observado="stopped",
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot
