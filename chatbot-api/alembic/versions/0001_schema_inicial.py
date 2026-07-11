"""schema inicial do Chatbot: lojas, credenciais_servico, conversas, mensagens

Revision ID: 0001
Revises:
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lojas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("evolution_instance", sa.String(), nullable=False),
        sa.Column("whatsapp", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lojas_slug", "lojas", ["slug"], unique=True)
    op.create_index("ix_lojas_instance", "lojas", ["evolution_instance"], unique=True)

    op.create_table(
        "credenciais_servico",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("papel", sa.String(), nullable=False, server_default="dono"),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credenciais_loja_id", "credenciais_servico", ["loja_id"])

    op.create_table(
        "conversas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("telefone", sa.String(), nullable=False),
        sa.Column("bot_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(), nullable=False, server_default="aberta"),
        sa.Column("responsavel", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conversas_loja_id", "conversas", ["loja_id"])
    op.create_index("ix_conversas_telefone", "conversas", ["telefone"])

    op.create_table(
        "mensagens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("conversa_id", sa.String(length=36), sa.ForeignKey("conversas.id"), nullable=False),
        sa.Column("direcao", sa.String(), nullable=False),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("texto", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mensagens_loja_id", "mensagens", ["loja_id"])
    op.create_index("ix_mensagens_conversa_id", "mensagens", ["conversa_id"])
    op.create_index("ix_mensagens_provider_msg", "mensagens", ["provider_message_id"])


def downgrade() -> None:
    op.drop_table("mensagens")
    op.drop_table("conversas")
    op.drop_index("ix_credenciais_loja_id", table_name="credenciais_servico")
    op.drop_table("credenciais_servico")
    op.drop_index("ix_lojas_instance", table_name="lojas")
    op.drop_index("ix_lojas_slug", table_name="lojas")
    op.drop_table("lojas")
