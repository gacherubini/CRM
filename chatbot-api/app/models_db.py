"""Modelos do Chatbot (Plano #2A): lojas, credenciais_servico, conversas, mensagens.

leads e consentimentos entram no próximo incremento.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Loja(Base):
    __tablename__ = "lojas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nome: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    # instância da Evolution que identifica esta loja no webhook (nunca vem do body do cliente)
    evolution_instance: Mapped[str] = mapped_column(String, unique=True, index=True)
    whatsapp: Mapped[str | None] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CredencialServico(Base):
    __tablename__ = "credenciais_servico"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), index=True)
    papel: Mapped[str] = mapped_column(String, default="dono")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Conversa(Base):
    __tablename__ = "conversas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    telefone: Mapped[str] = mapped_column(String, index=True)
    bot_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String, default="aberta")  # aberta | handoff | encerrada
    responsavel: Mapped[str | None] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class Mensagem(Base):
    __tablename__ = "mensagens"
    # provider_message_id nulo é permitido em múltiplas linhas; só ids reais deduplicam.
    __table_args__ = (
        UniqueConstraint(
            "loja_id", "provider_message_id", name="uq_mensagens_loja_provider"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    conversa_id: Mapped[str] = mapped_column(ForeignKey("conversas.id"), index=True)
    direcao: Mapped[str] = mapped_column(String)  # entrada | saida
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    texto: Mapped[str | None] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    telefone: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str | None] = mapped_column(String, nullable=True)
    interesse: Mapped[str | None] = mapped_column(String, nullable=True)
    etapa: Mapped[str] = mapped_column(String, default="novo")
    consentimento_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origem: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canal: Mapped[str | None] = mapped_column(String(40), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    veiculo_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    catalog_interest_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    atribuida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class Consentimento(Base):
    __tablename__ = "consentimentos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    telefone: Mapped[str] = mapped_column(String, index=True)
    versao_texto: Mapped[str] = mapped_column(String)
    finalidade: Mapped[str] = mapped_column(String)
    evidencia: Mapped[str | None] = mapped_column(String, nullable=True)
    aceito_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CatalogAttribution(Base):
    """Clique anônimo pendente até uma mensagem inbound apresentar a referência."""

    __tablename__ = "catalog_attributions"
    __table_args__ = (
        UniqueConstraint("loja_id", "event_id", name="uq_catalog_attr_loja_evento"),
        UniqueConstraint("loja_id", "catalog_interest_ref", name="uq_catalog_attr_loja_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    catalog_interest_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    veiculo_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    origem: Mapped[str] = mapped_column(String(80), nullable=False)
    canal: Mapped[str] = mapped_column(String(40), nullable=False)
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    atribuida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
