"""Fundação Google Ads: conexões OAuth e state store.

Revision ID: 0010_revy_control_google_ads_connections
Revises: 0009_revy_control_provisioning_outbox
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0010_revy_control_google_ads_connections"
down_revision = "0009_revy_control_provisioning_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_ads_connections",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=True),
        sa.Column("login_customer_id", sa.String(20), nullable=True),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'conectado', 'atencao', 'expirado', 'revogado', 'erro'"
            ")",
            name="ck_google_ads_connections_status",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_connections_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            name="uq_google_ads_connections_loja_id",
        ),
    )
    op.create_index(
        "ix_google_ads_connections_loja_id",
        "google_ads_connections",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_connections_status",
        "google_ads_connections",
        ["status"],
    )

    op.create_table(
        "google_ads_oauth_states",
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at >= created_at",
            name="ck_google_ads_oauth_states_expiracao",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_oauth_states_loja_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["gestores_revy.id"],
            name="fk_google_ads_oauth_states_actor_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_google_ads_oauth_states_loja_id",
        "google_ads_oauth_states",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_oauth_states_actor_id",
        "google_ads_oauth_states",
        ["actor_id"],
    )
    op.create_index(
        "ix_google_ads_oauth_states_expires_at",
        "google_ads_oauth_states",
        ["expires_at"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
