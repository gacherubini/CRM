"""fila_vendedor: vendedores do rodizio do Modo 2

Revision ID: 0020_fila_vendedor
Revises: 0019_canal_principal_estoque

Modo 2 (spec dos dois modos): a central distribui o lead por rodizio, e
precisa saber quem sao os vendedores, em que ordem, e com que numero. Mora
no chatbot porque e ele que roda o rodizio e que casa o inbound do
vendedor com o cadastro; o Portal so desenha a tela por HTTP.

Sem unique (loja_id, ordem): reordenar a fila trocaria duas linhas e
esbarraria na constraint no meio da transacao. A ordem e resolvida na
leitura, e empate desempata por criado_em.
"""

import sqlalchemy as sa
from alembic import op


revision = "0020_fila_vendedor"
down_revision = "0019_canal_principal_estoque"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fila_vendedor",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fila_vendedor_loja_id", "fila_vendedor", ["loja_id"])
    op.create_index("ix_fila_vendedor_loja_ordem", "fila_vendedor", ["loja_id", "ordem"])


def downgrade() -> None:
    op.drop_index("ix_fila_vendedor_loja_ordem", table_name="fila_vendedor")
    op.drop_index("ix_fila_vendedor_loja_id", table_name="fila_vendedor")
    op.drop_table("fila_vendedor")
