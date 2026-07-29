"""Recuperações de senha dos acessos ao Revy Control.

Revision ID: 0006_revy_control_recuperacoes
Revises: 0005_revy_control_convites
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_revy_control_recuperacoes"
down_revision = "0005_revy_control_convites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recuperacoes_senha_control",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("acesso_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por_gestor_id", sa.String(36), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expira_em >= criado_em",
            name="ck_recuperacoes_senha_control_expiracao",
        ),
        sa.CheckConstraint(
            "usado_em IS NULL OR usado_em >= criado_em",
            name="ck_recuperacoes_senha_control_uso",
        ),
        sa.CheckConstraint(
            "revogado_em IS NULL OR revogado_em >= criado_em",
            name="ck_recuperacoes_senha_control_revogacao",
        ),
        sa.ForeignKeyConstraint(
            ["acesso_id"],
            ["acessos_control.id"],
            name="fk_recuperacoes_senha_control_acesso_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["criado_por_gestor_id"],
            ["gestores_revy.id"],
            name="fk_recuperacoes_senha_control_criado_por_gestor_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_recuperacoes_senha_control_token_hash",
        ),
    )
    op.create_index(
        "ix_recuperacoes_senha_control_acesso_id",
        "recuperacoes_senha_control",
        ["acesso_id"],
    )
    op.create_index(
        "ix_recuperacoes_senha_control_criado_por_gestor_id",
        "recuperacoes_senha_control",
        ["criado_por_gestor_id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
