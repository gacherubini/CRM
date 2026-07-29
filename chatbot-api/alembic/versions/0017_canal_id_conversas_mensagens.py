"""canal_id em conversas/mensagens + estado no canal (multi-WA expand).

Revision ID: 0017_canal_id_conversas_mensagens
Revises: 0015_whatsapp_canais

Expand:
- whatsapp_canais.estado (pendente|conectado|desconectado|inativo)
- conversas.canal_id FK nullable + unique (canal_id, telefone)
- mensagens.canal_id FK nullable
- troca unique mensagens: (loja_id, provider_message_id) → (canal_id, provider_message_id)
- backfill canal_id a partir do canal legado (loja + evolution_instance)
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_canal_id_conversas_mensagens"
down_revision = "0016_lead_google_click_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_canais",
        sa.Column(
            "estado",
            sa.String(length=20),
            nullable=False,
            server_default="conectado",
        ),
    )

    op.add_column(
        "conversas",
        sa.Column("canal_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_conversas_canal_id", "conversas", ["canal_id"])
    op.create_foreign_key(
        "fk_conversas_canal_id",
        "conversas",
        "whatsapp_canais",
        ["canal_id"],
        ["id"],
    )

    op.add_column(
        "mensagens",
        sa.Column("canal_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_mensagens_canal_id", "mensagens", ["canal_id"])
    op.create_foreign_key(
        "fk_mensagens_canal_id",
        "mensagens",
        "whatsapp_canais",
        ["canal_id"],
        ["id"],
    )

    # Backfill: canal legado por loja (instância da loja) → conversas e mensagens.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE conversas
            SET canal_id = (
                SELECT c.id FROM whatsapp_canais c
                WHERE c.loja_id = conversas.loja_id
                ORDER BY c.criado_em ASC
                LIMIT 1
            )
            WHERE canal_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE mensagens
            SET canal_id = (
                SELECT cv.canal_id FROM conversas cv
                WHERE cv.id = mensagens.conversa_id
            )
            WHERE canal_id IS NULL
            """
        )
    )
    # Mensagens sem conversa resolvida: tenta canal da loja.
    conn.execute(
        sa.text(
            """
            UPDATE mensagens
            SET canal_id = (
                SELECT c.id FROM whatsapp_canais c
                WHERE c.loja_id = mensagens.loja_id
                ORDER BY c.criado_em ASC
                LIMIT 1
            )
            WHERE canal_id IS NULL
            """
        )
    )

    # Unique conversas (canal_id, telefone) — NULLs de canal_id não colidem.
    with op.batch_alter_table("conversas") as batch_op:
        batch_op.create_unique_constraint(
            "uq_conversas_canal_telefone", ["canal_id", "telefone"]
        )

    # Troca unique de mensagens para permitir mesmo provider_id em canais distintos.
    with op.batch_alter_table("mensagens") as batch_op:
        batch_op.drop_constraint("uq_mensagens_loja_provider", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mensagens_canal_provider", ["canal_id", "provider_message_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("mensagens") as batch_op:
        batch_op.drop_constraint("uq_mensagens_canal_provider", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mensagens_loja_provider", ["loja_id", "provider_message_id"]
        )

    with op.batch_alter_table("conversas") as batch_op:
        batch_op.drop_constraint("uq_conversas_canal_telefone", type_="unique")

    op.drop_constraint("fk_mensagens_canal_id", "mensagens", type_="foreignkey")
    op.drop_index("ix_mensagens_canal_id", table_name="mensagens")
    op.drop_column("mensagens", "canal_id")

    op.drop_constraint("fk_conversas_canal_id", "conversas", type_="foreignkey")
    op.drop_index("ix_conversas_canal_id", table_name="conversas")
    op.drop_column("conversas", "canal_id")

    op.drop_column("whatsapp_canais", "estado")
