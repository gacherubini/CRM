"""venda excluida: autoria e data da exclusao

Revision ID: 0024_venda_excluida
Revises: 0023_copiloto_sinal_visto

Leva de 2026-08-16: o dono passou a poder apagar uma venda registrada por
engano. Apagar NAO e cancelar — cancelar e negocio desfeito (fato comercial,
continua no historico), excluir e registro que nunca deveria ter existido.

A exclusao e logica: `vendas.status` recebe o valor 'excluida' e a linha
permanece. Nao ha DELETE por dois motivos concretos:

1. com o modulo Financeiro entrando na mesma leva, apagar linha e lucro de
   mes fechado mudando sozinho, sem rastro de quem mudou;
2. a entrega ao Control passa por outbox com retentativa. Se a linha sumisse
   e a entrega falhasse depois, nao existiria mais o que reenviar — a
   projecao de ROI la ficaria errada para sempre.

`status` e String(20) sem CheckConstraint, entao o valor novo nao exige
migration. Estas duas colunas exigem: sem elas, "quem apagou e quando" nao
tem onde morar, e uma exclusao viraria um estado sem autor.
"""

import sqlalchemy as sa
from alembic import op


revision = "0024_venda_excluida"
down_revision = "0023_copiloto_sinal_visto"
branch_labels = None
depends_on = None

_TABELA = "vendas"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.add_column(sa.Column("excluida_por", sa.String(length=320), nullable=True))
        batch.add_column(
            sa.Column("excluida_em", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    # Reverter devolve as vendas excluidas para as listas e para os totais,
    # com o status 'excluida' orfao de significado no codigo antigo. Quem
    # rodar isto em producao precisa decidir antes o que fazer com essas
    # linhas: nao ha resposta automatica correta aqui.
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_column("excluida_em")
        batch.drop_column("excluida_por")
