"""auditoria aceita dominio copiloto + tabela copiloto_acao

Revision ID: 0021_copiloto_acoes
Revises: 0020_copiloto_conversa_turno
"""

import sqlalchemy as sa
from alembic import op


revision = "0021_copiloto_acoes"
down_revision = "0020_copiloto_conversa_turno"
branch_labels = None
depends_on = None

_NOME = "ck_loja_operacao_auditoria_dominio"
_TABELA = "loja_operacao_auditoria"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira', 'canal', 'copiloto')"
        )

    op.create_table(
        "copiloto_acao",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("turno_id", sa.String(length=36), nullable=True),
        sa.Column("ator_email", sa.String(length=320), nullable=False),
        sa.Column("acao", sa.String(length=40), nullable=False),
        sa.Column("entidade_ref", sa.String(length=120), nullable=False),
        sa.Column("valor_anterior", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("valor_novo", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("erro_code", sa.String(length=40), nullable=True),
        sa.Column("executada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("desfeita_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desfazer_ate", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('executada', 'desfeita', 'falhou')",
            name="ck_copiloto_acao_estado",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copiloto_acao_loja_slug", "copiloto_acao", ["loja_slug"])
    op.create_index(
        "ix_copiloto_acao_loja_criada", "copiloto_acao", ["loja_slug", "executada_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_copiloto_acao_loja_criada", table_name="copiloto_acao")
    op.drop_index("ix_copiloto_acao_loja_slug", table_name="copiloto_acao")
    op.drop_table("copiloto_acao")
    # Linhas de copiloto impediriam a volta da constraint antiga.
    op.execute(f"DELETE FROM {_TABELA} WHERE dominio = 'copiloto'")
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira', 'canal')"
        )
