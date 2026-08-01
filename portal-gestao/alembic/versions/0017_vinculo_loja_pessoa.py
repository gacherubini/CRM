"""cria vinculo_loja_pessoa e pessoa_revy_projetada

Revision ID: 0017_vinculo_loja_pessoa
Revises: 0016_convites_acesso_loja
"""

import sqlalchemy as sa
from alembic import op


revision = "0017_vinculo_loja_pessoa"
down_revision = "0016_convites_acesso_loja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pessoa_revy_projetada",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("nome", sa.String(length=160), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "vinculo_loja_pessoa",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pessoa_id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("cargo", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["pessoa_id"],
            ["pessoa_revy_projetada.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pessoa_id", "loja_slug", "cargo", name="uq_vinculo_loja_pessoa"
        ),
    )
    op.create_index(
        "ix_vinculo_loja_pessoa_pessoa_id",
        "vinculo_loja_pessoa",
        ["pessoa_id"],
        unique=False,
    )
    op.create_index(
        "ix_vinculo_loja_pessoa_loja_slug",
        "vinculo_loja_pessoa",
        ["loja_slug"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("vinculo_loja_pessoa")
    op.drop_table("pessoa_revy_projetada")