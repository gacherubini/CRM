"""whatsapp_canais: waba_id e template_oferta — credencial Cloud por loja (spec §6.2)

Revision ID: 0025_canal_cloud_por_loja
Revises: 0024_cloud_evento_falho

O Modo 2 saiu do piloto com uma credencial global (CHATBOT_GRAPH_PHONE_NUMBER_ID
e CHATBOT_GRAPH_TEMPLATE_OFERTA). Com duas lojas Cloud no mesmo processo isso
manda a mensagem de uma pelo numero da outra, e template de mensagem e recurso
da WABA — o nome aprovado numa loja nao existe na outra.

Expand-only, as duas colunas nullable e sem backfill: canal sem valor gravado
cai na variavel de ambiente, entao a loja piloto continua funcionando sem
migracao de dado manual.

O phone_number_id NAO ganha coluna: ele reusa `evolution_instance`, que ja e a
chave de roteamento do inbound nos dois modos. Economia deliberada de migration.

Token de System User, App Secret e verify token sao do Revy (um app na Meta) e
seguem em variavel de ambiente — de proposito nao ha coluna para eles.
"""
import sqlalchemy as sa
from alembic import op


revision = "0025_canal_cloud_por_loja"
down_revision = "0024_cloud_evento_falho"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # waba_id nao nulo e o que marca o canal como Cloud (ver app/cloud_canal.py).
    op.add_column(
        "whatsapp_canais",
        sa.Column("waba_id", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("template_oferta", sa.String(length=120), nullable=True),
    )
    # Lookup do canal Cloud da loja no envio: sem isto e varredura por loja.
    op.create_index(
        "ix_whatsapp_canais_waba_id",
        "whatsapp_canais",
        ["waba_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_canais_waba_id", table_name="whatsapp_canais")
    op.drop_column("whatsapp_canais", "template_oferta")
    op.drop_column("whatsapp_canais", "waba_id")
