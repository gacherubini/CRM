"""cache meta_ad_campanha (ad_id → campaign_id via Graph).

Revision ID: 0015_meta_ad_campanha
Revises: 0014_campanha_anuncios
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_meta_ad_campanha"
down_revision = "0014_campanha_anuncios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_ad_campanha",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("ad_id", sa.String(length=64), nullable=False),
        sa.Column("meta_campaign_id", sa.String(length=64), nullable=True),
        sa.Column("meta_campaign_nome", sa.String(length=200), nullable=True),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.String(length=300), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("loja_slug", "ad_id", name="uq_meta_ad_campanha"),
    )
    op.create_index(
        "ix_meta_ad_campanha_loja_slug",
        "meta_ad_campanha",
        ["loja_slug"],
    )
    op.create_index(
        "ix_meta_ad_campanha_ad_id",
        "meta_ad_campanha",
        ["ad_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meta_ad_campanha_ad_id", table_name="meta_ad_campanha")
    op.drop_index("ix_meta_ad_campanha_loja_slug", table_name="meta_ad_campanha")
    op.drop_table("meta_ad_campanha")
