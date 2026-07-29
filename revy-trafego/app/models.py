import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
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
        CheckConstraint(
            "versao >= 1",
            name="ck_lojas_versao",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="rascunho", index=True)
    versao: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ModuloRevy(Base):
    """Módulo comercializável do portfólio Revy."""

    __tablename__ = "modulos_revy"
    __table_args__ = (
        CheckConstraint(
            "codigo IN ('vendas', 'estoque')",
            name="ck_modulos_revy_codigo",
        ),
        UniqueConstraint(
            "codigo",
            name="uq_modulos_revy_codigo",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    codigo: Mapped[str] = mapped_column(String(32))
    nome: Mapped[str] = mapped_column(String(160))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class LojaModulo(Base):
    """Estado contratado de um módulo para uma Loja."""

    __tablename__ = "loja_modulos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('ativo', 'suspenso')",
            name="ck_loja_modulos_estado",
        ),
        CheckConstraint(
            "versao >= 1",
            name="ck_loja_modulos_versao",
        ),
        CheckConstraint(
            "(estado = 'ativo' AND suspenso_em IS NULL) OR "
            "(estado = 'suspenso' AND suspenso_em IS NOT NULL)",
            name="ck_loja_modulos_suspensao",
        ),
        UniqueConstraint(
            "loja_id",
            "modulo_id",
            name="uq_loja_modulos_loja_modulo",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT")
    )
    modulo_id: Mapped[str] = mapped_column(
        ForeignKey("modulos_revy.id", ondelete="RESTRICT")
    )
    estado: Mapped[str] = mapped_column(String(20))
    versao: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
    )
    contratado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora,
    )
    suspenso_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora,
    )


class ContratoLoja(Base):
    """Condição comercial vigente de uma Loja."""

    __tablename__ = "contratos_loja"
    __table_args__ = (
        CheckConstraint(
            "valor_mensal >= 0",
            name="ck_contratos_loja_valor_mensal",
        ),
        CheckConstraint(
            "moeda = 'BRL'",
            name="ck_contratos_loja_moeda",
        ),
        CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_contratos_loja_vigencia",
        ),
        CheckConstraint(
            "vencimento_dia BETWEEN 1 AND 31",
            name="ck_contratos_loja_vencimento_dia",
        ),
        CheckConstraint(
            "situacao_cobranca IN ('em_dia', 'atrasada', 'isenta')",
            name="ck_contratos_loja_situacao_cobranca",
        ),
        CheckConstraint(
            "estado IN ('ativo', 'encerrado')",
            name="ck_contratos_loja_estado",
        ),
        Index(
            "uq_contratos_loja_ativo",
            "loja_id",
            unique=True,
            sqlite_where=text("estado = 'ativo'"),
            postgresql_where=text("estado = 'ativo'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"),
        index=True,
    )
    valor_mensal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moeda: Mapped[str] = mapped_column(
        String(3),
        default="BRL",
        server_default=text("'BRL'"),
    )
    vigencia_inicio: Mapped[date] = mapped_column(Date)
    vigencia_fim: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    vencimento_dia: Mapped[int] = mapped_column(Integer)
    situacao_cobranca: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora,
    )


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


