"""copiloto_acao: estado pendente + estado_anterior de publicacao

Revision ID: 0022_copiloto_acao_pendente_e_estado_anterior
Revises: 0021_copiloto_acoes

Revisão da Task 4 (2026-08-12): duas correções de projeto na mesma migration.

- I-5: sem um estado ``pendente`` gravado ANTES do PATCH, uma queda do
  processo entre a escrita no estoque e o commit final deixava o preço da
  loja alterado sem nenhuma linha em ``copiloto_acao`` — nem sequer
  ``falhou``. ``pendente`` entra no CheckConstraint de estado.
- I-1: o desfazer de publicar/despublicar era decorativo — a linha gravava
  ``desfazer_ate`` mas nada guardava o estado de publicação anterior para
  restaurar. ``estado_anterior`` fecha essa lacuna.
"""

import sqlalchemy as sa
from alembic import op


revision = "0022_copiloto_acao_pendente_e_estado_anterior"
down_revision = "0021_copiloto_acoes"
branch_labels = None
depends_on = None

_TABELA = "copiloto_acao"
_NOME_CONSTRAINT = "ck_copiloto_acao_estado"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.add_column(
            sa.Column("estado_anterior", sa.String(length=40), nullable=True)
        )
        batch.drop_constraint(_NOME_CONSTRAINT, type_="check")
        batch.create_check_constraint(
            _NOME_CONSTRAINT,
            "estado IN ('pendente', 'executada', 'desfeita', 'falhou')",
        )


def downgrade() -> None:
    # Linhas pendentes não existiam antes desta migration — sem trilha
    # confiável para reclassificá-las, tratamos como falha e removemos.
    op.execute(f"DELETE FROM {_TABELA} WHERE estado = 'pendente'")
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_constraint(_NOME_CONSTRAINT, type_="check")
        batch.create_check_constraint(
            _NOME_CONSTRAINT, "estado IN ('executada', 'desfeita', 'falhou')"
        )
        batch.drop_column("estado_anterior")
