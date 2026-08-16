"""fila_vendedor.usuario_id: liga o vendedor a pessoa da Loja

Revision ID: 0023_fila_vendedor_usuario
Revises: 0022_conversa_followup_toques

O sino 1:1 do Modo 2 enderec,a o sinal por ``Usuario.id`` do portal-gestao,
e ``fila_vendedor.id`` e um UUID gerado aqui — espacos de identificador
diferentes, que nunca batem. Sem esta coluna o sinal e criado apontando
para um id que nenhum usuario tem, e o sino nao toca para ninguem.

Nullable de proposito: fila cadastrada pela API antes de a tela do Portal
existir continua valida. O Portal nao enderec,a sinal para vendedor sem
vinculo, em vez de enderec,ar errado.
"""

import sqlalchemy as sa
from alembic import op


revision = "0023_fila_vendedor_usuario"
down_revision = "0022_conversa_followup_toques"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fila_vendedor") as batch:
        batch.add_column(sa.Column("usuario_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_fila_vendedor_usuario", "fila_vendedor", ["loja_id", "usuario_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_fila_vendedor_usuario", table_name="fila_vendedor")
    with op.batch_alter_table("fila_vendedor") as batch:
        batch.drop_column("usuario_id")
