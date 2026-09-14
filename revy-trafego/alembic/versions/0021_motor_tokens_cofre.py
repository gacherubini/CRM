"""Cofre de tokens do Motor por loja (uma linha por slug, só blob cifrado).

Revision ID: 0021_motor_tokens_cofre
Revises: 0020_loja_whatsapp_modo

Tabela nova, sem backfill: loja criada passa a ganhar credencial via ensure do
Motor (sem CLI nem edição de secret); o claro nunca pousa aqui, só o blob
Fernet. Downgrade derruba só o que este upgrade criou.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0021_motor_tokens_cofre"
down_revision = "0020_loja_whatsapp_modo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "motor_tokens_cofre",
        sa.Column("loja_slug", sa.String(120), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(loja_slug) BETWEEN 1 AND 120",
            name="ck_motor_tokens_cofre_slug",
        ),
        sa.PrimaryKeyConstraint("loja_slug"),
    )


def downgrade() -> None:
    op.drop_table("motor_tokens_cofre")
