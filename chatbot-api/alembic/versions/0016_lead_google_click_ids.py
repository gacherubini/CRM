"""Click IDs Google (gbraid/wbraid) em leads e catalog_attributions.

Revision ID: 0016_lead_google_click_ids
Revises: 0015_whatsapp_canais
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_lead_google_click_ids"
down_revision = "0015_whatsapp_canais"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("gbraid", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("wbraid", sa.String(length=255), nullable=True))

    with op.batch_alter_table("catalog_attributions") as batch:
        batch.add_column(sa.Column("gbraid", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("wbraid", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("catalog_attributions") as batch:
        batch.drop_column("wbraid")
        batch.drop_column("gbraid")
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("wbraid")
        batch.drop_column("gbraid")
