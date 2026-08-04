"""campanha_anuncios (ad_id por campanha).

Revision ID: 0014_campanha_anuncios
Revises: 0013_revy_control_readiness_alert_acceptances
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014_campanha_anuncios"
down_revision = "0013_revy_control_readiness_alert_acceptances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campanha_anuncios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("campanha_id", sa.String(length=36), nullable=False),
        sa.Column("ad_id", sa.String(length=64), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["campanha_id"],
            ["campanhas.id"],
            name="fk_campanha_anuncios_campanha_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campanha_id", "ad_id", name="uq_campanha_ad_id"),
    )
    op.create_index(
        "ix_campanha_anuncios_loja_slug",
        "campanha_anuncios",
        ["loja_slug"],
    )
    op.create_index(
        "ix_campanha_anuncios_campanha_id",
        "campanha_anuncios",
        ["campanha_id"],
    )
    op.create_index(
        "ix_campanha_anuncios_ad_id",
        "campanha_anuncios",
        ["ad_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_campanha_anuncios_ad_id",
        table_name="campanha_anuncios",
    )
    op.drop_index(
        "ix_campanha_anuncios_campanha_id",
        table_name="campanha_anuncios",
    )
    op.drop_index(
        "ix_campanha_anuncios_loja_slug",
        table_name="campanha_anuncios",
    )
    op.drop_table("campanha_anuncios")
