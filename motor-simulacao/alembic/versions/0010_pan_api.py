"""credencial genérica cifrada e campos da simulação PAN

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credenciais_provedor", sa.Column("config_cifrada", sa.Text(), nullable=True)
    )
    op.add_column(
        "simulacoes", sa.Column("codigo_veiculo_provedor", sa.String(100), nullable=True)
    )
    op.add_column("simulacoes", sa.Column("ano_modelo", sa.Integer(), nullable=True))
    op.add_column("simulacoes", sa.Column("zero_km", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("simulacoes", "zero_km")
    op.drop_column("simulacoes", "ano_modelo")
    op.drop_column("simulacoes", "codigo_veiculo_provedor")
    op.drop_column("credenciais_provedor", "config_cifrada")
