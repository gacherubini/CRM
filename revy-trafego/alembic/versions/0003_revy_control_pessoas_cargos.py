"""Pessoas canônicas e múltiplos cargos por Loja.

Revision ID: 0003_revy_control_pessoas_cargos
Revises: 0002_revy_control_lojas_rbac
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003_revy_control_pessoas_cargos"
down_revision = "0002_revy_control_lojas_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pessoas",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "email = lower(trim(email)) AND length(email) BETWEEN 3 AND 320",
            name="ck_pessoas_email_normalizado",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pessoas_email", "pessoas", ["email"], unique=True)

    op.create_table(
        "cargos_loja",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("pessoa_id", sa.String(36), nullable=False),
        sa.Column("cargo", sa.String(20), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("origem_id", sa.String(160), nullable=True),
        sa.CheckConstraint(
            "cargo IN ('dono', 'gerente', 'vendedor')",
            name="ck_cargos_loja_cargo",
        ),
        sa.CheckConstraint(
            "origem IN ('control', 'portal')",
            name="ck_cargos_loja_origem",
        ),
        sa.CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= iniciado_em",
            name="ck_cargos_loja_periodo",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_cargos_loja_loja_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pessoa_id"],
            ["pessoas.id"],
            name="fk_cargos_loja_pessoa_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cargos_loja_loja_id", "cargos_loja", ["loja_id"])
    op.create_index("ix_cargos_loja_pessoa_id", "cargos_loja", ["pessoa_id"])
    op.create_index(
        "uq_cargos_loja_cargo_ativo",
        "cargos_loja",
        ["loja_id", "pessoa_id", "cargo"],
        unique=True,
        sqlite_where=sa.text("encerrado_em IS NULL"),
        postgresql_where=sa.text("encerrado_em IS NULL"),
    )
    op.create_index(
        "uq_cargos_loja_origem_ativa",
        "cargos_loja",
        ["origem", "origem_id"],
        unique=True,
        sqlite_where=sa.text(
            "origem_id IS NOT NULL AND encerrado_em IS NULL"
        ),
        postgresql_where=sa.text(
            "origem_id IS NOT NULL AND encerrado_em IS NULL"
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
