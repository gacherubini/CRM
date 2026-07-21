"""Metadados seguros e capa única para fotos de veículos.

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "veiculo_fotos", sa.Column("content_type", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "veiculo_fotos", sa.Column("tamanho_bytes", sa.Integer(), nullable=True)
    )
    op.add_column(
        "veiculo_fotos",
        sa.Column("capa", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text("UPDATE veiculo_fotos SET capa = TRUE WHERE ordem = 0"))
    op.create_index(
        "uq_veiculo_foto_capa",
        "veiculo_fotos",
        ["veiculo_id"],
        unique=True,
        sqlite_where=sa.text("capa = 1"),
        postgresql_where=sa.text("capa IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_veiculo_foto_capa", table_name="veiculo_fotos")
    op.drop_column("veiculo_fotos", "capa")
    op.drop_column("veiculo_fotos", "tamanho_bytes")
    op.drop_column("veiculo_fotos", "content_type")
