"""perfil: avatar preset + foto propria na tabela usuarios

Revision ID: 0027_perfil_avatar_foto
Revises: 0026_copiloto_sinal_destinatario

`avatar_key` guarda o slug do bichinho escolhido na galeria do Perfil
(NULL = inicial do nome, o comportamento de antes); `foto_perfil` guarda
os bytes do upload proprio (banco, nao disco — disco local nao persiste
no Fly). As duas nullable porque toda linha legada e inicial-por-padrao:
nenhum backfill, nenhuma mudanca de comportamento sem acao da pessoa.
"""

import sqlalchemy as sa
from alembic import op


revision = "0027_perfil_avatar_foto"
down_revision = "0026_copiloto_sinal_destinatario"
branch_labels = None
depends_on = None

_TABELA = "usuarios"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.add_column(sa.Column("avatar_key", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("foto_perfil", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    # Some o avatar/foto gravados depois do upgrade — no modelo antigo nao
    # existe onde guarda-los. Linha legada (NULL/NULL) volta intacta.
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_column("foto_perfil")
        batch.drop_column("avatar_key")
