"""mensagens: transcrição sob demanda do áudio de saída

Revision ID: 0030_mensagem_transcricao
Revises: 0029_mensagem_audio

Expand-only e nullable, sem backfill. A transcrição nasce sob demanda, então
mensagem de áudio sem pedido de transcrição continua com None.
"""
import sqlalchemy as sa
from alembic import op


revision = "0030_mensagem_transcricao"
down_revision = "0029_mensagem_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mensagens",
        sa.Column("transcricao", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mensagens", "transcricao")
