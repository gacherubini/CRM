"""Loja escolhe o modo de WhatsApp (1 Baileys+grupo, 2 central Cloud).

Revision ID: 0019_loja_whatsapp_modo
Revises: 0018_copiloto_modulo

Spec dos dois modos, §5.8: o tipo de atendimento e escolha do Control, por
loja, e 1 XOR 2 — nunca os dois. Server default 1 para que toda loja
existente continue no comportamento de hoje: o backfill e semanticamente
correto, nao um chute.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019_loja_whatsapp_modo"
down_revision = "0018_copiloto_modulo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lojas") as batch_op:
        batch_op.add_column(
            sa.Column(
                "whatsapp_modo",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_check_constraint(
            "ck_lojas_whatsapp_modo", "whatsapp_modo IN (1, 2)"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
