"""Tabela whatsapp_canais (multi-WhatsApp skeleton).

Revision ID: 0015_whatsapp_canais
Revises: 0014_loja_operacional_projecao
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_whatsapp_canais"
down_revision = "0014_loja_operacional_projecao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_canais",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("e164_or_label", sa.String(length=80), nullable=False),
        sa.Column("evolution_instance", sa.String(length=120), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evolution_instance", name="uq_whatsapp_canais_instance"),
    )
    op.create_index("ix_whatsapp_canais_loja_id", "whatsapp_canais", ["loja_id"])
    op.create_index(
        "ix_whatsapp_canais_evolution_instance",
        "whatsapp_canais",
        ["evolution_instance"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_canais_evolution_instance", table_name="whatsapp_canais")
    op.drop_index("ix_whatsapp_canais_loja_id", table_name="whatsapp_canais")
    op.drop_table("whatsapp_canais")
