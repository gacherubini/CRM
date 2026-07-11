"""Modelos do Estoque (Plano #4A): lojas, credenciais_servico, veiculos.

`usuarios_estoque`, `veiculo_fotos`, `importacoes`, `eventos_saida` e `auditoria`
entram nos incrementos seguintes.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Loja(Base):
    __tablename__ = "lojas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nome: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    whatsapp: Mapped[str | None] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CredencialServico(Base):
    __tablename__ = "credenciais_servico"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), index=True)
    papel: Mapped[str] = mapped_column(String, default="operador")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Veiculo(Base):
    __tablename__ = "veiculos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String)  # moto | carro
    marca: Mapped[str] = mapped_column(String)
    modelo: Mapped[str] = mapped_column(String)
    versao: Mapped[str | None] = mapped_column(String, nullable=True)
    ano_modelo: Mapped[int] = mapped_column(Integer)
    cor: Mapped[str | None] = mapped_column(String, nullable=True)
    km: Mapped[int] = mapped_column(Integer, default=0)
    preco: Mapped[float] = mapped_column(Numeric(12, 2))
    custo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # nunca público
    status: Mapped[str] = mapped_column(String, default="disponivel")
    publicado: Mapped[bool] = mapped_column(Boolean, default=False)
    codigo_interno: Mapped[str | None] = mapped_column(String, nullable=True)
    foto_url: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )
