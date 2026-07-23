"""codigo_ctwa na campanha (match CTWA por mensagem).

Revision ID: 0010_campanha_codigo_ctwa
Revises: 0009_meta_ads_spend
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_campanha_codigo_ctwa"
down_revision = "0009_meta_ads_spend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campanhas",
        sa.Column("codigo_ctwa", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_campanhas_codigo_ctwa", "campanhas", ["codigo_ctwa"])


def downgrade() -> None:
    op.drop_index("ix_campanhas_codigo_ctwa", table_name="campanhas")
    op.drop_column("campanhas", "codigo_ctwa")
