"""First/last touch e click ids nos leads e catalog_attributions."""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.add_column(sa.Column("origem_first", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("canal_first", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("utm_source_first", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_medium_first", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_campaign_first", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_content_first", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_term_first", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("origem_last", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("canal_last", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("utm_source_last", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_medium_last", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_campaign_last", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_content_last", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("utm_term_last", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("fbclid", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("gclid", sa.String(length=255), nullable=True))

    with op.batch_alter_table("catalog_attributions") as batch:
        batch.add_column(sa.Column("fbclid", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("gclid", sa.String(length=255), nullable=True))

    # Backfill: first = last = utm legado
    op.execute(
        """
        UPDATE leads SET
          utm_source_first = utm_source,
          utm_medium_first = utm_medium,
          utm_campaign_first = utm_campaign,
          utm_content_first = utm_content,
          utm_term_first = utm_term,
          origem_first = origem,
          canal_first = canal,
          utm_source_last = utm_source,
          utm_medium_last = utm_medium,
          utm_campaign_last = utm_campaign,
          utm_content_last = utm_content,
          utm_term_last = utm_term,
          origem_last = origem,
          canal_last = canal
        WHERE utm_campaign IS NOT NULL OR origem IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("catalog_attributions") as batch:
        batch.drop_column("gclid")
        batch.drop_column("fbclid")
    with op.batch_alter_table("leads") as batch:
        for col in (
            "gclid",
            "fbclid",
            "utm_term_last",
            "utm_content_last",
            "utm_campaign_last",
            "utm_medium_last",
            "utm_source_last",
            "canal_last",
            "origem_last",
            "utm_term_first",
            "utm_content_first",
            "utm_campaign_first",
            "utm_medium_first",
            "utm_source_first",
            "canal_first",
            "origem_first",
        ):
            batch.drop_column(col)
