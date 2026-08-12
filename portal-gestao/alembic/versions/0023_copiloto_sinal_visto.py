"""copiloto_sinal_visto: "visto" por pessoa, nao por loja

Revision ID: 0023_copiloto_sinal_visto
Revises: 0022_copiloto_acao_pendente_e_estado_anterior

Fase 4, Task 0: "visto" era estado do sinal (compartilhado pela loja
inteira) — um gestor marcava visto e sumia para todo mundo. O dono decidiu
que "visto" e por pessoa: todo gestor/quem tem acesso a Revy Loja precisa
ver a notificacao ate marcar por si. E relacao N-para-N entre sinal e
pessoa, por isso tabela — coluna em copiloto_sinal so guardaria um leitor.
Dispensar continua da loja (nao mexe aqui).

Backfill + aperto de constraint (revisao de 2026-08-12): o codigo anterior
a esta task ja gravava estado="visto" em copiloto_sinal (existe desde o
commit 641b1ae, mergeado bem antes desta task) — essa semantica era da
loja e NUNCA registrou quem viu. Sem o backfill abaixo, uma linha legada
com estado="visto" nunca mais bate o filtro `estado == 'novo'` que
`contar_sinais_novos` passou a usar: ela some do contador de "novos" para
TODO mundo, para sempre, sem nenhum jeito de recuperar quem deveria ve-la
(a informacao de quem marcou nunca existiu). Resetar para 'novo' e a unica
correcao coerente com a decisao do dono ("todos os gestores devem
receber") — o alerta reaparece uma vez para todos, o que e estritamente
melhor que ficar invisivel para sempre. Custo: um alerta repetido; nenhum
dado e perdido.
"""

import sqlalchemy as sa
from alembic import op


revision = "0023_copiloto_sinal_visto"
down_revision = "0022_copiloto_acao_pendente_e_estado_anterior"
branch_labels = None
depends_on = None

_TABELA = "copiloto_sinal_visto"
_TABELA_SINAL = "copiloto_sinal"
_NOME_CONSTRAINT = "ck_copiloto_sinal_estado"


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

    # Backfill ANTES de apertar a constraint: ver docstring do módulo. Trata
    # toda linha legada como "não vista por ninguém" — a única leitura
    # possível, já que o "visto" antigo nunca guardou quem a marcou.
    op.execute(f"UPDATE {_TABELA_SINAL} SET estado = 'novo' WHERE estado = 'visto'")

    # "visto" sai dos estados válidos: nenhum código volta a escrevê-lo por
    # engano agora que ele não existe mais como opção declarada.
    with op.batch_alter_table(_TABELA_SINAL) as batch:
        batch.drop_constraint(_NOME_CONSTRAINT, type_="check")
        batch.create_check_constraint(
            _NOME_CONSTRAINT, "estado IN ('novo', 'resolvido', 'dispensado')"
        )


def downgrade() -> None:
    # Restaura a constraint antiga (com "visto" aceito) — mas NÃO reverte o
    # backfill: não há como saber quais das linhas hoje "novo" eram
    # "visto" antes do upgrade (a informação foi perdida no próprio
    # backfill, de propósito, porque também não existia associada a
    # nenhuma pessoa). Fingir simetria aqui seria pior que admitir que o
    # downgrade é parcial: a constraint volta, os dados não.
    with op.batch_alter_table(_TABELA_SINAL) as batch:
        batch.drop_constraint(_NOME_CONSTRAINT, type_="check")
        batch.create_check_constraint(
            _NOME_CONSTRAINT,
            "estado IN ('novo', 'visto', 'resolvido', 'dispensado')",
        )

    op.drop_index("ix_copiloto_sinal_visto_usuario", table_name=_TABELA)
    op.drop_index("ix_copiloto_sinal_visto_sinal_id", table_name=_TABELA)
    op.drop_table(_TABELA)
