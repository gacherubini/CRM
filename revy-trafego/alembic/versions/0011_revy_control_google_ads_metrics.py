"""Métricas Google Ads: contas selecionáveis e campaign daily.

Revision ID: 0011_revy_control_google_ads_metrics
Revises: 0010_revy_control_google_ads_connections
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_revy_control_google_ads_metrics"
down_revision = "0010_revy_control_google_ads_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_ads_accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("login_customer_id", sa.String(20), nullable=True),
        sa.Column("is_manager", sa.Boolean(), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=True),
        sa.Column("time_zone", sa.String(64), nullable=True),
        sa.Column("descriptive_name", sa.String(240), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'ativo', 'inativo', 'erro', 'desconhecido'"
            ")",
            name="ck_google_ads_accounts_status",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_accounts_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            "customer_id",
            name="uq_google_ads_accounts_loja_customer",
        ),
    )
    op.create_index(
        "ix_google_ads_accounts_loja_id",
        "google_ads_accounts",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_accounts_customer_id",
        "google_ads_accounts",
        ["customer_id"],
    )
    op.create_index(
        "ix_google_ads_accounts_selected",
        "google_ads_accounts",
        ["loja_id", "selected"],
    )

    op.create_table(
        "google_ads_campaign_daily",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(40), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False),
        sa.Column(
            "conversions",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "conversions_value",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("currency_code", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "impressions >= 0",
            name="ck_google_ads_campaign_daily_impressions",
        ),
        sa.CheckConstraint(
            "clicks >= 0",
            name="ck_google_ads_campaign_daily_clicks",
        ),
        sa.CheckConstraint(
            "cost_micros >= 0",
            name="ck_google_ads_campaign_daily_cost_micros",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_campaign_daily_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "campaign_id",
            "date",
            name="uq_google_ads_campaign_daily_customer_campaign_date",
        ),
    )
    op.create_index(
        "ix_google_ads_campaign_daily_loja_id",
        "google_ads_campaign_daily",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_campaign_daily_customer_id",
        "google_ads_campaign_daily",
        ["customer_id"],
    )
    op.create_index(
        "ix_google_ads_campaign_daily_date",
        "google_ads_campaign_daily",
        ["date"],
    )
    op.create_index(
        "ix_google_ads_campaign_daily_loja_date",
        "google_ads_campaign_daily",
        ["loja_id", "date"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
