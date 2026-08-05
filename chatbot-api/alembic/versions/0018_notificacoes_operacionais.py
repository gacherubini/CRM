"""notificacoes_operacionais — alerta de simulação no grupo de estoque.

Revision ID: 0018_notificacoes_operacionais
Revises: 0017_canal_id_conversas_msg
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_notificacoes_operacionais"
down_revision = "0017_canal_id_conversas_msg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notificacoes_operacionais",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(length=36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column(
            "canal_id",
            sa.String(length=36),
            sa.ForeignKey("whatsapp_canais.id"),
            nullable=True,
        ),
        sa.Column("tipo", sa.String(length=40), nullable=False, server_default="simulacao_humana"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("destino_jid", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("payload_resumo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "loja_id", "idempotency_key", name="uq_notif_op_loja_idempotency"
        ),
    )
    op.create_index(
        "ix_notificacoes_operacionais_loja_id",
        "notificacoes_operacionais",
        ["loja_id"],
    )
    op.create_index(
        "ix_notificacoes_operacionais_canal_id",
        "notificacoes_operacionais",
        ["canal_id"],
    )
    op.create_index(
        "ix_notificacoes_operacionais_status",
        "notificacoes_operacionais",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_notificacoes_operacionais_status", table_name="notificacoes_operacionais")
    op.drop_index("ix_notificacoes_operacionais_canal_id", table_name="notificacoes_operacionais")
    op.drop_index("ix_notificacoes_operacionais_loja_id", table_name="notificacoes_operacionais")
    op.drop_table("notificacoes_operacionais")
