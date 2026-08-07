"""Religa vendas_projetadas.loja_id orfaos.

A projecao gravava apenas loja_slug, entao toda venda recebida do Portal depois
da 0002 ficou com loja_id NULL e sumia da Visao Geral do Control (que filtra por
loja_id). A projecao passou a resolver o vinculo; esta migration cura o passivo.

Revision ID: 0017_vendas_projetadas_backfill_loja_id
Revises: 0016_meta_ad_ultima_tentativa
"""

from alembic import op

from app.control.backfill import religar_vendas_orfas

revision = "0017_vendas_projetadas_backfill_loja_id"
down_revision = "0016_meta_ad_ultima_tentativa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    religar_vendas_orfas(op.get_bind())


def downgrade() -> None:
    # Backfill de dados: nada a desfazer sem perder vinculos legitimos.
    pass
