"""cria copiloto_sinal (alertas proativos do Copiloto de Vendas)

Revision ID: 0019_copiloto_sinal
Revises: 0018_redefinicoes_senha
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_copiloto_sinal"
down_revision = "0018_redefinicoes_senha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copiloto_sinal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("regra", sa.String(length=40), nullable=False),
        sa.Column("entidade_ref", sa.String(length=120), nullable=True),
        sa.Column("severidade", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.String(length=240), nullable=False),
        sa.Column("detalhe", sa.String(length=600), nullable=False),
        sa.Column("dados_json", sa.Text(), nullable=True),
        sa.Column("acao_sugerida_json", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispensado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('novo', 'visto', 'resolvido', 'dispensado')",
            name="ck_copiloto_sinal_estado",
        ),
        sa.CheckConstraint(
            "severidade IN ('info', 'atencao', 'critico')",
            name="ck_copiloto_sinal_severidade",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copiloto_sinal_loja_slug", "copiloto_sinal", ["loja_slug"], unique=False
    )
    op.create_index(
        "ix_copiloto_sinal_regra", "copiloto_sinal", ["regra"], unique=False
    )
    op.create_index(
        "ix_copiloto_sinal_loja_regra_entidade",
        "copiloto_sinal",
        ["loja_slug", "regra", "entidade_ref"],
        unique=False,
    )
    op.create_index(
        "ix_copiloto_sinal_loja_estado",
        "copiloto_sinal",
        ["loja_slug", "estado", "criado_em"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_copiloto_sinal_loja_estado", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_loja_regra_entidade", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_regra", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_loja_slug", table_name="copiloto_sinal")
    op.drop_table("copiloto_sinal")
