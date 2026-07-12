"""Cria vendas, custos diretos e metas."""

from alembic import op
import sqlalchemy as sa

revision = "0002_cria_vendas_metas"
down_revision = "0001_cria_usuarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("lead_ref", sa.String(length=120), nullable=True),
        sa.Column("vendedor_email", sa.String(length=320), nullable=False),
        sa.Column("veiculo_ref", sa.String(length=120), nullable=True),
        sa.Column("descricao", sa.String(length=240), nullable=False),
        sa.Column("preco_venda", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("custo_veiculo", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("motivo_cancelamento", sa.String(length=240), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmada_por", sa.String(length=320), nullable=True),
        sa.Column("confirmada_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vendas_loja_slug"), "vendas", ["loja_slug"], unique=False)
    op.create_index(op.f("ix_vendas_vendedor_email"), "vendas", ["vendedor_email"], unique=False)
    op.create_index(op.f("ix_vendas_status"), "vendas", ["status"], unique=False)

    op.create_table(
        "venda_custos_diretos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("venda_id", sa.String(length=36), nullable=False),
        sa.Column("categoria", sa.String(length=20), nullable=False),
        sa.Column("valor", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venda_id"], ["vendas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venda_custos_diretos_venda_id"), "venda_custos_diretos", ["venda_id"], unique=False)

    op.create_table(
        "metas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("escopo", sa.String(length=20), nullable=False),
        sa.Column("vendedor_email", sa.String(length=320), nullable=True),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("valor_alvo", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metas_loja_slug"), "metas", ["loja_slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_metas_loja_slug"), table_name="metas")
    op.drop_table("metas")
    op.drop_index(op.f("ix_venda_custos_diretos_venda_id"), table_name="venda_custos_diretos")
    op.drop_table("venda_custos_diretos")
    op.drop_index(op.f("ix_vendas_status"), table_name="vendas")
    op.drop_index(op.f("ix_vendas_vendedor_email"), table_name="vendas")
    op.drop_index(op.f("ix_vendas_loja_slug"), table_name="vendas")
    op.drop_table("vendas")
