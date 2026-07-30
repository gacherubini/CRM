"""auditoria de operacao aceita dominio canal

Revision ID: 0015_auditoria_dominio_canal
Revises: 0014_loja_operacao_auditoria
"""

from alembic import op


revision = "0015_auditoria_dominio_canal"
down_revision = "0014_loja_operacao_auditoria"
branch_labels = None
depends_on = None

_NOME = "ck_loja_operacao_auditoria_dominio"
_TABELA = "loja_operacao_auditoria"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira', 'canal')"
        )


def downgrade() -> None:
    # Linhas de canal impediriam a volta da constraint antiga.
    op.execute(f"DELETE FROM {_TABELA} WHERE dominio = 'canal'")
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME, type_="check")
        batch.create_check_constraint(
            _NOME, "dominio IN ('atendimento', 'financeira')"
        )
