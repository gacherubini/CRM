import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return str(uuid.uuid4())


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(32), default="vendedor")
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Venda(Base):
    __tablename__ = "vendas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    lead_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vendedor_email: Mapped[str] = mapped_column(String(320), index=True)
    veiculo_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    descricao: Mapped[str] = mapped_column(String(240))
    preco_venda: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    custo_veiculo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="registrada", index=True)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(240), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    confirmada_por: Mapped[str | None] = mapped_column(String(320), nullable=True)
    confirmada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    custos_diretos: Mapped[list["VendaCustoDireto"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan"
    )


class VendaCustoDireto(Base):
    __tablename__ = "venda_custos_diretos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    venda_id: Mapped[str] = mapped_column(ForeignKey("vendas.id"), index=True)
    categoria: Mapped[str] = mapped_column(String(20))
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    venda: Mapped["Venda"] = relationship(back_populates="custos_diretos")


class Meta(Base):
    __tablename__ = "metas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    escopo: Mapped[str] = mapped_column(String(20), default="loja")
    vendedor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20))
    periodo_inicio: Mapped[date] = mapped_column(Date)
    periodo_fim: Mapped[date] = mapped_column(Date)
    valor_alvo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)


class AtendimentoAtribuicao(Base):
    __tablename__ = "atendimento_atribuicoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    telefone_hmac: Mapped[str] = mapped_column(String(64), index=True)
    vendedor_email: Mapped[str] = mapped_column(String(320), index=True)
    origem: Mapped[str] = mapped_column(String(32), default="handoff_portal")
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
