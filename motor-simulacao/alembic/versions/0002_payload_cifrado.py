"""payload pessoal cifrado + índice cego de CPF em simulacoes

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("simulacoes", sa.Column("payload_cifrado", sa.Text(), nullable=True))
    op.add_column("simulacoes", sa.Column("cpf_indice_cego", sa.String(), nullable=True))
    op.create_index(
        "ix_simulacoes_cpf_indice_cego", "simulacoes", ["cpf_indice_cego"]
    )


def downgrade() -> None:
    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.drop_index("ix_simulacoes_cpf_indice_cego")
        batch_op.drop_column("cpf_indice_cego")
        batch_op.drop_column("payload_cifrado")
