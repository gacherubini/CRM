"""Outbox duravel para eventos Portal -> Revy Trafego.

Revision ID: 0012_revy_trafego_event_outbox
Revises: 0011_pixel_capi_auditoria
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_revy_trafego_event_outbox"
down_revision = "0011_pixel_capi_auditoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revy_trafego_event_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("venda_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload_ciphertext", sa.String(length=9000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=240), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_revy_trafego_event_outbox_loja_slug",
        "revy_trafego_event_outbox",
        ["loja_slug"],
    )
    op.create_index(
        "ix_revy_trafego_event_outbox_venda_id",
        "revy_trafego_event_outbox",
        ["venda_id"],
    )
    op.create_index(
        "ix_revy_trafego_event_outbox_event_id",
        "revy_trafego_event_outbox",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_revy_trafego_event_outbox_event_type",
        "revy_trafego_event_outbox",
        ["event_type"],
    )
    op.create_index(
        "ix_revy_trafego_event_outbox_status",
        "revy_trafego_event_outbox",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_revy_trafego_event_outbox_status",
        table_name="revy_trafego_event_outbox",
    )
    op.drop_index(
        "ix_revy_trafego_event_outbox_event_type",
        table_name="revy_trafego_event_outbox",
    )
    op.drop_index(
        "ix_revy_trafego_event_outbox_event_id",
        table_name="revy_trafego_event_outbox",
    )
    op.drop_index(
        "ix_revy_trafego_event_outbox_venda_id",
        table_name="revy_trafego_event_outbox",
    )
    op.drop_index(
        "ix_revy_trafego_event_outbox_loja_slug",
        table_name="revy_trafego_event_outbox",
    )
    op.drop_table("revy_trafego_event_outbox")
