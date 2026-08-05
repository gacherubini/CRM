"""veiculos.ordem_vitrine — ordem manual na vitrine pública.

Revision ID: 0009_veiculo_ordem_vitrine
Revises: 0008_loja_operacional_projecao
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_veiculo_ordem_vitrine"
down_revision = "0008_loja_operacional_projecao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veiculos",
        sa.Column("ordem_vitrine", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_veiculos_loja_ordem_vitrine",
        "veiculos",
        ["loja_id", "ordem_vitrine"],
    )
    # server_default só na expand; valor efetivo fica na coluna.
    op.alter_column("veiculos", "ordem_vitrine", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_veiculos_loja_ordem_vitrine", table_name="veiculos")
    op.drop_column("veiculos", "ordem_vitrine")
