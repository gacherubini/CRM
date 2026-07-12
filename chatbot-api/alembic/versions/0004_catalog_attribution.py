"""atribuição de interesse do catálogo

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        for name, length in (
            ("origem", 80), ("canal", 40), ("utm_source", 120),
            ("utm_medium", 120), ("utm_campaign", 120), ("utm_content", 120),
            ("utm_term", 120), ("veiculo_ref", 120), ("catalog_interest_ref", 32),
        ):
            batch_op.add_column(sa.Column(name, sa.String(length=length), nullable=True))
        batch_op.add_column(sa.Column("atribuida_em", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "catalog_attributions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("catalog_interest_ref", sa.String(length=32), nullable=False),
        sa.Column("veiculo_ref", sa.String(length=120), nullable=False),
        sa.Column("origem", sa.String(length=80), nullable=False),
        sa.Column("canal", sa.String(length=40), nullable=False),
        sa.Column("utm_source", sa.String(length=120), nullable=True),
        sa.Column("utm_medium", sa.String(length=120), nullable=True),
        sa.Column("utm_campaign", sa.String(length=120), nullable=True),
        sa.Column("utm_content", sa.String(length=120), nullable=True),
        sa.Column("utm_term", sa.String(length=120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("telefone", sa.String(), nullable=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("atribuida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("loja_id", "event_id", name="uq_catalog_attr_loja_evento"),
        sa.UniqueConstraint("loja_id", "catalog_interest_ref", name="uq_catalog_attr_loja_ref"),
    )
    op.create_index("ix_catalog_attr_loja_id", "catalog_attributions", ["loja_id"])
    op.create_index("ix_catalog_attr_event_id", "catalog_attributions", ["event_id"])
    op.create_index("ix_catalog_attr_ref", "catalog_attributions", ["catalog_interest_ref"])
    op.create_index("ix_catalog_attr_telefone", "catalog_attributions", ["telefone"])
    op.create_index("ix_catalog_attr_lead_id", "catalog_attributions", ["lead_id"])


def downgrade() -> None:
    op.drop_table("catalog_attributions")
    with op.batch_alter_table("leads") as batch_op:
        for name in (
            "atribuida_em", "catalog_interest_ref", "veiculo_ref", "utm_term",
            "utm_content", "utm_campaign", "utm_medium", "utm_source", "canal", "origem",
        ):
            batch_op.drop_column(name)
