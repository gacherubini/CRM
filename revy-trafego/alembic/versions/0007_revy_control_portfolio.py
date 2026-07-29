"""Portfólio de módulos e contratos das Lojas no Revy Control.

Revision ID: 0007_revy_control_portfolio
Revises: 0006_revy_control_recuperacoes
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0007_revy_control_portfolio"
down_revision = "0006_revy_control_recuperacoes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "modulos_revy",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("codigo", sa.String(32), nullable=False),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "codigo IN ('vendas', 'estoque')",
            name="ck_modulos_revy_codigo",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "codigo",
            name="uq_modulos_revy_codigo",
        ),
    )

    agora = datetime.now(timezone.utc)
    modulos_revy = sa.table(
        "modulos_revy",
        sa.column("id", sa.String(36)),
        sa.column("codigo", sa.String(32)),
        sa.column("nome", sa.String(160)),
        sa.column("criado_em", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        modulos_revy,
        [
            {
                "id": "vendas",
                "codigo": "vendas",
                "nome": "Vendas",
                "criado_em": agora,
            },
            {
                "id": "estoque",
                "codigo": "estoque",
                "nome": "Estoque",
                "criado_em": agora,
            },
        ],
    )

    op.create_table(
        "loja_modulos",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("modulo_id", sa.String(36), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column(
            "versao",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("contratado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("suspenso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('ativo', 'suspenso')",
            name="ck_loja_modulos_estado",
        ),
        sa.CheckConstraint(
            "versao >= 1",
            name="ck_loja_modulos_versao",
        ),
        sa.CheckConstraint(
            "(estado = 'ativo' AND suspenso_em IS NULL) OR "
            "(estado = 'suspenso' AND suspenso_em IS NOT NULL)",
            name="ck_loja_modulos_suspensao",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_loja_modulos_loja_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["modulo_id"],
            ["modulos_revy.id"],
            name="fk_loja_modulos_modulo_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_id",
            "modulo_id",
            name="uq_loja_modulos_loja_modulo",
        ),
    )

    op.create_table(
        "contratos_loja",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("valor_mensal", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "moeda",
            sa.String(3),
            server_default=sa.text("'BRL'"),
            nullable=False,
        ),
        sa.Column("vigencia_inicio", sa.Date(), nullable=False),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("vencimento_dia", sa.Integer(), nullable=False),
        sa.Column("situacao_cobranca", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "valor_mensal >= 0",
            name="ck_contratos_loja_valor_mensal",
        ),
        sa.CheckConstraint(
            "moeda = 'BRL'",
            name="ck_contratos_loja_moeda",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_contratos_loja_vigencia",
        ),
        sa.CheckConstraint(
            "vencimento_dia BETWEEN 1 AND 31",
            name="ck_contratos_loja_vencimento_dia",
        ),
        sa.CheckConstraint(
            "situacao_cobranca IN ('em_dia', 'atrasada', 'isenta')",
            name="ck_contratos_loja_situacao_cobranca",
        ),
        sa.CheckConstraint(
            "estado IN ('ativo', 'encerrado')",
            name="ck_contratos_loja_estado",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_contratos_loja_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contratos_loja_loja_id",
        "contratos_loja",
        ["loja_id"],
    )
    op.create_index(
        "uq_contratos_loja_ativo",
        "contratos_loja",
        ["loja_id"],
        unique=True,
        sqlite_where=sa.text("estado = 'ativo'"),
        postgresql_where=sa.text("estado = 'ativo'"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
