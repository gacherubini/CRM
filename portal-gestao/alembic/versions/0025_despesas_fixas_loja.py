"""despesa fixa da loja: cadastro recorrente + ajuste por mes

Revision ID: 0025_despesas_fixas_loja
Revises: 0024_venda_excluida

Modulo Financeiro (2026-08-16). A despesa fixa NAO e rateada por venda: ela
entra so no resultado do mes, e o que responde "essa moto pagou a estrutura?"
e o ponto de equilibrio. Por isso estas tabelas nao tem vinculo com `vendas`.

`competencia` e String(7) no formato 'YYYY-MM' — rotulo de mes, sem fuso e sem
ambiguidade de primeiro/ultimo dia. Comparacao lexicografica de 'YYYY-MM'
coincide com a cronologica, entao os filtros de vigencia sao comparacao de
string direta.

Nao existe coluna `ativa` de proposito: um booleano de ativacao e uma
competencia final dizem a mesma coisa e uma hora discordam. Desativar grava
`fim_competencia` = mes corrente, e o mes ja fechado continua correto quando
alguem revisita o passado.
"""

import sqlalchemy as sa
from alembic import op


revision = "0025_despesas_fixas_loja"
down_revision = "0024_venda_excluida"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "despesa_fixa_loja",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("descricao", sa.String(length=240), nullable=False),
        sa.Column("valor_mensal", sa.Numeric(12, 2), nullable=False),
        sa.Column("inicio_competencia", sa.String(length=7), nullable=False),
        sa.Column("fim_competencia", sa.String(length=7), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_despesa_fixa_loja_loja_slug", "despesa_fixa_loja", ["loja_slug"]
    )

    op.create_table(
        "despesa_fixa_ajuste",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("despesa_id", sa.String(length=36), nullable=False),
        sa.Column("competencia", sa.String(length=7), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["despesa_id"], ["despesa_fixa_loja.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Um ajuste por despesa por mes: dois valores para o mesmo mes fariam
        # o total depender da ordem de leitura.
        sa.UniqueConstraint(
            "despesa_id", "competencia", name="uq_despesa_fixa_ajuste_mes"
        ),
    )
    op.create_index(
        "ix_despesa_fixa_ajuste_despesa_id", "despesa_fixa_ajuste", ["despesa_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_despesa_fixa_ajuste_despesa_id", table_name="despesa_fixa_ajuste")
    op.drop_table("despesa_fixa_ajuste")
    op.drop_index("ix_despesa_fixa_loja_loja_slug", table_name="despesa_fixa_loja")
    op.drop_table("despesa_fixa_loja")
