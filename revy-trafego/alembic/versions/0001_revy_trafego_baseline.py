"""Baseline do banco proprio do Revy Trafego.

Revision ID: 0001_revy_trafego_baseline
Revises: None

A verificacao de existencia permite carimbar o banco compartilhado durante o
strangler sem recriar tabelas que vieram das migrations do Portal.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_revy_trafego_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _existe(nome: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(nome)


def upgrade() -> None:
    if not _existe("gestores_revy"):
        op.create_table(
            "gestores_revy",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("nome", sa.String(160), nullable=False),
            sa.Column("senha_hash", sa.String(255), nullable=False),
            sa.Column("papel", sa.String(32), nullable=False),
            sa.Column("ativo", sa.Boolean(), nullable=False),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_gestores_revy_email", "gestores_revy", ["email"], unique=True)

    if not _existe("gestor_audit_log"):
        op.create_table(
            "gestor_audit_log",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("gestor_email", sa.String(320), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("acao", sa.String(64), nullable=False),
            sa.Column("recurso_id", sa.String(160), nullable=True),
            sa.Column("em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_gestor_audit_log_gestor_email", "gestor_audit_log", ["gestor_email"])
        op.create_index("ix_gestor_audit_log_loja_slug", "gestor_audit_log", ["loja_slug"])
        op.create_index("ix_gestor_audit_log_em", "gestor_audit_log", ["em"])

    if not _existe("vendas_projetadas"):
        op.create_table(
            "vendas_projetadas",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("lead_ref", sa.String(120), nullable=True),
            sa.Column("preco_venda", sa.Numeric(12, 2), nullable=False),
            sa.Column("custo_veiculo", sa.Numeric(12, 2), nullable=True),
            sa.Column("custos_diretos_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("confirmada_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("campanha_id_first", sa.String(36), nullable=True),
            sa.Column("campanha_id_last", sa.String(36), nullable=True),
            sa.Column("utm_campaign_first", sa.String(120), nullable=True),
            sa.Column("utm_campaign_last", sa.String(120), nullable=True),
            sa.PrimaryKeyConstraint("id", "loja_slug"),
        )
        for nome, colunas in (
            ("ix_vendas_projetadas_loja_slug", ["loja_slug"]),
            ("ix_vendas_projetadas_status", ["status"]),
            ("ix_vendas_projetadas_criada_em", ["criada_em"]),
            ("ix_vendas_projetadas_atualizada_em", ["atualizada_em"]),
            ("ix_vendas_projetadas_campanha_id_first", ["campanha_id_first"]),
            ("ix_vendas_projetadas_campanha_id_last", ["campanha_id_last"]),
        ):
            op.create_index(nome, "vendas_projetadas", colunas)

    if not _existe("meta_pixel_config"):
        op.create_table(
            "meta_pixel_config",
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("pixel_id", sa.String(64), nullable=False),
            sa.Column("token_ciphertext", sa.String(1024), nullable=True),
            sa.Column("test_event_code", sa.String(64), nullable=True),
            sa.Column("enviar_page_view", sa.Boolean(), nullable=False),
            sa.Column("enviar_lead", sa.Boolean(), nullable=False),
            sa.Column("enviar_purchase", sa.Boolean(), nullable=False),
            sa.Column("medicao_onboarding_dismiss_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("loja_slug"),
        )

    if not _existe("meta_ads_config"):
        op.create_table(
            "meta_ads_config",
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("ad_account_id", sa.String(64), nullable=False),
            sa.Column("token_ciphertext", sa.String(1024), nullable=True),
            sa.Column("sync_enabled", sa.Boolean(), nullable=False),
            sa.Column("ultima_sync_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ultima_sync_status", sa.String(20), nullable=True),
            sa.Column("ultima_sync_erro", sa.String(500), nullable=True),
            sa.Column("ultima_sync_resumo", sa.String(240), nullable=True),
            sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("loja_slug"),
        )

    if not _existe("pixel_capi_auditoria"):
        op.create_table(
            "pixel_capi_auditoria",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("origem", sa.String(40), nullable=False),
            sa.Column("event_name", sa.String(40), nullable=True),
            sa.Column("event_id", sa.String(120), nullable=True),
            sa.Column("pixel_id_sufixo", sa.String(12), nullable=True),
            sa.Column("modo", sa.String(20), nullable=True),
            sa.Column("tem_ph", sa.Boolean(), nullable=False),
            sa.Column("tem_em", sa.Boolean(), nullable=False),
            sa.Column("tem_fbclid", sa.Boolean(), nullable=False),
            sa.Column("tem_fbc", sa.Boolean(), nullable=False),
            sa.Column("tem_ctwa_clid", sa.Boolean(), nullable=False),
            sa.Column("tem_external_id", sa.Boolean(), nullable=False),
            sa.Column("tem_test_event_code", sa.Boolean(), nullable=False),
            sa.Column("enviar_page_view", sa.Boolean(), nullable=True),
            sa.Column("enviar_lead", sa.Boolean(), nullable=True),
            sa.Column("enviar_purchase", sa.Boolean(), nullable=True),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("venda_id", sa.String(36), nullable=True),
            sa.Column("detalhe", sa.String(240), nullable=True),
            sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        for nome, colunas in (
            ("ix_pixel_capi_auditoria_loja_slug", ["loja_slug"]),
            ("ix_pixel_capi_auditoria_origem", ["origem"]),
            ("ix_pixel_capi_auditoria_criada_em", ["criada_em"]),
        ):
            op.create_index(nome, "pixel_capi_auditoria", colunas)

    if not _existe("meta_capi_outbox"):
        op.create_table(
            "meta_capi_outbox",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("venda_id", sa.String(36), nullable=True),
            sa.Column("event_id", sa.String(120), nullable=False),
            sa.Column("event_name", sa.String(40), nullable=False),
            sa.Column("payload_json", sa.String(4000), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.String(500), nullable=True),
            sa.Column("last_http_status", sa.Integer(), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("loja_slug", "event_id", name="uq_meta_capi_outbox_loja_event_id"),
        )
        for nome, colunas in (
            ("ix_meta_capi_outbox_loja_slug", ["loja_slug"]),
            ("ix_meta_capi_outbox_venda_id", ["venda_id"]),
            ("ix_meta_capi_outbox_event_id", ["event_id"]),
            ("ix_meta_capi_outbox_status", ["status"]),
        ):
            op.create_index(nome, "meta_capi_outbox", colunas)

    if not _existe("campanhas"):
        op.create_table(
            "campanhas",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("nome", sa.String(160), nullable=False),
            sa.Column("canal", sa.String(32), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("utm_source", sa.String(120), nullable=True),
            sa.Column("utm_medium", sa.String(120), nullable=True),
            sa.Column("utm_campaign", sa.String(120), nullable=False),
            sa.Column("utm_campaign_norm", sa.String(120), nullable=False),
            sa.Column("utm_content", sa.String(120), nullable=True),
            sa.Column("utm_term", sa.String(120), nullable=True),
            sa.Column("meta_campaign_id", sa.String(64), nullable=True),
            sa.Column("codigo_ctwa", sa.String(40), nullable=True),
            sa.Column("periodo_inicio", sa.Date(), nullable=True),
            sa.Column("periodo_fim", sa.Date(), nullable=True),
            sa.Column("notas", sa.String(500), nullable=True),
            sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("criada_por_email", sa.String(320), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        for nome, colunas in (
            ("ix_campanhas_loja_slug", ["loja_slug"]),
            ("ix_campanhas_status", ["status"]),
            ("ix_campanhas_utm_campaign_norm", ["utm_campaign_norm"]),
            ("ix_campanhas_meta_campaign_id", ["meta_campaign_id"]),
            ("ix_campanhas_codigo_ctwa", ["codigo_ctwa"]),
        ):
            op.create_index(nome, "campanhas", colunas)

    if not _existe("campanha_gastos"):
        op.create_table(
            "campanha_gastos",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("campanha_id", sa.String(36), nullable=False),
            sa.Column("loja_slug", sa.String(120), nullable=False),
            sa.Column("valor", sa.Numeric(12, 2), nullable=False),
            sa.Column("referencia", sa.Date(), nullable=False),
            sa.Column("nota", sa.String(240), nullable=True),
            sa.Column("origem", sa.String(20), nullable=False),
            sa.Column("external_key", sa.String(120), nullable=True),
            sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("criada_por", sa.String(320), nullable=False),
            sa.ForeignKeyConstraint(["campanha_id"], ["campanhas.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("external_key", name="uq_campanha_gasto_external_key"),
        )
        op.create_index("ix_campanha_gastos_campanha_id", "campanha_gastos", ["campanha_id"])
        op.create_index("ix_campanha_gastos_loja_slug", "campanha_gastos", ["loja_slug"])
        op.create_index("ix_campanha_gastos_referencia", "campanha_gastos", ["referencia"])


def downgrade() -> None:
    raise RuntimeError(
        "Baseline transicional: downgrade destrutivo nao e suportado; restaure backup."
    )
