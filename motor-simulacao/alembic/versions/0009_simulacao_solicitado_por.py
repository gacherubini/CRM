"""simulacao: solicitado_por (ator do Portal que disparou a sim — histórico Task 16)"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("simulacoes", sa.Column("solicitado_por", sa.String(), nullable=True))
    op.create_index(
        "ix_simulacoes_solicitado_por", "simulacoes", ["solicitado_por"]
    )


def downgrade() -> None:
    op.drop_index("ix_simulacoes_solicitado_por", table_name="simulacoes")
    op.drop_column("simulacoes", "solicitado_por")
