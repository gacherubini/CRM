"""Conversões Google Ads: bindings, outbox e tentativas de upload.

Revision ID: 0012_revy_control_google_ads_conversions
Revises: 0011_revy_control_google_ads_metrics
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012_revy_control_google_ads_conversions"
down_revision = "0011_revy_control_google_ads_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_ads_conversion_bindings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("revy_event_type", sa.String(80), nullable=False),
        sa.Column(
            "conversion_action_resource_name",
            sa.String(240),
            nullable=False,
        ),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_conversion_bindings_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            "revy_event_type",
            name="uq_google_ads_conversion_bindings_loja_event",
        ),
    )
    op.create_index(
        "ix_google_ads_conversion_bindings_loja_id",
        "google_ads_conversion_bindings",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_conversion_bindings_customer_id",
        "google_ads_conversion_bindings",
        ["customer_id"],
    )

    op.create_table(
        "google_ads_conversion_outbox",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("domain_event_id", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("transaction_id", sa.String(240), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'pending', 'sent', 'failed', 'dead'"
            ")",
            name="ck_google_ads_conversion_outbox_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_google_ads_conversion_outbox_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_google_ads_conversion_outbox_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            name="uq_google_ads_conversion_outbox_transaction_id",
        ),
    )
    op.create_index(
        "ix_google_ads_conversion_outbox_loja_id",
        "google_ads_conversion_outbox",
        ["loja_id"],
    )
    op.create_index(
        "ix_google_ads_conversion_outbox_status",
        "google_ads_conversion_outbox",
        ["status"],
    )
    op.create_index(
        "ix_google_ads_conversion_outbox_next_attempt",
        "google_ads_conversion_outbox",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_google_ads_conversion_outbox_domain_event",
        "google_ads_conversion_outbox",
        ["loja_id", "domain_event_id"],
    )

    op.create_table(
        "google_ads_upload_attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("outbox_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt >= 1",
            name="ck_google_ads_upload_attempts_attempt",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'accepted', 'rejected', 'error'"
            ")",
            name="ck_google_ads_upload_attempts_status",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_id"],
            ["google_ads_conversion_outbox.id"],
            name="fk_google_ads_upload_attempts_outbox_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_google_ads_upload_attempts_outbox_id",
        "google_ads_upload_attempts",
        ["outbox_id"],
    )
    op.create_index(
        "ix_google_ads_upload_attempts_request_id",
        "google_ads_upload_attempts",
        ["request_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
