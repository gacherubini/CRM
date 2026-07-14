"""simulacao_resultados: entrada necessaria devolvida pelo banco"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulacao_resultados", sa.Column("entrada", sa.Numeric(12, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("simulacao_resultados", "entrada")
