"""schema inicial do Estoque: lojas, credenciais_servico, veiculos

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
        sa.Column("whatsapp", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lojas_slug", "lojas", ["slug"], unique=True)

    op.create_table(
        "credenciais_servico",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("papel", sa.String(), nullable=False, server_default="operador"),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credenciais_loja_id", "credenciais_servico", ["loja_id"])

    op.create_table(
        "veiculos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("marca", sa.String(), nullable=False),
        sa.Column("modelo", sa.String(), nullable=False),
        sa.Column("versao", sa.String(), nullable=True),
        sa.Column("ano_modelo", sa.Integer(), nullable=False),
        sa.Column("cor", sa.String(), nullable=True),
        sa.Column("km", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preco", sa.Numeric(12, 2), nullable=False),
        sa.Column("custo", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="disponivel"),
        sa.Column("publicado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("codigo_interno", sa.String(), nullable=True),
        sa.Column("foto_url", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_veiculos_loja_id", "veiculos", ["loja_id"])


def downgrade() -> None:
    op.drop_index("ix_veiculos_loja_id", table_name="veiculos")
    op.drop_table("veiculos")
    op.drop_index("ix_credenciais_loja_id", table_name="credenciais_servico")
    op.drop_table("credenciais_servico")
    op.drop_index("ix_lojas_slug", table_name="lojas")
    op.drop_table("lojas")
