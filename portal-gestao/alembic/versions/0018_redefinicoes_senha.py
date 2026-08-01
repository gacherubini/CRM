"""cria redefinicoes de senha

Revision ID: 0018_redefinicoes_senha
Revises: 0017_vinculo_loja_pessoa
"""

import sqlalchemy as sa
from alembic import op


revision = "0018_redefinicoes_senha"
down_revision = "0017_vinculo_loja_pessoa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redefinicoes_senha",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_redefinicoes_senha_usuario_id",
        "redefinicoes_senha",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_redefinicoes_senha_usuario_id", table_name="redefinicoes_senha"
    )
    op.drop_table("redefinicoes_senha")
