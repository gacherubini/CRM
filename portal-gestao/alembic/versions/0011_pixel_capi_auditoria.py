"""Auditoria de chaves Pixel / CAPI (match keys sem PII).

Revision ID: 0011_pixel_capi_auditoria
Revises: 0010_campanha_codigo_ctwa
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_pixel_capi_auditoria"
down_revision = "0010_campanha_codigo_ctwa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pixel_capi_auditoria",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("origem", sa.String(length=40), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=True),
        sa.Column("event_id", sa.String(length=120), nullable=True),
        sa.Column("pixel_id_sufixo", sa.String(length=12), nullable=True),
        sa.Column("modo", sa.String(length=20), nullable=True),
        sa.Column("tem_ph", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_em", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_fbclid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_fbc", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_ctwa_clid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_external_id", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tem_test_event_code", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enviar_page_view", sa.Boolean(), nullable=True),
        sa.Column("enviar_lead", sa.Boolean(), nullable=True),
        sa.Column("enviar_purchase", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("venda_id", sa.String(length=36), nullable=True),
        sa.Column("detalhe", sa.String(length=240), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pixel_capi_auditoria_loja_slug", "pixel_capi_auditoria", ["loja_slug"])
    op.create_index("ix_pixel_capi_auditoria_criada_em", "pixel_capi_auditoria", ["criada_em"])
    op.create_index("ix_pixel_capi_auditoria_origem", "pixel_capi_auditoria", ["origem"])


def downgrade() -> None:
    op.drop_index("ix_pixel_capi_auditoria_origem", table_name="pixel_capi_auditoria")
    op.drop_index("ix_pixel_capi_auditoria_criada_em", table_name="pixel_capi_auditoria")
    op.drop_index("ix_pixel_capi_auditoria_loja_slug", table_name="pixel_capi_auditoria")
    op.drop_table("pixel_capi_auditoria")
