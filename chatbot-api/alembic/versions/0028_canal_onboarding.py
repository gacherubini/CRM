"""whatsapp_canais: campos de retomada e segredos do embedded signup

Revision ID: 0028_canal_onboarding
Revises: 0027_agente_config

Expand-only, todas nullable e sem backfill: canal que nao nasceu pelo embedded
signup (todo Modo 1 e a loja piloto) continua com None e nada muda para ele.

Sem batch_alter_table: o chatbot esta em Postgres desde 23/08 e ele estoura la.

Nao ha coluna de estado nova de proposito — `estado` ja existe e o vocabulario
do Modo 2 mora em whatsapp_provider.ESTADOS_VALIDOS.
"""
import sqlalchemy as sa
from alembic import op


revision = "0028_canal_onboarding"
down_revision = "0027_agente_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_canais",
        sa.Column("business_id", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("onboarding_elo", sa.Integer(), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("onboarding_erro", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("token_cifrado", sa.Text(), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("pin_cifrado", sa.String(length=255), nullable=True),
    )
    # NOT NULL com server_default: canal antigo nasce com 0 sem backfill, e o
    # contador nunca e None no codigo que decide se ainda pode tentar.
    op.add_column(
        "whatsapp_canais",
        sa.Column(
            "registro_tentativas",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_canais", "registro_tentativas")
    op.drop_column("whatsapp_canais", "pin_cifrado")
    op.drop_column("whatsapp_canais", "token_cifrado")
    op.drop_column("whatsapp_canais", "onboarding_erro")
    op.drop_column("whatsapp_canais", "onboarding_elo")
    op.drop_column("whatsapp_canais", "business_id")
