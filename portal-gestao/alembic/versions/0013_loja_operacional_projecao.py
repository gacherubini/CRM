"""Projeção do estado operacional do Control (por loja_slug).

Revision ID: 0013_loja_operacional_projecao
Revises: 0012_revy_trafego_event_outbox
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_loja_operacional_projecao"
down_revision = "0012_revy_trafego_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loja_operacional_projecao",
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("aggregate", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("loja_slug", "aggregate"),
    )
    op.create_index(
        "ix_loja_operacional_projecao_loja_slug",
        "loja_operacional_projecao",
        ["loja_slug"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_loja_operacional_projecao_loja_slug",
        table_name="loja_operacional_projecao",
    )
    op.drop_table("loja_operacional_projecao")
