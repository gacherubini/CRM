"""adiciona dismiss do onboarding de medição

Revision ID: 0007_onboarding_medicao
Revises: 0006_campanhas_roi
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_onboarding_medicao"
down_revision = "0006_campanhas_roi"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "meta_pixel_config",
        sa.Column("medicao_onboarding_dismiss_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("meta_pixel_config", "medicao_onboarding_dismiss_em")
