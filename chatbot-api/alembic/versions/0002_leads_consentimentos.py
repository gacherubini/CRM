"""leads e consentimentos

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
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("telefone", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=True),
        sa.Column("interesse", sa.String(), nullable=True),
        sa.Column("etapa", sa.String(), nullable=False, server_default="novo"),
        sa.Column("consentimento_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_leads_loja_id", "leads", ["loja_id"])
    op.create_index("ix_leads_telefone", "leads", ["telefone"])

    op.create_table(
        "consentimentos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("telefone", sa.String(), nullable=False),
        sa.Column("versao_texto", sa.String(), nullable=False),
        sa.Column("finalidade", sa.String(), nullable=False),
        sa.Column("evidencia", sa.String(), nullable=True),
        sa.Column("aceito_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consentimentos_loja_id", "consentimentos", ["loja_id"])
    op.create_index("ix_consentimentos_telefone", "consentimentos", ["telefone"])


def downgrade() -> None:
    op.drop_table("consentimentos")
    op.drop_index("ix_leads_telefone", table_name="leads")
    op.drop_index("ix_leads_loja_id", table_name="leads")
    op.drop_table("leads")
