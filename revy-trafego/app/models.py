import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return str(uuid.uuid4())


class GestorRevy(Base):
    """Usuário interno da equipe Revy (não é o dono da loja)."""

    __tablename__ = "gestores_revy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(32), default="gestor")  # gestor | admin
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class GestorAuditLog(Base):
    """Auditoria de acesso a PII / diagnóstico."""

    __tablename__ = "gestor_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    gestor_email: Mapped[str] = mapped_column(String(320), index=True)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    acao: Mapped[str] = mapped_column(String(64))
    recurso_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)


# --- Tabelas compartilhadas com portal-gestao (mesmos nomes) ---


class Venda(Base):
    __tablename__ = "vendas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    lead_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    vendedor_email: Mapped[str] = mapped_column(String(320), index=True)
    veiculo_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    descricao: Mapped[str] = mapped_column(String(240))
    preco_venda: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    custo_veiculo: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="registrada", index=True)
    motivo_cancelamento: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    confirmada_por: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    confirmada_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    campanha_id_first: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    campanha_id_last: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    utm_campaign_first: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_campaign_last: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

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


class MetaPixelConfig(Base):
    __tablename__ = "meta_pixel_config"

    loja_slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    pixel_id: Mapped[str] = mapped_column(String(64), default="")
    token_ciphertext: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    test_event_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enviar_page_view: Mapped[bool] = mapped_column(Boolean, default=True)
    enviar_lead: Mapped[bool] = mapped_column(Boolean, default=True)
    enviar_purchase: Mapped[bool] = mapped_column(Boolean, default=True)
    medicao_onboarding_dismiss_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class MetaAdsConfig(Base):
    __tablename__ = "meta_ads_config"

    loja_slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    ad_account_id: Mapped[str] = mapped_column(String(64), default="")
    token_ciphertext: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ultima_sync_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultima_sync_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ultima_sync_erro: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ultima_sync_resumo: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class PixelCapiAuditoria(Base):
    __tablename__ = "pixel_capi_auditoria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    origem: Mapped[str] = mapped_column(String(40), index=True)
    event_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    pixel_id_sufixo: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    modo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tem_ph: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_em: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_fbclid: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_fbc: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_ctwa_clid: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_external_id: Mapped[bool] = mapped_column(Boolean, default=False)
    tem_test_event_code: Mapped[bool] = mapped_column(Boolean, default=False)
    enviar_page_view: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    enviar_lead: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    enviar_purchase: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    venda_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    detalhe: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class MetaCapiOutbox(Base):
    __tablename__ = "meta_capi_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    venda_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    event_name: Mapped[str] = mapped_column(String(40), default="Purchase")
    payload_json: Mapped[str] = mapped_column(String(4000))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Campanha(Base):
    __tablename__ = "campanhas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    nome: Mapped[str] = mapped_column(String(160))
    canal: Mapped[str] = mapped_column(String(32), default="meta")
    status: Mapped[str] = mapped_column(String(20), default="ativa", index=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str] = mapped_column(String(120))
    utm_campaign_norm: Mapped[str] = mapped_column(String(120), index=True)
    utm_content: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_term: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    codigo_ctwa: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    periodo_inicio: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    periodo_fim: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notas: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por_email: Mapped[str] = mapped_column(String(320))

    gastos: Mapped[list["CampanhaGasto"]] = relationship(
        back_populates="campanha", cascade="all, delete-orphan"
    )


class CampanhaGasto(Base):
    __tablename__ = "campanha_gastos"
    __table_args__ = (
        UniqueConstraint("external_key", name="uq_campanha_gasto_external_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    campanha_id: Mapped[str] = mapped_column(ForeignKey("campanhas.id"), index=True)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    referencia: Mapped[date] = mapped_column(Date, index=True)
    nota: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    external_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por: Mapped[str] = mapped_column(String(320))

    campanha: Mapped["Campanha"] = relationship(back_populates="gastos")
