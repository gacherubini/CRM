"""Usuários para administração standalone.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios_estoque",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("papel", sa.String(32), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("loja_id", "email", name="uq_usuario_estoque_loja_email"),
    )
    op.create_index("ix_usuarios_estoque_loja_id", "usuarios_estoque", ["loja_id"])


def downgrade() -> None:
    op.drop_table("usuarios_estoque")
