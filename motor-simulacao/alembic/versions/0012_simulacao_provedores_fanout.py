"""tarefas por provedor (fan-out) + worker_slots + evento.provedor

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulacao_eventos",
        sa.Column("provedor", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_simulacao_eventos_provedor", "simulacao_eventos", ["provedor"]
    )

    op.create_table(
        "simulacao_provedores",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "simulacao_id",
            sa.String(length=36),
            sa.ForeignKey("simulacoes.id"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            sa.String(length=36),
            sa.ForeignKey("clientes_api.id"),
            nullable=False,
        ),
        sa.Column("provedor", sa.String(length=100), nullable=False),
        sa.Column("tipo_driver", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="recebida"),
        sa.Column("tentativa", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserva_token", sa.String(length=36), nullable=True),
        sa.Column("reservada_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_slot_id", sa.String(length=36), nullable=True),
        sa.Column("codigo_erro", sa.String(length=120), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "simulacao_id", "provedor", name="uq_simulacao_provedores_sim_provedor"
        ),
    )
    op.create_index(
        "ix_simulacao_provedores_simulacao_id", "simulacao_provedores", ["simulacao_id"]
    )
    op.create_index(
        "ix_simulacao_provedores_cliente_id", "simulacao_provedores", ["cliente_id"]
    )
    op.create_index(
        "ix_simulacao_provedores_status", "simulacao_provedores", ["status"]
    )

    op.create_table(
        "worker_slots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provedor", sa.String(length=100), nullable=False),
        sa.Column("tipo_driver", sa.String(length=32), nullable=False),
        sa.Column("fly_machine_id", sa.String(length=64), nullable=False),
        sa.Column("regiao", sa.String(length=16), nullable=False, server_default="gru"),
        sa.Column("memory_mb", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("estado_observado", sa.String(length=40), nullable=True),
        sa.Column("ultimo_start_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_stop_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_falha_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("fly_machine_id", name="uq_worker_slots_fly_machine_id"),
    )
    op.create_index("ix_worker_slots_provedor", "worker_slots", ["provedor"])


def downgrade() -> None:
    op.drop_index("ix_worker_slots_provedor", table_name="worker_slots")
    op.drop_table("worker_slots")

    op.drop_index("ix_simulacao_provedores_status", table_name="simulacao_provedores")
    op.drop_index("ix_simulacao_provedores_cliente_id", table_name="simulacao_provedores")
    op.drop_index("ix_simulacao_provedores_simulacao_id", table_name="simulacao_provedores")
    op.drop_table("simulacao_provedores")

    op.drop_index("ix_simulacao_eventos_provedor", table_name="simulacao_eventos")
    op.drop_column("simulacao_eventos", "provedor")
