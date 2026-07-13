"""numeros autorizados por loja (E5 cadastro WhatsApp)

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
    op.create_table(
        "numeros_autorizados",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("papel", sa.String(length=40), nullable=False, server_default="vendedor"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("loja_id", "telefone", name="uq_numeros_autorizados_loja_telefone"),
    )
    op.create_index("ix_numeros_autorizados_loja_id", "numeros_autorizados", ["loja_id"])
    op.create_index("ix_numeros_autorizados_telefone", "numeros_autorizados", ["telefone"])


def downgrade() -> None:
    op.drop_index("ix_numeros_autorizados_telefone", table_name="numeros_autorizados")
    op.drop_index("ix_numeros_autorizados_loja_id", table_name="numeros_autorizados")
    op.drop_table("numeros_autorizados")
