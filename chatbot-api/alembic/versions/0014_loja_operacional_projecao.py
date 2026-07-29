"""Projeção do estado operacional do Control.

Revision ID: 0014_loja_operacional_projecao
Revises: 0013_tracking_pendente_conversa
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_loja_operacional_projecao"
down_revision = "0013_tracking_pendente_conversa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loja_operacional_projecao",
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("loja_id", "aggregate"),
    )


def downgrade() -> None:
    op.drop_table("loja_operacional_projecao")
