"""Adiciona o módulo Copiloto ao portfólio do Revy Control.

Revision ID: 0018_copiloto_modulo
Revises: 0017_vendas_projetadas_backfill_loja_id
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0018_copiloto_modulo"
down_revision = "0017_vendas_projetadas_backfill_loja_id"
branch_labels = None
depends_on = None


def _trocar_check_codigo(valores: str) -> None:
    """Troca o CHECK de `modulos_revy.codigo` sem quebrar no Postgres.

    `batch_alter_table(recreate="always")` é o caminho do SQLite, que não sabe
    fazer ALTER de constraint: ele copia a tabela inteira e recria tudo, PK
    inclusive. No Postgres essa cópia estoura, porque a FK
    `fk_loja_modulos_modulo_id` de `loja_modulos` depende do índice da PK:

        DependentObjectsStillExist: cannot drop constraint modulos_revy_pkey

    Achado no ensaio de 16/08/2026, rodando as migrations do zero contra o
    Postgres de verdade. No Postgres o ALTER direto existe, então não há por que
    reconstruir a tabela — o ramo por dialeto é o conserto, e não um hack de
    janela.
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
    # A CHECK original só admitia ('vendas', 'estoque'); recria com copiloto
    # antes de inserir a linha de catálogo (senão a própria insert viola o CHECK).
    _trocar_check_codigo("'vendas', 'estoque', 'copiloto'")

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
                "id": "copiloto",
                "codigo": "copiloto",
                "nome": "Copiloto de Vendas",
                "criado_em": datetime.now(timezone.utc),
            },
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
