"""copiloto_sinal: destinatario opcional (sino 1:1 do Modo 2)

Revision ID: 0024_copiloto_sinal_destinatario
Revises: 0023_copiloto_sinal_visto

O sino sempre foi da loja: quem tem acesso ve o sinal, e "visto" e por
pessoa (0023). A oferta 1:1 do rodizio (spec dos dois modos, §5.7) precisa
do oposto — SO o vendedor da vez pode ver, dono e gerente nao. Coluna
nullable porque NULL tem que continuar significando "da loja inteira":
os 7 sinais do Copiloto nao mudam de comportamento nem precisam backfill.

Guarda id de usuario, nunca telefone — mesma disciplina do model.
"""

import sqlalchemy as sa
from alembic import op


revision = "0024_copiloto_sinal_destinatario"
down_revision = "0023_copiloto_sinal_visto"
branch_labels = None
depends_on = None

_TABELA = "copiloto_sinal"
_INDICE = "ix_copiloto_sinal_destinatario"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.add_column(
            sa.Column("destinatario_usuario_id", sa.String(length=36), nullable=True)
        )
    op.create_index(
        _INDICE,
        _TABELA,
        ["loja_slug", "destinatario_usuario_id", "estado"],
    )


def downgrade() -> None:
    # Sem perda de dado da loja: toda linha legada tem NULL aqui. Só some o
    # endereçamento 1:1 gravado depois do upgrade — e no modelo antigo não
    # existe onde guardá-lo.
    op.drop_index(_INDICE, table_name=_TABELA)
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_column("destinatario_usuario_id")
