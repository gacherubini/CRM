"""placa do veículo + unicidade parcial (loja_id, placa)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("veiculos", sa.Column("placa", sa.String(length=7), nullable=True))
    # Unicidade parcial: (loja_id, placa) somente quando placa preenchida.
    op.create_index(
        "uq_veiculos_loja_placa",
        "veiculos",
        ["loja_id", "placa"],
        unique=True,
        sqlite_where=sa.text("placa IS NOT NULL"),
        postgresql_where=sa.text("placa IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_veiculos_loja_placa", table_name="veiculos")
    op.drop_column("veiculos", "placa")
