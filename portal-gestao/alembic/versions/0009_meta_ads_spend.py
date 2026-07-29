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

    with op.batch_alter_table("campanha_gastos") as batch_op:
        batch_op.add_column(
            sa.Column(
                "origem",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column("external_key", sa.String(length=120), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_campanha_gasto_external_key", ["external_key"]
        )
    op.create_index(
        "ix_campanha_gastos_origem", "campanha_gastos", ["origem"]
    )


def downgrade() -> None:
    op.drop_index("ix_campanha_gastos_origem", table_name="campanha_gastos")
    with op.batch_alter_table("campanha_gastos") as batch_op:
        batch_op.drop_constraint(
            "uq_campanha_gasto_external_key", type_="unique"
        )
        batch_op.drop_column("external_key")
        batch_op.drop_column("origem")
    op.drop_index("ix_campanhas_meta_campaign_id", table_name="campanhas")
    op.drop_column("campanhas", "meta_campaign_id")
    op.drop_table("meta_ads_config")
