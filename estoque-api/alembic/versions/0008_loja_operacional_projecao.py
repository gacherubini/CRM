"""Projeção do estado operacional do Control.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
