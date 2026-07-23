"""Campos CTWA (Click-to-WhatsApp) no lead.

Revision ID: 0010_lead_ctwa
Revises: 0009_operacao_menu_sessao
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_lead_ctwa"
down_revision = "0009_operacao_menu_sessao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("ctwa_clid", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("ctwa_clid_first", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("meta_ad_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("meta_ad_id_first", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("meta_campaign_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("meta_campaign_id_first", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("meta_adset_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("ctwa_source_type", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("ctwa_codigo", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("ctwa_codigo_first", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("ctwa_atribuido_em", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_ctwa_clid", "leads", ["ctwa_clid"])
    op.create_index("ix_leads_meta_campaign_id", "leads", ["meta_campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_meta_campaign_id", table_name="leads")
    op.drop_index("ix_leads_ctwa_clid", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for col in (
            "ctwa_atribuido_em",
            "ctwa_codigo_first",
            "ctwa_codigo",
            "ctwa_source_type",
            "meta_adset_id",
            "meta_campaign_id_first",
            "meta_campaign_id",
            "meta_ad_id_first",
            "meta_ad_id",
            "ctwa_clid_first",
            "ctwa_clid",
        ):
            batch.drop_column(col)
