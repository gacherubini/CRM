"""oferta_lead + rodizio_ponteiro: estado do rodizio do Modo 2

Revision ID: 0021_oferta_lead
Revises: 0020_fila_vendedor

O rodizio precisa de estado durável, nao de memoria de processo: o prazo
de 10 min tem que sobreviver a restart de VM, e o "primeiro clique vence"
tem que valer mesmo depois de o vendedor seguinte ja ter sido chamado.
"""

import sqlalchemy as sa
from alembic import op


revision = "0021_oferta_lead"
down_revision = "0020_fila_vendedor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oferta_lead",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("telefone_cliente", sa.String(length=20), nullable=False),
        sa.Column("vendedor_id", sa.String(length=36), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="aberta"),
        sa.Column("posicao_inicial", sa.Integer(), nullable=False),
        sa.Column("prazo_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("travada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.ForeignKeyConstraint(["vendedor_id"], ["fila_vendedor.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oferta_lead_loja_id", "oferta_lead", ["loja_id"])
    op.create_index("ix_oferta_lead_telefone", "oferta_lead", ["telefone_cliente"])
    op.create_index("ix_oferta_lead_loja_estado", "oferta_lead", ["loja_id", "estado"])
    op.create_index("ix_oferta_lead_prazo", "oferta_lead", ["estado", "prazo_em"])

    op.create_table(
        "rodizio_ponteiro",
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("posicao", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("loja_id"),
    )


def downgrade() -> None:
    op.drop_table("rodizio_ponteiro")
    op.drop_index("ix_oferta_lead_prazo", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_loja_estado", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_telefone", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_loja_id", table_name="oferta_lead")
    op.drop_table("oferta_lead")
