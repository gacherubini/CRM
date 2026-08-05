"""lojas.catalogo_url — link do catálogo enviado pelo bot.

Revision ID: 0010_loja_catalogo_url
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lojas",
        sa.Column("catalogo_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lojas", "catalogo_url")
