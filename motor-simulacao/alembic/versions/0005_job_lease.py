"""lease de processamento e recuperação de jobs abandonados

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("simulacoes", sa.Column("reserva_token", sa.String(36), nullable=True))
    op.add_column(
        "simulacoes", sa.Column("reservada_ate", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_simulacoes_reservada_ate", "simulacoes", ["reservada_ate"])
    # Jobs antigos em processando não tinham lease e seriam irrecuperáveis.
    op.execute(
        "UPDATE simulacoes SET status = 'recebida', atualizada_em = CURRENT_TIMESTAMP "
        "WHERE status = 'processando'"
    )


def downgrade() -> None:
    op.drop_index("ix_simulacoes_reservada_ate", table_name="simulacoes")
    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.drop_column("reservada_ate")
        batch_op.drop_column("reserva_token")
