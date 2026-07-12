"""Entrega da outbox: destinos por loja, registros de entrega e agendamento de retry.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "eventos_saida",
        sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_eventos_saida_proxima_tentativa_em", "eventos_saida", ["proxima_tentativa_em"]
    )

    op.create_table(
        "webhook_destinos",
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("segredo_cifrado", sa.String(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "entregas_evento",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evento_id", sa.String(36), sa.ForeignKey("eventos_saida.id"), nullable=False),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("destino_url", sa.String(), nullable=False),
        sa.Column("tentativa", sa.Integer(), nullable=False),
        sa.Column("status_http", sa.Integer(), nullable=True),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("erro", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entregas_evento_evento_id", "entregas_evento", ["evento_id"])
    op.create_index("ix_entregas_evento_loja_id", "entregas_evento", ["loja_id"])


def downgrade() -> None:
    op.drop_table("entregas_evento")
    op.drop_table("webhook_destinos")
    op.drop_index("ix_eventos_saida_proxima_tentativa_em", table_name="eventos_saida")
    op.drop_column("eventos_saida", "proxima_tentativa_em")