class ControlProvisioningOutbox(Base):
    """Outbox durável de snapshots de provisionamento do Revy Control."""

    __tablename__ = "control_provisioning_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'failed')",
            name="ck_control_provisioning_outbox_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_control_provisioning_outbox_attempts",
        ),
        UniqueConstraint(
            "event_id",
            name="uq_control_provisioning_outbox_event_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    destination: Mapped[str] = mapped_column(String(80), index=True)
    event_id: Mapped[str] = mapped_column(String(240), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsConnection(Base):
    """Conexão OAuth Google Ads de uma Loja (refresh token cifrado)."""

    __tablename__ = "google_ads_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'conectado', 'atencao', 'expirado', 'revogado', 'erro'"
            ")",
            name="ck_google_ads_connections_status",
        ),
        UniqueConstraint(
            "loja_id",
            name="uq_google_ads_connections_loja_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    login_customer_id: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    refresh_token_ciphertext: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsOAuthState(Base):
    """State CSRF de curta duração para o fluxo OAuth multiusuário Google Ads."""

    __tablename__ = "google_ads_oauth_states"
    __table_args__ = (
        CheckConstraint(
            "expires_at >= created_at",
            name="ck_google_ads_oauth_states_expiracao",
        ),
    )

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsAccount(Base):
    """Conta Google Ads descoberta/selecionável por Loja (não manager como anunciante)."""

    __tablename__ = "google_ads_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'ativo', 'inativo', 'erro', 'desconhecido'"
            ")",
            name="ck_google_ads_accounts_status",
        ),
        UniqueConstraint(
            "loja_id",
            "customer_id",
            name="uq_google_ads_accounts_loja_customer",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    login_customer_id: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    is_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    currency_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    time_zone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    descriptive_name: Mapped[Optional[str]] = mapped_column(
        String(240), nullable=True
    )
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="desconhecido")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsCampaignDaily(Base):
    """Métricas diárias por campanha (upsert idempotente por customer/campaign/date)."""

    __tablename__ = "google_ads_campaign_daily"
    __table_args__ = (
        CheckConstraint(
            "impressions >= 0",
            name="ck_google_ads_campaign_daily_impressions",
        ),
        CheckConstraint(
            "clicks >= 0",
            name="ck_google_ads_campaign_daily_clicks",
        ),
        CheckConstraint(
            "cost_micros >= 0",
            name="ck_google_ads_campaign_daily_cost_micros",
        ),
        UniqueConstraint(
            "customer_id",
            "campaign_id",
            "date",
            name="uq_google_ads_campaign_daily_customer_campaign_date",
        ),
        Index(
            "ix_google_ads_campaign_daily_loja_date",
            "loja_id",
            "date",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    campaign_id: Mapped[str] = mapped_column(String(40))
    date: Mapped[date] = mapped_column(Date, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversions: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    conversions_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    currency_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsConversionBinding(Base):
    """Mapeia evento Revy → conversion action existente no Google (nunca cria ação)."""

    __tablename__ = "google_ads_conversion_bindings"
    __table_args__ = (
        UniqueConstraint(
            "loja_id",
            "revy_event_type",
            name="uq_google_ads_conversion_bindings_loja_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    revy_event_type: Mapped[str] = mapped_column(String(80))
    conversion_action_resource_name: Mapped[str] = mapped_column(String(240))
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsConversionOutbox(Base):
    """Outbox de conversões para Data Manager API (transaction_id determinístico)."""

    __tablename__ = "google_ads_conversion_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending', 'sent', 'failed', 'dead'"
            ")",
            name="ck_google_ads_conversion_outbox_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_google_ads_conversion_outbox_attempts",
        ),
        UniqueConstraint(
            "transaction_id",
            name="uq_google_ads_conversion_outbox_transaction_id",
        ),
        Index(
            "ix_google_ads_conversion_outbox_domain_event",
            "loja_id",
            "domain_event_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    domain_event_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(80))
    transaction_id: Mapped[str] = mapped_column(String(240))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    request_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class GoogleAdsUploadAttempt(Base):
    """Diagnóstico lean de cada tentativa de upload (request_id, status, erro)."""

    __tablename__ = "google_ads_upload_attempts"
    __table_args__ = (
        CheckConstraint(
            "attempt >= 1",
            name="ck_google_ads_upload_attempts_attempt",
        ),
        CheckConstraint(
            "status IN ("
            "'accepted', 'rejected', 'error'"
            ")",
            name="ck_google_ads_upload_attempts_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    outbox_id: Mapped[str] = mapped_column(
        ForeignKey("google_ads_conversion_outbox.id", ondelete="RESTRICT"),
        index=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora
    )


class ReadinessAlertAcceptance(Base):
    """Aceite auditavel de alerta de prontidao (nao contorna checks required)."""

    __tablename__ = "readiness_alert_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "loja_id",
            "check_code",
            name="uq_readiness_alert_acceptances_loja_check",
        ),
        CheckConstraint(
            "length(trim(check_code)) > 0",
            name="ck_readiness_alert_acceptances_check_code",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_readiness_alert_acceptances_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id", ondelete="RESTRICT"), index=True
    )
    check_code: Mapped[str] = mapped_column(String(64))
    accepted_by: Mapped[str] = mapped_column(
        ForeignKey("gestores_revy.id", ondelete="RESTRICT"), index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, index=True
    )
