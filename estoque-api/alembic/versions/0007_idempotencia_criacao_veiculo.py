"""Idempotência persistente para cadastro de veículo.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotencias_criacao_veiculo",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("chave_hash", sa.String(length=64), nullable=False),
        sa.Column("requisicao_hash", sa.String(length=64), nullable=False),
        sa.Column("veiculo_id", sa.String(length=36), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.ForeignKeyConstraint(
            ["veiculo_id"], ["veiculos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            "chave_hash",
            name="uq_idempotencia_veiculo_loja_chave",
        ),
    )
    op.create_index(
        "ix_idempotencias_criacao_veiculo_loja_id",
        "idempotencias_criacao_veiculo",
        ["loja_id"],
    )
    op.create_index(
        "ix_idempotencias_criacao_veiculo_veiculo_id",
        "idempotencias_criacao_veiculo",
        ["veiculo_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idempotencias_criacao_veiculo_veiculo_id",
        table_name="idempotencias_criacao_veiculo",
    )
    op.drop_index(
        "ix_idempotencias_criacao_veiculo_loja_id",
        table_name="idempotencias_criacao_veiculo",
    )
    op.drop_table("idempotencias_criacao_veiculo")
