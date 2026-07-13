"""Config Meta Pixel + outbox CAPI (E10)."""

from alembic import op
import sqlalchemy as sa


revision = "0005_meta_pixel_capi"
down_revision = "0004_cria_atendimento_atribuicoes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_pixel_config",
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("pixel_id", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.String(length=1024), nullable=True),
        sa.Column("test_event_code", sa.String(length=64), nullable=True),
        sa.Column("enviar_page_view", sa.Boolean(), nullable=False),
        sa.Column("enviar_lead", sa.Boolean(), nullable=False),
        sa.Column("enviar_purchase", sa.Boolean(), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("loja_slug"),
    )
    op.create_table(
        "meta_capi_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("venda_id", sa.String(length=36), nullable=True),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.String(length=4000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meta_capi_outbox_loja_slug"), "meta_capi_outbox", ["loja_slug"])
    op.create_index(op.f("ix_meta_capi_outbox_venda_id"), "meta_capi_outbox", ["venda_id"])
    op.create_index(op.f("ix_meta_capi_outbox_event_id"), "meta_capi_outbox", ["event_id"], unique=True)
    op.create_index(op.f("ix_meta_capi_outbox_status"), "meta_capi_outbox", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_meta_capi_outbox_status"), table_name="meta_capi_outbox")
    op.drop_index(op.f("ix_meta_capi_outbox_event_id"), table_name="meta_capi_outbox")
    op.drop_index(op.f("ix_meta_capi_outbox_venda_id"), table_name="meta_capi_outbox")
    op.drop_index(op.f("ix_meta_capi_outbox_loja_slug"), table_name="meta_capi_outbox")
    op.drop_table("meta_capi_outbox")
    op.drop_table("meta_pixel_config")
