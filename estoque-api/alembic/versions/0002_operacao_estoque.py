"""Fotos, importações, outbox e auditoria.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_veiculos_loja_codigo", "veiculos", ["loja_id", "codigo_interno"])
    op.create_table(
        "veiculo_fotos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("veiculo_id", sa.String(36), sa.ForeignKey("veiculos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("veiculo_id", "ordem", name="uq_veiculo_foto_ordem"),
    )
    op.create_index("ix_veiculo_fotos_loja_id", "veiculo_fotos", ["loja_id"])
    op.create_index("ix_veiculo_fotos_veiculo_id", "veiculo_fotos", ["veiculo_id"])
    op.create_table(
        "importacoes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_linhas", sa.Integer(), nullable=False),
        sa.Column("importadas", sa.Integer(), nullable=False),
        sa.Column("atualizadas", sa.Integer(), nullable=False),
        sa.Column("erros", sa.JSON(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_importacoes_loja_id", "importacoes", ["loja_id"])
    op.create_table(
        "eventos_saida",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("agregado_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eventos_saida_loja_id", "eventos_saida", ["loja_id"])
    op.create_index("ix_eventos_saida_tipo", "eventos_saida", ["tipo"])
    op.create_index("ix_eventos_saida_agregado_id", "eventos_saida", ["agregado_id"])
    op.create_table(
        "auditoria",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("loja_id", sa.String(36), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("recurso", sa.String(), nullable=False),
        sa.Column("recurso_id", sa.String(36), nullable=False),
        sa.Column("acao", sa.String(), nullable=False),
        sa.Column("ator_papel", sa.String(), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auditoria_loja_id", "auditoria", ["loja_id"])
    op.create_index("ix_auditoria_recurso_id", "auditoria", ["recurso_id"])


def downgrade() -> None:
    op.drop_table("auditoria")
    op.drop_table("eventos_saida")
    op.drop_table("importacoes")
    op.drop_table("veiculo_fotos")
    op.drop_constraint("uq_veiculos_loja_codigo", "veiculos", type_="unique")
