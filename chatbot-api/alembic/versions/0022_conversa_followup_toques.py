"""conversas.followup_toques: estado do cutucao de silencio (Modo 2)

Revision ID: 0022_conversa_followup_toques
Revises: 0021_oferta_lead

Spec dos dois modos, §5.9: 30 min sem resposta manda a msg 1, +1 h manda a
msg 2, e para. Saber em qual toque a conversa esta precisa de estado
duravel — inferir contando mensagens de saida desde o ultimo inbound
quebraria no dia em que o bot responder duas vezes seguidas.

Default 0 e server_default '0': conversa existente entra como "nenhum
toque dado", que e a leitura correta para o Modo 1 (que nao cutuca).
"""

import sqlalchemy as sa
from alembic import op


revision = "0022_conversa_followup_toques"
down_revision = "0021_oferta_lead"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversas") as batch:
        batch.add_column(
            sa.Column(
                "followup_toques", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("conversas") as batch:
        batch.drop_column("followup_toques")
