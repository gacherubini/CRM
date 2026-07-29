"""Outbox durável de provisionamento do Revy Control.

Revision ID: 0009_revy_control_provisioning_outbox
Revises: 0008_revy_control_loja_versao
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0009_revy_control_provisioning_outbox"
down_revision = "0008_revy_control_loja_versao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_provisioning_outbox",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("destination", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(240), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'failed')",
            name="ck_control_provisioning_outbox_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_control_provisioning_outbox_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_control_provisioning_outbox_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            name="uq_control_provisioning_outbox_event_id",
        ),
    )
    op.create_index(
        "ix_control_provisioning_outbox_loja_id",
        "control_provisioning_outbox",
        ["loja_id"],
    )
    op.create_index(
        "ix_control_provisioning_outbox_destination",
        "control_provisioning_outbox",
        ["destination"],
    )
    op.create_index(
        "ix_control_provisioning_outbox_event_id",
        "control_provisioning_outbox",
        ["event_id"],
    )
    op.create_index(
        "ix_control_provisioning_outbox_status",
        "control_provisioning_outbox",
        ["status"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
