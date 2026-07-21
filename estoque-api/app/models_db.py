"""Modelos persistentes do Estoque independente (Plano #4A)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class UsuarioEstoque(Base):
    __tablename__ = "usuarios_estoque"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False, default="operador")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    __table_args__ = (
        UniqueConstraint("loja_id", "email", name="uq_usuario_estoque_loja_email"),
    )


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
    placa: Mapped[str | None] = mapped_column(String(7), nullable=True)  # normalizada, sem hífen
    codigo_interno: Mapped[str | None] = mapped_column(String, nullable=True)
    foto_url: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )
    fotos: Mapped[list["VeiculoFoto"]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan", order_by="VeiculoFoto.ordem"
    )

    __table_args__ = (
        UniqueConstraint("loja_id", "codigo_interno", name="uq_veiculos_loja_codigo"),
        # Unicidade parcial: (loja_id, placa) apenas quando placa preenchida.
        Index(
            "uq_veiculos_loja_placa",
            "loja_id",
            "placa",
            unique=True,
            sqlite_where=text("placa IS NOT NULL"),
            postgresql_where=text("placa IS NOT NULL"),
        ),
    )


class VeiculoFoto(Base):
    __tablename__ = "veiculo_fotos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    veiculo_id: Mapped[str] = mapped_column(
        ForeignKey("veiculos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tamanho_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    veiculo: Mapped[Veiculo] = relationship(back_populates="fotos")

    __table_args__ = (
        UniqueConstraint("veiculo_id", "ordem", name="uq_veiculo_foto_ordem"),
        Index(
            "uq_veiculo_foto_capa",
            "veiculo_id",
            unique=True,
            sqlite_where=text("capa = 1"),
            postgresql_where=text("capa IS TRUE"),
        ),
    )


class Importacao(Base):
    __tablename__ = "importacoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    nome_arquivo: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processando")
    total_linhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    atualizadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    erros: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class EventoSaida(Base):
    __tablename__ = "eventos_saida"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agregado_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pendente")
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    processada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class WebhookDestino(Base):
    """Destino de entrega da outbox por loja. O segredo HMAC fica cifrado (nunca em claro)."""

    __tablename__ = "webhook_destinos"

    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), primary_key=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    segredo_cifrado: Mapped[str] = mapped_column(String, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class EntregaEvento(Base):
    """Registro individual de cada tentativa de entrega. O ``id`` é o delivery/idempotency id."""

    __tablename__ = "entregas_evento"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    evento_id: Mapped[str] = mapped_column(
        ForeignKey("eventos_saida.id"), nullable=False, index=True
    )
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    destino_url: Mapped[str] = mapped_column(String, nullable=False)
    tentativa: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status_http: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    recurso: Mapped[str] = mapped_column(String, nullable=False)
    recurso_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    acao: Mapped[str] = mapped_column(String, nullable=False)
    ator_papel: Mapped[str] = mapped_column(String, nullable=False)
    dados: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
