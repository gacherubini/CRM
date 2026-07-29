"""Aceites de alerta de prontidão (Fase 3).

Revision ID: 0013_revy_control_readiness_alert_acceptances
Revises: 0010_revy_control_google_ads_connections
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0013_revy_control_readiness_alert_acceptances"
down_revision = "0012_revy_control_google_ads_conversions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "readiness_alert_acceptances",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("check_code", sa.String(64), nullable=False),
        sa.Column("accepted_by", sa.String(36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(check_code)) > 0",
            name="ck_readiness_alert_acceptances_check_code",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_readiness_alert_acceptances_reason",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_readiness_alert_acceptances_loja_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["gestores_revy.id"],
            name="fk_readiness_alert_acceptances_accepted_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            "check_code",
            name="uq_readiness_alert_acceptances_loja_check",
        ),
    )
    op.create_index(
        "ix_readiness_alert_acceptances_loja_id",
        "readiness_alert_acceptances",
        ["loja_id"],
    )
    op.create_index(
        "ix_readiness_alert_acceptances_accepted_by",
        "readiness_alert_acceptances",
        ["accepted_by"],
    )
    op.create_index(
        "ix_readiness_alert_acceptances_accepted_at",
        "readiness_alert_acceptances",
        ["accepted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_readiness_alert_acceptances_accepted_at",
        table_name="readiness_alert_acceptances",
    )
    op.drop_index(
        "ix_readiness_alert_acceptances_accepted_by",
        table_name="readiness_alert_acceptances",
    )
    op.drop_index(
        "ix_readiness_alert_acceptances_loja_id",
        table_name="readiness_alert_acceptances",
    )
    op.drop_table("readiness_alert_acceptances")
