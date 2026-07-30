"""Trilha append-only de operações Loja (atendimento + financeiras).

Revision ID: 0014_loja_operacao_auditoria
Revises: 0013_loja_operacional_projecao
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_loja_operacao_auditoria"
down_revision = "0013_loja_operacional_projecao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loja_operacao_auditoria",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("dominio", sa.String(length=20), nullable=False),
        sa.Column("acao", sa.String(length=40), nullable=False),
        sa.Column("ator_email", sa.String(length=320), nullable=False),
        sa.Column("telefone_hmac", sa.String(length=64), nullable=True),
        sa.Column("de_email", sa.String(length=320), nullable=True),
        sa.Column("para_email", sa.String(length=320), nullable=True),
        sa.Column("origem", sa.String(length=40), nullable=True),
        sa.Column("provedor", sa.String(length=80), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dominio IN ('atendimento', 'financeira')",
            name="ck_loja_operacao_auditoria_dominio",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_loja_operacao_auditoria_loja_slug",
        "loja_operacao_auditoria",
        ["loja_slug"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_dominio",
        "loja_operacao_auditoria",
        ["dominio"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_acao",
        "loja_operacao_auditoria",
        ["acao"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_telefone_hmac",
        "loja_operacao_auditoria",
        ["telefone_hmac"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_provedor",
        "loja_operacao_auditoria",
        ["provedor"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_criado_em",
        "loja_operacao_auditoria",
        ["criado_em"],
    )
    op.create_index(
        "ix_loja_operacao_auditoria_loja_dominio_criado",
        "loja_operacao_auditoria",
        ["loja_slug", "dominio", "criado_em"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_loja_operacao_auditoria_loja_dominio_criado",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_criado_em",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_provedor",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_telefone_hmac",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_acao",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_dominio",
        table_name="loja_operacao_auditoria",
    )
    op.drop_index(
        "ix_loja_operacao_auditoria_loja_slug",
        table_name="loja_operacao_auditoria",
    )
    op.drop_table("loja_operacao_auditoria")
