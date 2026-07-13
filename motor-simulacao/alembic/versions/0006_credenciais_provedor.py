"""credenciais de portal bancário por cliente+provedor e trilha de auditoria

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credenciais_provedor",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cliente_id", sa.String(36), sa.ForeignKey("clientes_api.id"), nullable=False),
        sa.Column("provedor", sa.String(100), nullable=False),
        sa.Column("usuario", sa.String(200), nullable=False),
        # Senha do portal cifrada em repouso (Fernet via app.cripto); nunca em claro.
        sa.Column("senha_cifrada", sa.Text(), nullable=False),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("falhas_login", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_sucesso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro_sanitizado", sa.String(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "cliente_id", "provedor", name="uq_credenciais_provedor_cliente_provedor"
        ),
    )
    op.create_index(
        "ix_credenciais_provedor_cliente_id", "credenciais_provedor", ["cliente_id"]
    )

    op.create_table(
        "auditoria",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cliente_id", sa.String(36), sa.ForeignKey("clientes_api.id"), nullable=False),
        sa.Column("ator", sa.String(200), nullable=False),
        sa.Column("acao", sa.String(100), nullable=False),
        sa.Column("provedor", sa.String(100), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auditoria_cliente_id", "auditoria", ["cliente_id"])


def downgrade() -> None:
    op.drop_index("ix_auditoria_cliente_id", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_index("ix_credenciais_provedor_cliente_id", table_name="credenciais_provedor")
    op.drop_table("credenciais_provedor")
