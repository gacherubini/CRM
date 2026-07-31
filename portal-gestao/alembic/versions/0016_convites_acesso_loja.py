"""cria convites de acesso da loja

Revision ID: 0016_convites_acesso_loja
Revises: 0015_auditoria_dominio_canal
"""

import sqlalchemy as sa
from alembic import op


revision = "0016_convites_acesso_loja"
down_revision = "0015_auditoria_dominio_canal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "convites_acesso_loja",
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
        "ix_convites_acesso_loja_usuario_id",
        "convites_acesso_loja",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_convites_acesso_loja_usuario_id", table_name="convites_acesso_loja"
    )
    op.drop_table("convites_acesso_loja")
