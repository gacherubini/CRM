"""Auditoria de sinais CTWA no inbound.

Revision ID: 0011_ctwa_auditoria
Revises: 0010_lead_ctwa
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_ctwa_auditoria"
down_revision = "0010_lead_ctwa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ctwa_auditoria",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("telefone_mascarado", sa.String(length=20), nullable=False),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("tem_ctwa_clid", sa.Boolean(), nullable=False),
        sa.Column("ctwa_clid_sufixo", sa.String(length=16), nullable=True),
        sa.Column("meta_ad_id", sa.String(length=64), nullable=True),
        sa.Column("meta_campaign_id", sa.String(length=64), nullable=True),
        sa.Column("meta_adset_id", sa.String(length=64), nullable=True),
        sa.Column("ctwa_source_type", sa.String(length=40), nullable=True),
        sa.Column("ctwa_codigo", sa.String(length=40), nullable=True),
        sa.Column("codigo_extraido_texto", sa.Boolean(), nullable=False),
        sa.Column("atribuido_lead", sa.Boolean(), nullable=False),
        sa.Column("sinais_json", sa.String(length=500), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ctwa_auditoria_loja_id", "ctwa_auditoria", ["loja_id"])
    op.create_index("ix_ctwa_auditoria_criada_em", "ctwa_auditoria", ["criada_em"])
    op.create_index("ix_ctwa_auditoria_tem_ctwa_clid", "ctwa_auditoria", ["tem_ctwa_clid"])


def downgrade() -> None:
    op.drop_index("ix_ctwa_auditoria_tem_ctwa_clid", table_name="ctwa_auditoria")
    op.drop_index("ix_ctwa_auditoria_criada_em", table_name="ctwa_auditoria")
    op.drop_index("ix_ctwa_auditoria_loja_id", table_name="ctwa_auditoria")
    op.drop_table("ctwa_auditoria")
