"""mensagens: tipo, referência de mídia e duração (Áudio do Vendedor)

Revision ID: 0029_mensagem_audio
Revises: 0028_canal_onboarding

Expand-only, nullable exceto `tipo`. Mensagens antigas nascem `texto` por
server_default, sem backfill. `media_ref` é a chave do arquivo no volume; o
banco nunca guarda o binário nem base64.

Sem batch_alter_table: o chatbot está em Postgres desde 23/08 e o batch estoura
lá (mesma razão da 0028).
"""
import sqlalchemy as sa
from alembic import op


revision = "0029_mensagem_audio"
down_revision = "0028_canal_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mensagens",
        sa.Column(
            "tipo",
            sa.String(length=20),
            nullable=False,
            server_default="texto",
        ),
    )
    op.add_column(
        "mensagens",
        sa.Column("media_ref", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "mensagens",
        sa.Column("duracao_segundos", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mensagens", "duracao_segundos")
    op.drop_column("mensagens", "media_ref")
    op.drop_column("mensagens", "tipo")
