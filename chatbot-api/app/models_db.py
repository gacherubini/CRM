"""Modelos do Chatbot (Plano #2A): lojas, credenciais_servico, conversas, mensagens.

leads e consentimentos entram no próximo incremento.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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


class LojaOperacionalProjecao(Base):
    """Projeção monotônica do estado operacional vindo do Control (Loja / módulos)."""

    __tablename__ = "loja_operacional_projecao"

    loja_id: Mapped[str] = mapped_column(
        ForeignKey("lojas.id"), primary_key=True, nullable=False
    )
    aggregate: Mapped[str] = mapped_column(String(40), primary_key=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class WhatsAppCanal(Base):
    """Canal WhatsApp da loja (Fase 5 multi-WA). loja_id é imutável após criação."""

    __tablename__ = "whatsapp_canais"
    __table_args__ = (
        UniqueConstraint("evolution_instance", name="uq_whatsapp_canais_instance"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    # Número E.164 ou rótulo operacional (ex.: "legado", "linha-2").
    e164_or_label: Mapped[str] = mapped_column(String(80), nullable=False)
    evolution_instance: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # pendente | conectado | desconectado | inativo
    estado: Mapped[str] = mapped_column(String(20), default="pendente", nullable=False)
    # Só este canal responde no grupo de estoque e envia alertas de simulação.
    principal_estoque: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class FilaVendedor(Base):
    """Vendedor na fila de rodízio da loja (Modo 2).

    O telefone mora aqui, não no Portal: o chatbot já é dono de conversa e
    número (``Conversa.telefone``), e é ele que precisa casar o inbound do
    vendedor com o cadastro (spec §5.5). O Portal desenha a tela lendo por
    HTTP, mesmo padrão de ``whatsapp_canais``.

    ``nome`` é obrigatório porque vai no aviso ao cliente ("o João vai te
    chamar", spec §5.1) — sem ele o handoff fica anônimo.
    """

    __tablename__ = "fila_vendedor"
    __table_args__ = (
        Index("ix_fila_vendedor_loja_ordem", "loja_id", "ordem"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # Só dígitos (DDI+DDD+número), normalizado por operacao.normalizar_telefone.
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Pessoa da Loja (``Usuario.id`` do portal-gestao) que este vendedor é.
    # Sem ele o sino não toca: o sinal 1:1 é endereçado por id de usuário do
    # Portal, e ``FilaVendedor.id`` é um UUID daqui que nenhum usuário tem.
    # Nullable porque fila cadastrada por API antes da tela continua válida —
    # o Portal simplesmente não endereça sinal para quem não tem vínculo.
    usuario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class OfertaLead(Base):
    """Uma oferta de lead a um vendedor (spec §5.3).

    ``posicao_inicial`` guarda onde o ponteiro estava quando o lead entrou:
    e assim que se sabe que a volta fechou (voltou em quem comecou) sem
    contar quantas ofertas ja sairam.

    Oferta anterior continua ``aberta`` ate o lead travar — e o que faz
    "primeiro clique vence mesmo atrasado" funcionar.
    """

    __tablename__ = "oferta_lead"
    __table_args__ = (
        Index("ix_oferta_lead_loja_estado", "loja_id", "estado"),
        Index("ix_oferta_lead_prazo", "estado", "prazo_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    telefone_cliente: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    vendedor_id: Mapped[str] = mapped_column(ForeignKey("fila_vendedor.id"), nullable=False)
    # aberta | travada | expirada | esgotada
    estado: Mapped[str] = mapped_column(String(20), default="aberta", nullable=False)
    posicao_inicial: Mapped[int] = mapped_column(Integer, nullable=False)
    prazo_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    travada_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RodizioPonteiro(Base):
    """Onde a proxima oferta da loja comeca (spec §5.3).

    Avanca a cada OFERTA emitida, nao a cada lead: dois leads simultaneos
    caem em vendedores diferentes em vez de empilharem no primeiro da lista.
    """

    __tablename__ = "rodizio_ponteiro"

    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), primary_key=True)
    posicao: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CredencialServico(Base):
    __tablename__ = "credenciais_servico"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), index=True)
    papel: Mapped[str] = mapped_column(String, default="dono")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class Conversa(Base):
    __tablename__ = "conversas"
    # Multi-WA: conversa única por (canal_id, telefone) quando canal_id está setado.
    __table_args__ = (
        UniqueConstraint("canal_id", "telefone", name="uq_conversas_canal_telefone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    # Nullable na expand: legado sem canal; novos fluxos preenchem via instância.
    canal_id: Mapped[str | None] = mapped_column(
        ForeignKey("whatsapp_canais.id"), nullable=True, index=True
    )
    telefone: Mapped[str] = mapped_column(String, index=True)
    bot_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String, default="aberta")  # aberta | handoff | encerrada
    responsavel: Mapped[str | None] = mapped_column(String, nullable=True)
    # Sinais de anúncio ficam pendentes aqui até o cliente qualificar a simulação.
    tracking_pendente_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quantos cutucões de silêncio já saíram nesta rodada (Modo 2, spec §5.9).
    # Zera quando o cliente responde; para em 2 — não existe terceiro toque.
    followup_toques: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class Mensagem(Base):
    __tablename__ = "mensagens"
    # Multi-WA: dedupe por (canal_id, provider_message_id). provider nulo não deduplica.
    # Unique legado (loja_id, provider_message_id) removido na 0017 para permitir
    # o mesmo id de provedor em canais distintos da mesma loja.
    __table_args__ = (
        UniqueConstraint(
            "canal_id", "provider_message_id", name="uq_mensagens_canal_provider"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    canal_id: Mapped[str | None] = mapped_column(
        ForeignKey("whatsapp_canais.id"), nullable=True, index=True
    )
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
    # First / last touch (utm_* legado = last para compat)
    origem_first: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canal_first: Mapped[str | None] = mapped_column(String(40), nullable=True)
    utm_source_first: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium_first: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign_first: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content_first: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term_first: Mapped[str | None] = mapped_column(String(120), nullable=True)
    origem_last: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canal_last: Mapped[str | None] = mapped_column(String(40), nullable=True)
    utm_source_last: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium_last: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign_last: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_content_last: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_term_last: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fbclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gbraid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wbraid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Click-to-WhatsApp (CTWA) — last touch nos campos sem sufixo; first_* separado
    ctwa_clid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ctwa_clid_first: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_ad_id_first: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    meta_campaign_id_first: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_adset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ctwa_source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ctwa_codigo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ctwa_codigo_first: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ctwa_atribuido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    fbclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gclid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gbraid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wbraid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True, index=True)
    atribuida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CtwaAuditoria(Base):
    """Sinais CTWA recebidos no webhook (auditoria sem PII completo)."""

    __tablename__ = "ctwa_auditoria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    telefone_mascarado: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tem_ctwa_clid: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ctwa_clid_sufixo: Mapped[str | None] = mapped_column(String(16), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_adset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ctwa_source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ctwa_codigo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    codigo_extraido_texto: Mapped[bool] = mapped_column(Boolean, default=False)
    atribuido_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    sinais_json: Mapped[str | None] = mapped_column(String(500), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class NumeroAutorizado(Base):
    """Telefones de dono/vendedor autorizados a cadastrar veículo via WhatsApp (E5)."""

    __tablename__ = "numeros_autorizados"
    __table_args__ = (
        UniqueConstraint("loja_id", "telefone", name="uq_numeros_autorizados_loja_telefone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    telefone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(40), default="vendedor")  # dono | vendedor
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    foto_placa_atual: Mapped[str | None] = mapped_column(String(7), nullable=True)
    foto_sessao_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cadastro_expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Menu de operação WA: menu|cadastrar|listar|editar|despublicar|vender
    operacao_modo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # JSON textual: placa, step, campo, valor_pendente, busca…
    operacao_ctx: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class GrupoEstoque(Base):
    """Grupo de WhatsApp autorizado a operar o estoque da loja."""

    __tablename__ = "grupos_estoque"

    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), primary_key=True)
    grupo_jid: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    grupo_nome: Mapped[str | None] = mapped_column(String(160), nullable=True)
    foto_placa_atual: Mapped[str | None] = mapped_column(String(7), nullable=True)
    foto_sessao_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cadastro_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operacao_modo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    operacao_ctx: Mapped[str | None] = mapped_column(Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora, onupdate=_agora)


class NotificacaoOperacional(Base):
    """Outbox de alertas operacionais (ex.: simulação humana → grupo estoque).

    Nunca persiste CPF, nascimento, token ou texto bruto do cliente.
    """

    __tablename__ = "notificacoes_operacionais"
    __table_args__ = (
        UniqueConstraint(
            "loja_id", "idempotency_key", name="uq_notif_op_loja_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    canal_id: Mapped[str | None] = mapped_column(
        ForeignKey("whatsapp_canais.id"), nullable=True, index=True
    )
    tipo: Mapped[str] = mapped_column(String(40), nullable=False, default="simulacao_humana")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    destino_jid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Resumo seguro: interesse truncado, flags, telefone mascarado (JSON textual).
    payload_resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CloudEventoFalho(Base):
    """Evento da Cloud API que estourou no processamento (spec §6.1).

    A §6.1 manda responder ``200`` **imediatamente** para a Meta não reentregar,
    e processar depois. A primeira metade estava feita; a segunda virava
    ``logger.exception`` e o lead sumia em silêncio.

    Guarda o **corpo cru** — não o evento parseado — porque é dele que sai tudo
    de novo no reprocesso, e porque a assinatura da Meta já foi conferida sobre
    esses mesmos bytes. ``wamid`` é único: reentrega da Meta durante uma falha
    não cria duas linhas.
    """

    __tablename__ = "cloud_evento_falho"
    __table_args__ = (
        Index("ix_cloud_evento_falho_estado", "estado", "tentativas"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    wamid: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone_number_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    corpo_cru: Mapped[str] = mapped_column(Text, nullable=False)
    # pendente | processado | desistiu
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )
