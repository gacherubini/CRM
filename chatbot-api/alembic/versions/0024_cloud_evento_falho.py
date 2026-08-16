"""cloud_evento_falho: o "processar depois" da spec §6.1

Revision ID: 0024_cloud_evento_falho
Revises: 0023_fila_vendedor_usuario

A §6.1 manda responder 200 na hora para a Meta nao reentregar, e processar
depois. Responder rapido ja era feito; o "depois" virava logger.exception e o
lead sumia calado. Esta tabela guarda o corpo cru do que falhou para o worker
tentar de novo.

wamid e UNIQUE: reentrega da Meta durante uma falha nao pode criar duas linhas.
"""
import sqlalchemy as sa
from alembic import op


revision = "0024_cloud_evento_falho"
down_revision = "0023_fila_vendedor_usuario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_evento_falho",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("wamid", sa.String(length=255), nullable=False, unique=True),
        sa.Column("phone_number_id", sa.String(length=60), nullable=True),
        sa.Column("corpo_cru", sa.Text(), nullable=False),
        sa.Column(
            "estado", sa.String(length=20), nullable=False, server_default="pendente"
        ),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_cloud_evento_falho_estado",
        "cloud_evento_falho",
        ["estado", "tentativas"],
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_evento_falho_estado", table_name="cloud_evento_falho")
    op.drop_table("cloud_evento_falho")
