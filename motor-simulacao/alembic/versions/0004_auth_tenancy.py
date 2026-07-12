"""clientes, credenciais Bearer e isolamento de simulações por cliente

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTE_LEGADO_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "clientes_api",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "credenciais_api",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cliente_id", sa.String(36), sa.ForeignKey("clientes_api.id"), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_credenciais_api_cliente_id", "credenciais_api", ["cliente_id"])
    op.create_index("ix_credenciais_api_token_hash", "credenciais_api", ["token_hash"], unique=True)

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO clientes_api (id, nome, ativo, criado_em) "
            "VALUES (:id, :nome, :ativo, CURRENT_TIMESTAMP)"
        ),
        {"id": CLIENTE_LEGADO_ID, "nome": "Cliente legado", "ativo": True},
    )

    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cliente_id", sa.String(36), nullable=True))
    bind.execute(
        sa.text("UPDATE simulacoes SET cliente_id = :id WHERE cliente_id IS NULL"),
        {"id": CLIENTE_LEGADO_ID},
    )
    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.alter_column("cliente_id", existing_type=sa.String(36), nullable=False)
        batch_op.create_foreign_key(
            "fk_simulacoes_cliente_id", "clientes_api", ["cliente_id"], ["id"]
        )
        batch_op.create_index("ix_simulacoes_cliente_id", ["cliente_id"])

    # Recriação explícita troca a PK antiga (chave) pela PK composta. Funciona
    # igualmente em SQLite e Postgres, inclusive quando já existem linhas.
    op.create_table(
        "idempotencia_nova",
        sa.Column("cliente_id", sa.String(36), sa.ForeignKey("clientes_api.id"), primary_key=True),
        sa.Column("chave", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("simulacao_id", sa.String(36), sa.ForeignKey("simulacoes.id"), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    bind.execute(
        sa.text(
            "INSERT INTO idempotencia_nova "
            "(cliente_id, chave, request_hash, simulacao_id, criada_em) "
            "SELECT s.cliente_id, i.chave, i.request_hash, i.simulacao_id, i.criada_em "
            "FROM idempotencia i JOIN simulacoes s ON s.id = i.simulacao_id"
        )
    )
    op.drop_table("idempotencia")
    op.rename_table("idempotencia_nova", "idempotencia")


def downgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "idempotencia_antiga",
        sa.Column("chave", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("simulacao_id", sa.String(36), sa.ForeignKey("simulacoes.id"), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=True),
    )
    # Se clientes distintos reutilizaram a mesma chave, o schema antigo não
    # consegue representá-la. Falhar é mais seguro do que descartar dados.
    bind.execute(
        sa.text(
            "INSERT INTO idempotencia_antiga (chave, request_hash, simulacao_id, criada_em) "
            "SELECT chave, request_hash, simulacao_id, criada_em FROM idempotencia"
        )
    )
    op.drop_table("idempotencia")
    op.rename_table("idempotencia_antiga", "idempotencia")

    with op.batch_alter_table("simulacoes", schema=None) as batch_op:
        batch_op.drop_index("ix_simulacoes_cliente_id")
        batch_op.drop_constraint("fk_simulacoes_cliente_id", type_="foreignkey")
        batch_op.drop_column("cliente_id")

    op.drop_index("ix_credenciais_api_token_hash", table_name="credenciais_api")
    op.drop_index("ix_credenciais_api_cliente_id", table_name="credenciais_api")
    op.drop_table("credenciais_api")
    op.drop_table("clientes_api")
