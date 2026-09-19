"""simulacao: ordem de consulta dos bancos por loja

Revision ID: 0028_simulacao_ordem_bancos
Revises: 0027_perfil_avatar_foto

Guarda a ordem dos bancos na simulação manual (`ordem_json`, lista JSON em
texto). Ausente/vazio = ordem padrão (lista de credenciais), então não há
backfill e nenhuma loja muda de comportamento sem reordenar na tela.
"""

import sqlalchemy as sa
from alembic import op


revision = "0028_simulacao_ordem_bancos"
down_revision = "0027_perfil_avatar_foto"
branch_labels = None
depends_on = None

_TABELA = "simulacao_ordem_bancos"


def upgrade() -> None:
    op.create_table(
        _TABELA,
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("ordem_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("loja_slug"),
    )


def downgrade() -> None:
    op.drop_table(_TABELA)
