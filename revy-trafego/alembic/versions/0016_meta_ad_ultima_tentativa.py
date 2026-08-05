"""meta_ad_campanha.ultima_tentativa_em (cooldown de falha).

Revision ID: 0016_meta_ad_ultima_tentativa
Revises: 0015_meta_ad_campanha
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_meta_ad_ultima_tentativa"
down_revision = "0015_meta_ad_campanha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meta_ad_campanha",
        sa.Column("ultima_tentativa_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meta_ad_campanha", "ultima_tentativa_em")
