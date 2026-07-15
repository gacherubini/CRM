"""Fan-out multi-banco: tarefas por provedor e inventário de slots.

Plano 2026-07-14. Com ``MOTOR_FANOUT_ENABLED=0`` a criação de tarefas é no-op
e o pipeline legado (job único sequential) permanece.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import SimulacaoORM, SimulacaoProvedorORM
from app.motor.providers import normalizar_provedor, obter_provedor

STATUS_TERMINAIS_TAREFA = frozenset(
    {"concluida", "rejeitada", "falhou", "cancelada"}
)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def tipo_driver_provedor(nome: str) -> str:
    """Classifica o conector: mock | api | playwright."""
    canon = normalizar_provedor(nome)
    if canon == "mock" or not canon:
        return "mock"
    meta = obter_provedor(canon)
    if meta is None:
        # Bancos fictícios do mock usam rótulos tipo "Santander" (maiúscula).
        return "mock"
    modo = (meta.get("modo") or "api").lower()
    if modo == "playwright":
        return "playwright"
    return "api"


def criar_tarefas_provedor(
    db: Session, sim: SimulacaoORM, provedores: list[str] | None
) -> list[SimulacaoProvedorORM]:
    """Cria uma linha por banco de forma idempotente (unique sim+provedor).

    Só grava se ``FANOUT_ENABLED``. Retry de POST/idempotência não deve chamar
    isto duas vezes no caminho feliz (sim já existente); mesmo assim, evita
    duplicar se a linha já existir.
    """
    if not config.FANOUT_ENABLED:
        return []
    nomes = [normalizar_provedor(p) for p in (provedores or []) if p]
    # Mantém ordem e remove duplicados
    vistos: set[str] = set()
    ordenados: list[str] = []
    for n in nomes:
        if n and n not in vistos:
            vistos.add(n)
            ordenados.append(n)
    if not ordenados:
        ordenados = ["mock"]

    existentes = {
        t.provedor: t
        for t in db.query(SimulacaoProvedorORM)
        .filter_by(simulacao_id=sim.id)
        .all()
    }
    criadas: list[SimulacaoProvedorORM] = []
    for nome in ordenados:
        if nome in existentes:
            criadas.append(existentes[nome])
            continue
        tarefa = SimulacaoProvedorORM(
            id=str(uuid.uuid4()),
            simulacao_id=sim.id,
            cliente_id=sim.cliente_id,
            provedor=nome,
            tipo_driver=tipo_driver_provedor(nome),
            status="recebida",
            tentativa=0,
        )
        db.add(tarefa)
        criadas.append(tarefa)
        existentes[nome] = tarefa
    return criadas


def obter_tarefa(
    db: Session, simulacao_id: str, provedor: str
) -> SimulacaoProvedorORM | None:
    return (
        db.query(SimulacaoProvedorORM)
        .filter_by(
            simulacao_id=simulacao_id,
            provedor=normalizar_provedor(provedor),
        )
        .one_or_none()
    )


def marcar_tarefa(
    db: Session,
    simulacao_id: str,
    provedor: str,
    status: str,
    *,
    codigo_erro: str | None = None,
    incrementar_tentativa: bool = False,
) -> SimulacaoProvedorORM | None:
    """Atualiza status da tarefa se existir (no-op sem fan-out / sem linha)."""
    tarefa = obter_tarefa(db, simulacao_id, provedor)
    if tarefa is None:
        return None
    agora = _agora()
    tarefa.status = status
    tarefa.atualizada_em = agora
    if incrementar_tentativa:
        tarefa.tentativa = int(tarefa.tentativa or 0) + 1
    if status == "processando" and tarefa.iniciada_em is None:
        tarefa.iniciada_em = agora
    if status in STATUS_TERMINAIS_TAREFA:
        tarefa.finalizada_em = agora
        if codigo_erro:
            tarefa.codigo_erro = codigo_erro[:120]
    return tarefa


def cancelar_tarefas_abertas(db: Session, simulacao_id: str) -> int:
    """Marca tarefas não terminais como canceladas. Retorna quantas mudaram."""
    tarefas = (
        db.query(SimulacaoProvedorORM)
        .filter_by(simulacao_id=simulacao_id)
        .all()
    )
    n = 0
    agora = _agora()
    for t in tarefas:
        if t.status in STATUS_TERMINAIS_TAREFA:
            continue
        t.status = "cancelada"
        t.finalizada_em = agora
        t.atualizada_em = agora
        n += 1
    return n


def tarefas_publicas(sim: SimulacaoORM) -> list[dict]:
    """Projeção segura para API/Portal (sem tokens)."""
    saida = []
    for t in sim.tarefas_provedor or []:
        saida.append(
            {
                "id": t.id,
                "provedor": t.provedor,
                "tipo_driver": t.tipo_driver,
                "status": t.status,
                "tentativa": t.tentativa,
                "codigo_erro": t.codigo_erro,
                "criada_em": t.criada_em.isoformat() if t.criada_em else None,
                "iniciada_em": t.iniciada_em.isoformat() if t.iniciada_em else None,
                "finalizada_em": t.finalizada_em.isoformat() if t.finalizada_em else None,
            }
        )
    return saida
