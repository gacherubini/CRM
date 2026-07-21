"""Nome e sessão de cadastro por número autorizado.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.add_column(sa.Column("nome", sa.String(length=120), nullable=True))
        batch.add_column(
            sa.Column(
                "cadastro_expira_em",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("numeros_autorizados") as batch:
        batch.drop_column("cadastro_expira_em")
        batch.drop_column("nome")
