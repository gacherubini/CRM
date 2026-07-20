"""Campanhas, gastos e snapshot de atribuição na venda."""

from alembic import op
import sqlalchemy as sa


revision = "0006_campanhas_roi"
down_revision = "0005_meta_pixel_capi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campanhas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("nome", sa.String(length=160), nullable=False),
        sa.Column("canal", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("utm_source", sa.String(length=120), nullable=True),
        sa.Column("utm_medium", sa.String(length=120), nullable=True),
        sa.Column("utm_campaign", sa.String(length=120), nullable=False),
        sa.Column("utm_campaign_norm", sa.String(length=120), nullable=False),
        sa.Column("utm_content", sa.String(length=120), nullable=True),
        sa.Column("utm_term", sa.String(length=120), nullable=True),
        sa.Column("periodo_inicio", sa.Date(), nullable=True),
        sa.Column("periodo_fim", sa.Date(), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_por_email", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loja_slug", "utm_campaign_norm", name="uq_campanha_loja_utm_norm"),
    )
    op.create_index("ix_campanhas_loja_slug", "campanhas", ["loja_slug"])
    op.create_index("ix_campanhas_status", "campanhas", ["status"])
    op.create_index("ix_campanhas_utm_campaign_norm", "campanhas", ["utm_campaign_norm"])

    op.create_table(
        "campanha_gastos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campanha_id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("referencia", sa.Date(), nullable=False),
        sa.Column("nota", sa.String(length=240), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_por", sa.String(length=320), nullable=False),
        sa.ForeignKeyConstraint(["campanha_id"], ["campanhas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campanha_gastos_campanha_id", "campanha_gastos", ["campanha_id"])
    op.create_index("ix_campanha_gastos_loja_slug", "campanha_gastos", ["loja_slug"])
    op.create_index("ix_campanha_gastos_referencia", "campanha_gastos", ["referencia"])

    op.add_column("vendas", sa.Column("campanha_id_first", sa.String(length=36), nullable=True))
    op.add_column("vendas", sa.Column("campanha_id_last", sa.String(length=36), nullable=True))
    op.add_column("vendas", sa.Column("utm_campaign_first", sa.String(length=120), nullable=True))
    op.add_column("vendas", sa.Column("utm_campaign_last", sa.String(length=120), nullable=True))
    op.create_index("ix_vendas_campanha_id_first", "vendas", ["campanha_id_first"])
    op.create_index("ix_vendas_campanha_id_last", "vendas", ["campanha_id_last"])


def downgrade() -> None:
    op.drop_index("ix_vendas_campanha_id_last", table_name="vendas")
    op.drop_index("ix_vendas_campanha_id_first", table_name="vendas")
    op.drop_column("vendas", "utm_campaign_last")
    op.drop_column("vendas", "utm_campaign_first")
    op.drop_column("vendas", "campanha_id_last")
    op.drop_column("vendas", "campanha_id_first")
    op.drop_table("campanha_gastos")
    op.drop_table("campanhas")
