"""Projeção do estado operacional do Control por cliente_id.

Revision ID: 0014
Revises: 0013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cliente_operacional_projecao",
        sa.Column("cliente_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes_api.id"]),
        sa.PrimaryKeyConstraint("cliente_id", "aggregate"),
    )


def downgrade() -> None:
    op.drop_table("cliente_operacional_projecao")
