"""Estado de menu de operacao no WhatsApp (modo + contexto JSON).

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.add_column(sa.Column("operacao_modo", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("operacao_ctx", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.drop_column("operacao_ctx")
        batch.drop_column("operacao_modo")
