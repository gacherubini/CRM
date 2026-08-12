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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return str(uuid.uuid4())


FUNIL_EVENTO_TIPOS = (
    "lead_criado",
    "primeira_resposta",
    "simulacao_solicitada",
    "etapa_manual",
    "venda_registrada",
    "venda_confirmada",
    "perda",
)


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


class ConviteAcessoLoja(Base):
    __tablename__ = "convites_acesso_loja"
    __table_args__ = (
        Index("ix_convites_acesso_loja_usuario_id", "usuario_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    usuario_id: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class RedefinicaoSenha(Base):
    __tablename__ = "redefinicoes_senha"
    __table_args__ = (
        Index("ix_redefinicoes_senha_usuario_id", "usuario_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    usuario_id: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class LojaOperacionalProjecao(Base):
    """Projeção monotônica do estado operacional vindo do Control (Loja / módulos).

    Portal multi-tenant por ``loja_slug`` (não há tabela de lojas com UUID local).
    """

    __tablename__ = "loja_operacional_projecao"

    loja_slug: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    aggregate: Mapped[str] = mapped_column(String(40), primary_key=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )


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
    # Snapshot de atribuição no confirmar (estável mesmo se UTM do lead mudar depois).
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


class Meta(Base):
    __tablename__ = "metas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    escopo: Mapped[str] = mapped_column(String(20), default="loja")
    vendedor_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
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
    encerrada_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class LojaOperacaoAuditoria(Base):
    """Trilha append-only de operações da Loja (atendimento + financeiras).

    Nunca grava telefone em claro (só HMAC) nem senha/token de banco.
    """

    __tablename__ = "loja_operacao_auditoria"
    __table_args__ = (
        CheckConstraint(
            "dominio IN ('atendimento', 'financeira', 'canal', 'copiloto')",
            name="ck_loja_operacao_auditoria_dominio",
        ),
        Index(
            "ix_loja_operacao_auditoria_loja_dominio_criado",
            "loja_slug",
            "dominio",
            "criado_em",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dominio: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # atendimento: assumir|devolver|reatribuir
    # financeira: upsert|testar|revogar
    # canal: criar|conectar|desconectar|inativar
    acao: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    ator_email: Mapped[str] = mapped_column(String(320), nullable=False)
    telefone_hmac: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    de_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    para_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    origem: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provedor: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )


ACAO_ESTADOS = ("pendente", "executada", "desfeita", "falhou")


class CopilotoAcao(Base):
    """Ação executada a partir de uma proposta do Copiloto.

    O valor ANTERIOR é capturado aqui pelo Portal antes do PATCH: a
    ``estoque-api`` grava só o valor novo (``servico.py:504``) e o client não
    tem leitura de auditoria. Sem esta linha não existe desfazer.

    ``pendente`` é gravado e COMITADO antes de tocar a rede (§8.2, revisão de
    2026-08-12): se o processo morrer entre o PATCH e a promoção para
    ``executada``, a linha ``pendente`` é o único rastro de que o estoque de
    uma loja real pode ter mudado sem confirmação.

    ``estado_anterior`` guarda o estado de publicação (``"publicar"`` ou
    ``"despublicar"`` — o verbo que RESTAURA aquele estado) antes de
    ``repostar_veiculo``/``publicar_veiculo``/``despublicar_veiculo``. Não usa
    ``valor_anterior`` (é ``Numeric``, feito para preço) nem inventa um
    terceiro vocabulário: reaproveita os mesmos literais de ``VERBO_ESTOQUE``.
    """

    __tablename__ = "copiloto_acao"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendente', 'executada', 'desfeita', 'falhou')",
            name="ck_copiloto_acao_estado",
        ),
        Index("ix_copiloto_acao_loja_criada", "loja_slug", "executada_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    turno_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    ator_email: Mapped[str] = mapped_column(String(320), nullable=False)
    acao: Mapped[str] = mapped_column(String(40), nullable=False)
    entidade_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    valor_anterior: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    valor_novo: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    erro_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    executada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    desfeita_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    desfazer_ate: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FunilEvento(Base):
    """Evento imutável do funil, sempre isolado por loja e lead."""

    __tablename__ = "funil_eventos"
    __table_args__ = (
        UniqueConstraint(
            "loja_slug",
            "idempotency_key",
            name="uq_funil_evento_loja_idempotencia",
        ),
        CheckConstraint(
            "tipo IN ("
            + ", ".join(f"'{tipo}'" for tipo in FUNIL_EVENTO_TIPOS)
            + ")",
            name="ck_funil_evento_tipo",
        ),
        Index(
            "ix_funil_eventos_loja_lead_ocorrido",
            "loja_slug",
            "lead_ref",
            "ocorrido_em",
        ),
        Index(
            "ix_funil_eventos_loja_tipo_ocorrido",
            "loja_slug",
            "tipo",
            "ocorrido_em",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    lead_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ator_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class MetaPixelConfig(Base):
    """Configuração Meta Pixel / CAPI por loja (E10). Token só em ciphertext."""

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
    """Conta de anúncios Meta para importar spend (Marketing API / ads_read)."""

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
    """Auditoria de chaves Pixel/CAPI (flags de match, sem PII)."""

    __tablename__ = "pixel_capi_auditoria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    # config_salva | purchase_web | purchase_messaging | envio_outbox
    origem: Mapped[str] = mapped_column(String(40), index=True)
    event_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    pixel_id_sufixo: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    modo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # web | messaging
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
    """Outbox best-effort para eventos CAPI (Purchase etc.)."""

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


class RevyTrafegoEventOutbox(Base):
    """Entrega duravel de snapshots de venda ao Revy Trafego."""

    __tablename__ = "revy_trafego_event_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), index=True)
    venda_id: Mapped[str] = mapped_column(String(36), index=True)
    event_id: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_ciphertext: Mapped[str] = mapped_column(String(9000))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Campanha(Base):
    """Campanha de marketing/tráfego pago (métrica; não cria anúncio externo)."""

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
    # ID da campanha no Meta Ads (Insights) — vínculo para importar spend e CTWA.
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Código curto na mensagem pré-preenchida do anúncio CTWA (fallback sem ctwa_clid).
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


class PessoaRevyProjetada(Base):
    """Projeção de identidade do Control — pessoas com acesso ao Portal."""

    __tablename__ = "pessoa_revy_projetada"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nome: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)

    vinculos: Mapped[list["VinculoLojaPessoa"]] = relationship(
        back_populates="pessoa", cascade="all, delete-orphan"
    )


class VinculoLojaPessoa(Base):
    """Vínculo de uma pessoa com uma loja e seu cargo nela (multi-loja)."""

    __tablename__ = "vinculo_loja_pessoa"
    __table_args__ = (
        UniqueConstraint(
            "pessoa_id", "loja_slug", "cargo", name="uq_vinculo_loja_pessoa"
        ),
        Index("ix_vinculo_loja_pessoa_pessoa_id", "pessoa_id"),
        Index("ix_vinculo_loja_pessoa_loja_slug", "loja_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    pessoa_id: Mapped[str] = mapped_column(
        ForeignKey("pessoa_revy_projetada.id"), nullable=False
    )
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    cargo: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    atualizado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pessoa: Mapped["PessoaRevyProjetada"] = relationship(back_populates="vinculos")


# --- Copiloto de Vendas -----------------------------------------------------

SINAL_ESTADOS = ("novo", "resolvido", "dispensado")
SINAL_SEVERIDADES = ("info", "atencao", "critico")
SINAL_REGRAS = (
    "estoque_parado",
    "lead_sem_resposta",
    "meta_em_risco",
    "margem_incompleta",
    "cadastro_incompleto",
    "atribuicao_baixa",
    "preco_fora_da_faixa",
)
# Lista escrita à mão de propósito (evita acoplar `models.py`, importado no
# boot da aplicação, a uma leitura de arquivo via AST em outro módulo) — mas
# não é a única fonte: `tests/test_copiloto_sinal_model.py` parseia o AST de
# `app/loja/copiloto/sinais.py` (mesma técnica de
# `tests/test_copiloto_notificacoes_shell.py`, F4/Task 5) e falha se esta
# tupla ficar fora de sincronia com as regras que `sinais.py` de fato emite.


class CopilotoSinal(Base):
    """Alerta proativo do Copiloto.

    Gerado por REGRA DETERMINÍSTICA — o LLM não participa. É o que mantém a
    seção útil quando o provedor de IA está fora do ar.

    Nunca guarda telefone em claro (mesma disciplina de
    ``loja_operacao_auditoria``): sinais de lead são agregados.
    """

    __tablename__ = "copiloto_sinal"
    __table_args__ = (
        CheckConstraint(
            # "visto" foi removido da Fase 4/Task 0 em diante: virou a tabela
            # copiloto_sinal_visto (por pessoa). A migration 0023 faz o
            # backfill de linhas antigas com estado="visto" para "novo" antes
            # de apertar esta constraint — ver o comentário lá.
            "estado IN ('novo', 'resolvido', 'dispensado')",
            name="ck_copiloto_sinal_estado",
        ),
        CheckConstraint(
            "severidade IN ('info', 'atencao', 'critico')",
            name="ck_copiloto_sinal_severidade",
        ),
        Index(
            "ix_copiloto_sinal_loja_regra_entidade",
            "loja_slug",
            "regra",
            "entidade_ref",
        ),
        Index("ix_copiloto_sinal_loja_estado", "loja_slug", "estado", "criado_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    regra: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Id do veículo / meta / o que a regra observa. None = sinal agregado da loja.
    entidade_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    severidade: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(240), nullable=False)
    detalhe: Mapped[str] = mapped_column(String(600), nullable=False)
    dados_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acao_sugerida_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="novo")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora, nullable=False
    )
    resolvido_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispensado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CopilotoSinalVisto(Base):
    """"Visto" por pessoa (Fase 4, Task 0): sino do cabeçalho é individual.

    Relação N-para-N entre sinal e pessoa — por isso é tabela, não coluna em
    ``copiloto_sinal`` (que só guardaria um leitor). Um gestor marcar visto
    NUNCA muda o que os outros veem: ``estado`` do sinal continua o mesmo,
    só esta linha existe a mais. Dispensar é diferente — continua mudando
    ``estado`` em ``copiloto_sinal``, porque dispensar é da loja inteira.
    """

    __tablename__ = "copiloto_sinal_visto"
    __table_args__ = (
        UniqueConstraint(
            "sinal_id", "usuario_id", name="uq_copiloto_sinal_visto_sinal_usuario"
        ),
        Index("ix_copiloto_sinal_visto_usuario", "usuario_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    sinal_id: Mapped[str] = mapped_column(
        ForeignKey("copiloto_sinal.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id: Mapped[str] = mapped_column(String(36), nullable=False)
    visto_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )


TURNO_ESTADOS = ("pendente", "executando", "pronto", "erro", "cancelado")
PERGUNTA_MAX = 4000


class CopilotoConversa(Base):
    """Thread de chat do Copiloto. Uma por assunto, como no Claude."""

    __tablename__ = "copiloto_conversa"
    __table_args__ = (
        Index(
            "ix_copiloto_conversa_loja_usuario",
            "loja_slug",
            "usuario_id",
            "atualizada_em",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    usuario_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora, nullable=False
    )
    arquivada_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CopilotoTurno(Base):
    """Uma pergunta e sua execução.

    ``passos_json`` alimenta a UI de "pensando" e a citação de fonte; os
    contadores de token alimentam o log de perguntas — que é o instrumento de
    roadmap mais barato disponível.

    NUNCA guarda PII de cliente: as ferramentas devolvem agregados.
    """

    __tablename__ = "copiloto_turno"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendente', 'executando', 'pronto', 'erro', 'cancelado')",
            name="ck_copiloto_turno_estado",
        ),
        Index("ix_copiloto_turno_estado_criado", "estado", "criado_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    conversa_id: Mapped[str] = mapped_column(
        ForeignKey("copiloto_conversa.id", ondelete="CASCADE"), index=True
    )
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    usuario_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pergunta: Mapped[str] = mapped_column(String(PERGUNTA_MAX), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    passos_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    texto_parcial: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resposta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    erro_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    custo_estimado: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    iniciado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    concluido_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
