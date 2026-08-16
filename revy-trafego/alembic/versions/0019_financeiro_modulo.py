"""Adiciona o modulo Financeiro ao portfolio do Revy Control.

Revision ID: 0019_financeiro_modulo
Revises: 0018_copiloto_modulo

Leva de 2026-08-16: a Revy Loja ganhou a secao Financeiro (lucro por moto e
lucro operacional do mes). Como todo modulo, quem liga por loja e o Control.

Mesma forma da 0018: a CHECK tem que aceitar o codigo novo ANTES do insert de
catalogo, senao a propria insert viola a constraint.

Ninguem passa a ver a tela por causa desta migration. Contratar o modulo aqui
e condicao necessaria, nao suficiente: a Loja ainda exige a flag
REVY_LOJA_FINANCEIRO_ENABLED (default OFF) e papel de dono/gerente.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0019_financeiro_modulo"
down_revision = "0018_copiloto_modulo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("modulos_revy", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modulos_revy_codigo", type_="check")
        batch_op.create_check_constraint(
            "ck_modulos_revy_codigo",
            "codigo IN ('vendas', 'estoque', 'copiloto', 'financeiro')",
        )

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
                "id": "financeiro",
                "codigo": "financeiro",
                "nome": "Financeiro",
                "criado_em": datetime.now(timezone.utc),
            },
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
