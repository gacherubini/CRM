"""cria copiloto_conversa e copiloto_turno

Revision ID: 0020_copiloto_conversa_turno
Revises: 0019_copiloto_sinal
"""

import sqlalchemy as sa
from alembic import op


revision = "0020_copiloto_conversa_turno"
down_revision = "0019_copiloto_sinal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copiloto_conversa",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arquivada_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copiloto_conversa_loja_slug", "copiloto_conversa", ["loja_slug"]
    )
    op.create_index(
        "ix_copiloto_conversa_usuario_id", "copiloto_conversa", ["usuario_id"]
    )
    op.create_index(
        "ix_copiloto_conversa_loja_usuario",
        "copiloto_conversa",
        ["loja_slug", "usuario_id", "atualizada_em"],
    )
    op.create_table(
        "copiloto_turno",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversa_id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("pergunta", sa.String(length=4000), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("passos_json", sa.Text(), nullable=True),
        sa.Column("texto_parcial", sa.Text(), nullable=True),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("erro_code", sa.String(length=40), nullable=True),
        sa.Column("tokens_entrada", sa.Integer(), nullable=False),
        sa.Column("tokens_saida", sa.Integer(), nullable=False),
        sa.Column("custo_estimado", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('pendente', 'executando', 'pronto', 'erro', 'cancelado')",
            name="ck_copiloto_turno_estado",
        ),
        sa.ForeignKeyConstraint(
            ["conversa_id"], ["copiloto_conversa.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copiloto_turno_conversa_id", "copiloto_turno", ["conversa_id"])
    op.create_index("ix_copiloto_turno_loja_slug", "copiloto_turno", ["loja_slug"])
    op.create_index(
        "ix_copiloto_turno_estado_criado", "copiloto_turno", ["estado", "criado_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_copiloto_turno_estado_criado", table_name="copiloto_turno")
    op.drop_index("ix_copiloto_turno_loja_slug", table_name="copiloto_turno")
    op.drop_index("ix_copiloto_turno_conversa_id", table_name="copiloto_turno")
    op.drop_table("copiloto_turno")
    op.drop_index("ix_copiloto_conversa_loja_usuario", table_name="copiloto_conversa")
    op.drop_index("ix_copiloto_conversa_usuario_id", table_name="copiloto_conversa")
    op.drop_index("ix_copiloto_conversa_loja_slug", table_name="copiloto_conversa")
    op.drop_table("copiloto_conversa")
