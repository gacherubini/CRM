"""Loja de primeira classe, vínculos de tráfego e auditoria administrativa.

Revision ID: 0002_revy_control_lojas_rbac
Revises: 0001_revy_trafego_baseline
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.control.backfill import (
    TABELAS_LEGADAS_COM_LOJA,
    backfill_lojas_confirmadas,
)


revision = "0002_revy_control_lojas_rbac"
down_revision = "0001_revy_trafego_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lojas",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slug = lower(trim(slug)) AND length(slug) BETWEEN 1 AND 120",
            name="ck_lojas_slug_canonico",
        ),
        sa.CheckConstraint(
            "status IN ('rascunho', 'em_configuracao', 'pronta', 'ativa', "
            "'suspensa', 'encerrada')",
            name="ck_lojas_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lojas_slug", "lojas", ["slug"], unique=True)
    op.create_index("ix_lojas_status", "lojas", ["status"])

    op.create_table(
        "vinculos_trafego",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=False),
        sa.Column("gestor_id", sa.String(36), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('responsavel', 'colaborador')",
            name="ck_vinculos_trafego_tipo",
        ),
        sa.CheckConstraint(
            "encerrado_em IS NULL OR encerrado_em >= iniciado_em",
            name="ck_vinculos_trafego_periodo",
        ),
        sa.ForeignKeyConstraint(
            ["gestor_id"],
            ["gestores_revy.id"],
            name="fk_vinculos_trafego_gestor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_vinculos_trafego_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vinculos_trafego_loja_id", "vinculos_trafego", ["loja_id"]
    )
    op.create_index(
        "ix_vinculos_trafego_gestor_id", "vinculos_trafego", ["gestor_id"]
    )
    op.create_index(
        "uq_vinculos_trafego_gestor_ativo",
        "vinculos_trafego",
        ["loja_id", "gestor_id"],
        unique=True,
        sqlite_where=sa.text("encerrado_em IS NULL"),
        postgresql_where=sa.text("encerrado_em IS NULL"),
    )
    op.create_index(
        "uq_vinculos_trafego_responsavel_ativo",
        "vinculos_trafego",
        ["loja_id"],
        unique=True,
        sqlite_where=sa.text(
            "encerrado_em IS NULL AND tipo = 'responsavel'"
        ),
        postgresql_where=sa.text(
            "encerrado_em IS NULL AND tipo = 'responsavel'"
        ),
    )

    op.create_table(
        "auditoria_eventos",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("loja_id", sa.String(36), nullable=True),
        sa.Column("ator_gestor_id", sa.String(36), nullable=True),
        sa.Column("ator_email", sa.String(320), nullable=True),
        sa.Column("acao", sa.String(100), nullable=False),
        sa.Column("recurso_tipo", sa.String(80), nullable=False),
        sa.Column("recurso_id", sa.String(160), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("antes_json", sa.Text(), nullable=True),
        sa.Column("depois_json", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resultado IN ('sucesso', 'negado', 'erro')",
            name="ck_auditoria_eventos_resultado",
        ),
        sa.ForeignKeyConstraint(
            ["ator_gestor_id"],
            ["gestores_revy.id"],
            name="fk_auditoria_eventos_ator_gestor_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name="fk_auditoria_eventos_loja_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for nome, colunas in (
        ("ix_auditoria_eventos_loja_id", ["loja_id"]),
        ("ix_auditoria_eventos_ator_gestor_id", ["ator_gestor_id"]),
        ("ix_auditoria_eventos_acao", ["acao"]),
        ("ix_auditoria_eventos_criado_em", ["criado_em"]),
    ):
        op.create_index(nome, "auditoria_eventos", colunas)

    inspector = sa.inspect(op.get_bind())
    tabelas_existentes = set(inspector.get_table_names())
    for tabela in TABELAS_LEGADAS_COM_LOJA:
        if tabela not in tabelas_existentes:
            continue
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.add_column(
                sa.Column("loja_id", sa.String(36), nullable=True)
            )
            batch_op.create_foreign_key(
                f"fk_{tabela}_loja_id",
                "lojas",
                ["loja_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_index(f"ix_{tabela}_loja_id", ["loja_id"])

    backfill_lojas_confirmadas(op.get_bind())


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
