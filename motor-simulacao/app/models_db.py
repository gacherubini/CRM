"""Modelos canônicos do Motor (Plano #1A, Task 4).

`simulacoes` (job), `simulacao_resultados` (um por provedor/banco) e `idempotencia`.
Timestamps com timezone; UUID externo em `simulacoes`.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class SimulacaoORM(Base):
    __tablename__ = "simulacoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    referencia_externa: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="recebida")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )
    # Payload pessoal do job (cpf/nascimento/renda) cifrado em repouso; índice cego para dedup.
    payload_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    cpf_indice_cego: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    resultados: Mapped[list["ResultadoORM"]] = relationship(
        back_populates="simulacao", cascade="all, delete-orphan"
    )


class ResultadoORM(Base):
    __tablename__ = "simulacao_resultados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"))
    provedor: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="concluida")
    valor_parcela: Mapped[float] = mapped_column(Numeric(12, 2))
    taxa_am: Mapped[float] = mapped_column(Numeric(6, 4))
    prazo_meses: Mapped[int] = mapped_column(Integer)
    valor_financiado: Mapped[float] = mapped_column(Numeric(12, 2))
    codigo_erro: Mapped[str | None] = mapped_column(String, nullable=True)

    simulacao: Mapped["SimulacaoORM"] = relationship(back_populates="resultados")


class IdempotenciaORM(Base):
    __tablename__ = "idempotencia"

    chave: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
