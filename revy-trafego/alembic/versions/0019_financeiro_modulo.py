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


def _trocar_check_codigo(valores: str) -> None:
    """Troca o CHECK de `modulos_revy.codigo` sem quebrar no Postgres.

    Mesma armadilha da 0018, repetida aqui de propósito: migration não importa
    helper compartilhado, senão uma migration antiga passa a depender de código
    que alguém pode mudar depois.

    `batch_alter_table(recreate="always")` copia a tabela inteira — o caminho do
    SQLite, que não sabe fazer ALTER de constraint. No Postgres a cópia estoura,
    porque a FK `fk_loja_modulos_modulo_id` de `loja_modulos` depende do índice
    da PK de `modulos_revy` (`DependentObjectsStillExist`). Achado no ensaio de
    16/08/2026.
    """
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_modulos_revy_codigo", "modulos_revy", type_="check")
        op.create_check_constraint(
            "ck_modulos_revy_codigo", "modulos_revy", f"codigo IN ({valores})"
        )
        return

    with op.batch_alter_table("modulos_revy", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_modulos_revy_codigo", type_="check")
        batch_op.create_check_constraint(
            "ck_modulos_revy_codigo", f"codigo IN ({valores})"
        )


def upgrade() -> None:
    _trocar_check_codigo("'vendas', 'estoque', 'copiloto', 'financeiro'")

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
