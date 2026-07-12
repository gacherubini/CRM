"""Cria histórico local de handoffs atribuídos no Portal."""

from alembic import op
import sqlalchemy as sa


revision = "0004_cria_atendimento_atribuicoes"
down_revision = "0003_adiciona_meta_ativa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "atendimento_atribuicoes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("telefone_hmac", sa.String(length=64), nullable=False),
        sa.Column("vendedor_email", sa.String(length=320), nullable=False),
        sa.Column("origem", sa.String(length=32), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_atendimento_atribuicoes_loja_slug"), "atendimento_atribuicoes", ["loja_slug"])
    op.create_index(op.f("ix_atendimento_atribuicoes_telefone_hmac"), "atendimento_atribuicoes", ["telefone_hmac"])
    op.create_index(op.f("ix_atendimento_atribuicoes_vendedor_email"), "atendimento_atribuicoes", ["vendedor_email"])
    op.create_index(op.f("ix_atendimento_atribuicoes_ativa"), "atendimento_atribuicoes", ["ativa"])


def downgrade() -> None:
    op.drop_index(op.f("ix_atendimento_atribuicoes_ativa"), table_name="atendimento_atribuicoes")
    op.drop_index(op.f("ix_atendimento_atribuicoes_vendedor_email"), table_name="atendimento_atribuicoes")
    op.drop_index(op.f("ix_atendimento_atribuicoes_telefone_hmac"), table_name="atendimento_atribuicoes")
    op.drop_index(op.f("ix_atendimento_atribuicoes_loja_slug"), table_name="atendimento_atribuicoes")
    op.drop_table("atendimento_atribuicoes")
