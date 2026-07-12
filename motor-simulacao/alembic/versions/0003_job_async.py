"""job assíncrono: request persistido, tentativas e resultados de provedor nuláveis

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Parte não-pessoal da solicitação, necessária ao worker.
    op.add_column("simulacoes", sa.Column("categoria", sa.String(), nullable=True))
    op.add_column("simulacoes", sa.Column("valor", sa.Numeric(12, 2), nullable=True))
    op.add_column("simulacoes", sa.Column("entrada", sa.Numeric(12, 2), nullable=True))
    op.add_column("simulacoes", sa.Column("prazo_meses", sa.Integer(), nullable=True))
    op.add_column("simulacoes", sa.Column("provedores", sa.JSON(), nullable=True))
    op.create_index("ix_simulacoes_status", "simulacoes", ["status"])

    op.create_table(
        "simulacao_tentativas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("simulacao_id", sa.String(36), sa.ForeignKey("simulacoes.id"), nullable=False),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("tentativa", sa.Integer(), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("codigo_erro", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulacao_tentativas_simulacao_id", "simulacao_tentativas", ["simulacao_id"])

    # Provedor que falha/rejeita não tem parcela: campos monetários passam a nuláveis.
    with op.batch_alter_table("simulacao_resultados", schema=None) as batch_op:
        batch_op.alter_column("valor_parcela", existing_type=sa.Numeric(12, 2), nullable=True)
        batch_op.alter_column("taxa_am", existing_type=sa.Numeric(6, 4), nullable=True)
        batch_op.alter_column("prazo_meses", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("valor_financiado", existing_type=sa.Numeric(12, 2), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("simulacao_resultados", schema=None) as batch_op:
        batch_op.alter_column("valor_financiado", existing_type=sa.Numeric(12, 2), nullable=False)
        batch_op.alter_column("prazo_meses", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("taxa_am", existing_type=sa.Numeric(6, 4), nullable=False)
        batch_op.alter_column("valor_parcela", existing_type=sa.Numeric(12, 2), nullable=False)

    op.drop_index("ix_simulacao_tentativas_simulacao_id", table_name="simulacao_tentativas")
    op.drop_table("simulacao_tentativas")

    op.drop_index("ix_simulacoes_status", table_name="simulacoes")
    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.drop_column("provedores")
        batch_op.drop_column("prazo_meses")
        batch_op.drop_column("entrada")
        batch_op.drop_column("valor")
        batch_op.drop_column("categoria")
