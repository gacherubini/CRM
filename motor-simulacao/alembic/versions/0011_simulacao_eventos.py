"""timeline sanitizada e prints de simulação

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulacao_eventos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "simulacao_id", sa.String(36), sa.ForeignKey("simulacoes.id"), nullable=False
        ),
        sa.Column("etapa", sa.String(80), nullable=False),
        sa.Column("nivel", sa.String(16), nullable=False, server_default="info"),
        sa.Column("mensagem", sa.String(240), nullable=False),
        sa.Column("screenshot_path", sa.Text(), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_simulacao_eventos_simulacao_id", "simulacao_eventos", ["simulacao_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_simulacao_eventos_simulacao_id", table_name="simulacao_eventos")
    op.drop_table("simulacao_eventos")
