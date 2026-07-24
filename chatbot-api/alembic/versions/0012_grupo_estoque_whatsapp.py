"""Grupo exclusivo para operacao de estoque no WhatsApp.

Revision ID: 0012_grupo_estoque_whatsapp
Revises: 0011_ctwa_auditoria
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_grupo_estoque_whatsapp"
down_revision = "0011_ctwa_auditoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grupos_estoque",
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("grupo_jid", sa.String(length=120), nullable=False),
        sa.Column("grupo_nome", sa.String(length=160), nullable=True),
        sa.Column("foto_placa_atual", sa.String(length=7), nullable=True),
        sa.Column("foto_sessao_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cadastro_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operacao_modo", sa.String(length=40), nullable=True),
        sa.Column("operacao_ctx", sa.Text(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("loja_id"),
    )
    op.create_index(
        "ix_grupos_estoque_grupo_jid",
        "grupos_estoque",
        ["grupo_jid"],
    )


def downgrade() -> None:
    op.drop_index("ix_grupos_estoque_grupo_jid", table_name="grupos_estoque")
    op.drop_table("grupos_estoque")
