import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return str(uuid.uuid4())


class Loja(Base):
    __tablename__ = "lojas"
    __table_args__ = (
        CheckConstraint(
            "slug = lower(trim(slug)) AND length(slug) BETWEEN 1 AND 120",
            name="ck_lojas_slug_canonico",
        ),
        CheckConstraint(
            "status IN ('rascunho', 'em_configuracao', 'pronta', 'ativa', "
            "'suspensa', 'encerrada')",
            name="ck_lojas_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="rascunho", index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Pessoa(Base):
    __tablename__ = "pessoas"
    __table_args__ = (
        CheckConstraint(
            "email = lower(trim(email)) AND length(email) BETWEEN 3 AND 320",
            name="ck_pessoas_email_normalizado",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class CargoLoja(Base):
    __tablename__ = "cargos_loja"
    __table_args__ = (
        CheckConstraint(
            "cargo IN ('dono', 'gerente', 'vendedor')",
            name="ck_cargos_loja_cargo",
        ),
        CheckConstraint(
            "origem IN ('control', 'portal')",
            name="ck_cargos_loja_origem",
        ),
        CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= iniciado_em",
            name="ck_cargos_loja_periodo",
        ),
        Index(
            "uq_cargos_loja_cargo_ativo",
            "loja_id",
            "pessoa_id",
            "cargo",
            unique=True,
            sqlite_where=text("encerrado_em IS NULL"),
            postgresql_where=text("encerrado_em IS NULL"),
        ),
        Index(
            "uq_cargos_loja_origem_ativa",
            "origem",
            "origem_id",
            unique=True,
            sqlite_where=text(
                "origem_id IS NOT NULL AND encerrado_em IS NULL"
            ),
            postgresql_where=text(
                "origem_id IS NOT NULL AND encerrado_em IS NULL"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    pessoa_id: Mapped[str] = mapped_column(
        ForeignKey("pessoas.id", ondelete="RESTRICT"), index=True
    )
    cargo: Mapped[str] = mapped_column(String(20))
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    encerrado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    origem: Mapped[str] = mapped_column(String(20), default="control")
    origem_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)


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


class AcessoControl(Base):
    """Autenticação e papel global de uma Pessoa Revy no Revy Control."""

    __tablename__ = "acessos_control"
    __table_args__ = (
        CheckConstraint(
            "papel IN ('admin', 'gestor')",
            name="ck_acessos_control_papel",
        ),
        CheckConstraint(
            "estado IN ('pendente', 'ativo', 'desativado')",
            name="ck_acessos_control_estado",
        ),
        CheckConstraint(
            "sessao_versao >= 1",
            name="ck_acessos_control_sessao_versao",
        ),
        UniqueConstraint(
            "pessoa_id",
            name="uq_acessos_control_pessoa_id",
        ),
        UniqueConstraint(
            "gestor_legado_id",
            name="uq_acessos_control_gestor_legado_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    pessoa_id: Mapped[str] = mapped_column(
        ForeignKey("pessoas.id", ondelete="RESTRICT")
    )
    papel: Mapped[str] = mapped_column(String(32))
    estado: Mapped[str] = mapped_column(String(20))
    senha_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sessao_versao: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
    )
    gestor_legado_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"),
        nullable=True,
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ConviteAcessoControl(Base):
    """Convite de uso único para ativar um acesso ao Revy Control."""

    __tablename__ = "convites_acesso_control"
    __table_args__ = (
        CheckConstraint(
            "expira_em >= criado_em",
            name="ck_convites_acesso_control_expiracao",
        ),
        CheckConstraint(
            "usado_em IS NULL OR usado_em >= criado_em",
            name="ck_convites_acesso_control_uso",
        ),
        CheckConstraint(
            "revogado_em IS NULL OR revogado_em >= criado_em",
            name="ck_convites_acesso_control_revogacao",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_convites_acesso_control_token_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    acesso_id: Mapped[str] = mapped_column(
        ForeignKey("acessos_control.id", ondelete="RESTRICT"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revogado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    criado_por_gestor_id: Mapped[str] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"),
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class RecuperacaoSenhaControl(Base):
    """Token de uso único para recuperar a senha de um acesso ao Revy Control."""

    __tablename__ = "recuperacoes_senha_control"
    __table_args__ = (
        CheckConstraint(
            "expira_em >= criado_em",
            name="ck_recuperacoes_senha_control_expiracao",
        ),
        CheckConstraint(
            "usado_em IS NULL OR usado_em >= criado_em",
            name="ck_recuperacoes_senha_control_uso",
        ),
        CheckConstraint(
            "revogado_em IS NULL OR revogado_em >= criado_em",
            name="ck_recuperacoes_senha_control_revogacao",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_recuperacoes_senha_control_token_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    acesso_id: Mapped[str] = mapped_column(
        ForeignKey("acessos_control.id", ondelete="RESTRICT"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revogado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    criado_por_gestor_id: Mapped[str] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"),
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class VinculoTrafego(Base):
    __tablename__ = "vinculos_trafego"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('responsavel', 'colaborador')",
            name="ck_vinculos_trafego_tipo",
        ),
        CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= iniciado_em",
            name="ck_vinculos_trafego_periodo",
        ),
        Index(
            "uq_vinculos_trafego_gestor_ativo",
            "loja_id",
            "gestor_id",
            unique=True,
            sqlite_where=text("encerrado_em IS NULL"),
            postgresql_where=text("encerrado_em IS NULL"),
        ),
        Index(
            "uq_vinculos_trafego_responsavel_ativo",
            "loja_id",
            unique=True,
            sqlite_where=text(
                "encerrado_em IS NULL AND tipo = 'responsavel'"
            ),
            postgresql_where=text(
                "encerrado_em IS NULL AND tipo = 'responsavel'"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    gestor_id: Mapped[str] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"), index=True
    )
    tipo: Mapped[str] = mapped_column(String(20))
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    encerrado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditoriaEvento(Base):
    __tablename__ = "auditoria_eventos"
    __table_args__ = (
        CheckConstraint(
            "resultado IN ('sucesso', 'negado', 'erro')",
            name="ck_auditoria_eventos_resultado",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    ator_gestor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    ator_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    acao: Mapped[str] = mapped_column(String(100), index=True)
    recurso_tipo: Mapped[str] = mapped_column(String(80))
    recurso_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), default="sucesso")
    antes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    depois_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, index=True
    )


class GestorAuditLog(Base):
    """Auditoria de acesso a PII / diagnóstico."""

    __tablename__ = "gestor_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    gestor_email: Mapped[str] = mapped_column(String(320), index=True)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    acao: Mapped[str] = mapped_column(String(64))
    recurso_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)


class VendaProjetada(Base):
    """Snapshot de venda recebido do Portal; fonte local para ROI no Revy."""

    __tablename__ = "vendas_projetadas"

    # O id do Portal e estavel e torna a projecao naturalmente idempotente.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_slug: Mapped[str] = mapped_column(
        String(120), primary_key=True, index=True
    )
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    lead_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    preco_venda: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    custo_veiculo: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    custos_diretos_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmada_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    campanha_id_first: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    campanha_id_last: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    utm_campaign_first: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    utm_campaign_last: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )


class MetaPixelConfig(Base):
    __tablename__ = "meta_pixel_config"

    loja_slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
    __table_args__ = (
        UniqueConstraint(
            "loja_slug",
            "event_id",
            name="uq_meta_capi_outbox_loja_event_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    venda_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    event_id: Mapped[str] = mapped_column(String(120), index=True)
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
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
    loja_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    referencia: Mapped[date] = mapped_column(Date, index=True)
    nota: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")
    external_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por: Mapped[str] = mapped_column(String(320))

    campanha: Mapped["Campanha"] = relationship(back_populates="gastos")
