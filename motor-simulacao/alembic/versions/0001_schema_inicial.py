"""schema inicial do Motor: simulacoes, simulacao_resultados, idempotencia

Revision ID: 0001
Revises:
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulacoes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("referencia_externa", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="recebida"),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "simulacao_resultados",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "simulacao_id",
            sa.String(length=36),
            sa.ForeignKey("simulacoes.id"),
            nullable=False,
        ),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="concluida"),
        sa.Column("valor_parcela", sa.Numeric(12, 2), nullable=False),
        sa.Column("taxa_am", sa.Numeric(6, 4), nullable=False),
        sa.Column("prazo_meses", sa.Integer(), nullable=False),
        sa.Column("valor_financiado", sa.Numeric(12, 2), nullable=False),
        sa.Column("codigo_erro", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_resultados_simulacao_id", "simulacao_resultados", ["simulacao_id"]
    )
    op.create_table(
        "idempotencia",
        sa.Column("chave", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column(
            "simulacao_id",
            sa.String(length=36),
            sa.ForeignKey("simulacoes.id"),
            nullable=False,
        ),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("idempotencia")
    op.drop_index("ix_resultados_simulacao_id", table_name="simulacao_resultados")
    op.drop_table("simulacao_resultados")
    op.drop_table("simulacoes")
