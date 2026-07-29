"""Versão monotônica das Lojas no Revy Control.

Revision ID: 0008_revy_control_loja_versao
Revises: 0007_revy_control_portfolio
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_revy_control_loja_versao"
down_revision = "0007_revy_control_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lojas") as batch_op:
        batch_op.add_column(
            sa.Column(
                "versao",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_lojas_versao",
            "versao >= 1",
        )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
