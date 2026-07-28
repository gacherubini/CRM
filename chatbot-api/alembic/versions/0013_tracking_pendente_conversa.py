"""Tracking de anúncio pendente até a qualificação da simulação.

Revision ID: 0013_tracking_pendente_conversa
Revises: 0012_grupo_estoque_whatsapp
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_tracking_pendente_conversa"
down_revision = "0012_grupo_estoque_whatsapp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversas",
        sa.Column("tracking_pendente_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversas", "tracking_pendente_json")
