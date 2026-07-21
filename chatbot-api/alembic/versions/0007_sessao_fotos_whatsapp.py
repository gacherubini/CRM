"""Sessão curta de fotos por número autorizado.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.add_column(
            sa.Column("foto_placa_atual", sa.String(length=7), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "foto_sessao_expira_em",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.drop_column("foto_sessao_expira_em")
        batch.drop_column("foto_placa_atual")
