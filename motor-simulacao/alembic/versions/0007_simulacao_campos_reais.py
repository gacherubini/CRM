"""simulacao: campos do driver real (cnh/placa/uf/finalidade/multi-prazo)"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("simulacoes", sa.Column("cnh", sa.Boolean(), nullable=True))
    op.add_column("simulacoes", sa.Column("placa", sa.String(length=7), nullable=True))
    op.add_column(
        "simulacoes", sa.Column("uf_licenciamento", sa.String(length=2), nullable=True)
    )
    op.add_column("simulacoes", sa.Column("finalidade", sa.String(length=8), nullable=True))
    op.add_column("simulacoes", sa.Column("prazos_meses", sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in ("prazos_meses", "finalidade", "uf_licenciamento", "placa", "cnh"):
        op.drop_column("simulacoes", col)
