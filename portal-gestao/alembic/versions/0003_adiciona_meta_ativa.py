"""Adiciona estado ativo às metas."""

from alembic import op
import sqlalchemy as sa


revision = "0003_adiciona_meta_ativa"
down_revision = "0002_cria_vendas_metas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "metas",
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("metas", "ativa")
