"""Métricas operacionais agregadas e sem dados pessoais."""
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models_db import ResultadoORM, SimulacaoORM, SimulacaoTentativaORM


def _label(valor: str) -> str:
    return str(valor).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _amostra(nome: str, valor: int | float, **labels: str) -> str:
    sufixo = ""
    if labels:
        pares = ",".join(f'{chave}="{_label(valor_label)}"' for chave, valor_label in labels.items())
        sufixo = "{" + pares + "}"
    return f"{nome}{sufixo} {valor}"


def gerar_metricas(db: Session, agora: datetime | None = None) -> str:
    """Gera um snapshot Prometheus a partir do banco, sem estado em memória."""
    linhas = [
        "# HELP motor_simulations Current persisted simulations by status.",
        "# TYPE motor_simulations gauge",
    ]
    simulacoes = db.query(SimulacaoORM.status, func.count()).group_by(SimulacaoORM.status).all()
    for status, quantidade in simulacoes:
        linhas.append(_amostra("motor_simulations", quantidade, status=status))

    linhas.extend([
        "# HELP motor_queue_jobs Jobs currently waiting or being processed.",
        "# TYPE motor_queue_jobs gauge",
    ])
    por_status = dict(simulacoes)
    for status in ("recebida", "processando"):
        linhas.append(_amostra("motor_queue_jobs", por_status.get(status, 0), status=status))

    mais_antiga = (
        db.query(func.min(SimulacaoORM.criada_em))
        .filter(SimulacaoORM.status == "recebida")
        .scalar()
    )
    idade = 0.0
    if mais_antiga is not None:
        if mais_antiga.tzinfo is None:
            mais_antiga = mais_antiga.replace(tzinfo=timezone.utc)
        idade = max(0.0, ((agora or datetime.now(timezone.utc)) - mais_antiga).total_seconds())
    linhas.extend([
        "# HELP motor_queue_oldest_age_seconds Age of the oldest waiting job.",
        "# TYPE motor_queue_oldest_age_seconds gauge",
        _amostra("motor_queue_oldest_age_seconds", idade),
        "# HELP motor_provider_results Persisted final provider results.",
        "# TYPE motor_provider_results gauge",
    ])
    resultados = (
        db.query(ResultadoORM.provedor, ResultadoORM.status, func.count())
        .group_by(ResultadoORM.provedor, ResultadoORM.status)
        .all()
    )
    for provedor, status, quantidade in resultados:
        linhas.append(_amostra("motor_provider_results", quantidade, provider=provedor, status=status))

    linhas.extend([
        "# HELP motor_provider_attempts Persisted provider attempts by outcome.",
        "# TYPE motor_provider_attempts gauge",
        "# HELP motor_provider_retries Attempts after the first one.",
        "# TYPE motor_provider_retries gauge",
        "# HELP motor_provider_attempt_duration_seconds Provider attempt duration.",
        "# TYPE motor_provider_attempt_duration_seconds summary",
    ])
    tentativas = (
        db.query(
            SimulacaoTentativaORM.provedor,
            SimulacaoTentativaORM.status,
            func.count(),
            func.sum(SimulacaoTentativaORM.duracao_ms),
        )
        .group_by(SimulacaoTentativaORM.provedor, SimulacaoTentativaORM.status)
        .all()
    )
    retries: dict[str, int] = defaultdict(int)
    for provedor, status, quantidade, duracao_ms in tentativas:
        labels = {"provider": provedor, "status": status}
        linhas.append(_amostra("motor_provider_attempts", quantidade, **labels))
        linhas.append(_amostra("motor_provider_attempt_duration_seconds_count", quantidade, **labels))
        linhas.append(_amostra(
            "motor_provider_attempt_duration_seconds_sum",
            float(duracao_ms or 0) / 1000,
            **labels,
        ))
    for provedor, quantidade in (
        db.query(SimulacaoTentativaORM.provedor, func.count())
        .filter(SimulacaoTentativaORM.tentativa > 1)
        .group_by(SimulacaoTentativaORM.provedor)
        .all()
    ):
        retries[provedor] = quantidade
    for provedor in sorted({linha[0] for linha in tentativas}):
        linhas.append(_amostra("motor_provider_retries", retries[provedor], provider=provedor))

    return "\n".join(linhas) + "\n"
