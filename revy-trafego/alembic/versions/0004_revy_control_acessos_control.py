"""Acesso ao Revy Control ligado à Pessoa Revy.

Revision ID: 0004_revy_control_acessos_control
Revises: 0003_revy_control_pessoas_cargos
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.control.access_backfill import (
    backfill_acessos_control,
    validar_colisoes_email_gestores_revy,
)


revision = "0004_revy_control_acessos_control"
down_revision = "0003_revy_control_pessoas_cargos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    validar_colisoes_email_gestores_revy(connection)
    op.create_table(
        "acessos_control",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("pessoa_id", sa.String(36), nullable=False),
        sa.Column("papel", sa.String(32), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=True),
        sa.Column(
            "sessao_versao",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("gestor_legado_id", sa.String(36), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "papel IN ('admin', 'gestor')",
            name="ck_acessos_control_papel",
        ),
        sa.CheckConstraint(
            "estado IN ('pendente', 'ativo', 'desativado')",
            name="ck_acessos_control_estado",
        ),
        sa.CheckConstraint(
            "sessao_versao >= 1",
            name="ck_acessos_control_sessao_versao",
        ),
        sa.ForeignKeyConstraint(
            ["pessoa_id"],
            ["pessoas.id"],
            name="fk_acessos_control_pessoa_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gestor_legado_id"],
            ["gestores_revy.id"],
            name="fk_acessos_control_gestor_legado_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pessoa_id",
            name="uq_acessos_control_pessoa_id",
        ),
        sa.UniqueConstraint(
            "gestor_legado_id",
            name="uq_acessos_control_gestor_legado_id",
        ),
    )
    backfill_acessos_control(connection)


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
