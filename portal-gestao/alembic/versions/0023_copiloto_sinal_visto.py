"""copiloto_sinal_visto: "visto" por pessoa, nao por loja

Revision ID: 0023_copiloto_sinal_visto
Revises: 0022_copiloto_acao_pendente_e_estado_anterior

Fase 4, Task 0: "visto" era estado do sinal (compartilhado pela loja
inteira) — um gestor marcava visto e sumia para todo mundo. O dono decidiu
que "visto" e por pessoa: todo gestor/quem tem acesso a Revy Loja precisa
ver a notificacao ate marcar por si. E relacao N-para-N entre sinal e
pessoa, por isso tabela — coluna em copiloto_sinal so guardaria um leitor.
Dispensar continua da loja (nao mexe aqui).
"""

import sqlalchemy as sa
from alembic import op


revision = "0023_copiloto_sinal_visto"
down_revision = "0022_copiloto_acao_pendente_e_estado_anterior"
branch_labels = None
depends_on = None

_TABELA = "copiloto_sinal_visto"


def upgrade() -> None:
    op.create_table(
        _TABELA,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sinal_id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sinal_id"], ["copiloto_sinal.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sinal_id", "usuario_id", name="uq_copiloto_sinal_visto_sinal_usuario"
        ),
    )
    op.create_index(
        "ix_copiloto_sinal_visto_sinal_id", _TABELA, ["sinal_id"]
    )
    op.create_index(
        "ix_copiloto_sinal_visto_usuario", _TABELA, ["usuario_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_copiloto_sinal_visto_usuario", table_name=_TABELA)
    op.drop_index("ix_copiloto_sinal_visto_sinal_id", table_name=_TABELA)
    op.drop_table(_TABELA)
