"""Config Marketing API + meta_campaign_id + origem de gastos.

Revision ID: 0009_meta_ads_spend
Revises: 0008_funil_eventos
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_meta_ads_spend"
down_revision = "0008_funil_eventos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_ads_config",
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("ad_account_id", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.String(length=1024), nullable=True),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ultima_sync_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_sync_status", sa.String(length=20), nullable=True),
        sa.Column("ultima_sync_erro", sa.String(length=500), nullable=True),
        sa.Column("ultima_sync_resumo", sa.String(length=240), nullable=True),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("loja_slug"),
    )

    op.add_column(
        "campanhas",
        sa.Column("meta_campaign_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_campanhas_meta_campaign_id", "campanhas", ["meta_campaign_id"]
    )

    op.add_column(
        "campanha_gastos",
        sa.Column("origem", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "campanha_gastos",
        sa.Column("external_key", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "ix_campanha_gastos_origem", "campanha_gastos", ["origem"]
    )
    op.create_unique_constraint(
        "uq_campanha_gasto_external_key", "campanha_gastos", ["external_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_campanha_gasto_external_key", "campanha_gastos", type_="unique")
    op.drop_index("ix_campanha_gastos_origem", table_name="campanha_gastos")
    op.drop_column("campanha_gastos", "external_key")
    op.drop_column("campanha_gastos", "origem")
    op.drop_index("ix_campanhas_meta_campaign_id", table_name="campanhas")
    op.drop_column("campanhas", "meta_campaign_id")
    op.drop_table("meta_ads_config")
