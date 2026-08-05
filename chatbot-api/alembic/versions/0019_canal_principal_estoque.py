"""whatsapp_canais.principal_estoque — um canal opera o grupo de estoque.

Revision ID: 0019_canal_principal_estoque
Revises: 0018_notificacoes_operacionais
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_canal_principal_estoque"
down_revision = "0018_notificacoes_operacionais"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_canais",
        sa.Column(
            "principal_estoque",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill: por loja, o canal ativo mais antigo vira principal.
    # SQL genérico via ORM-like update em duas etapas com dialect.
    conn = op.get_bind()
    lojas = conn.execute(sa.text("SELECT DISTINCT loja_id FROM whatsapp_canais")).fetchall()
    for (loja_id,) in lojas:
        row = conn.execute(
            sa.text(
                """
                SELECT id FROM whatsapp_canais
                WHERE loja_id = :loja AND ativo = true
                ORDER BY criado_em ASC
                LIMIT 1
                """
            ),
            {"loja": loja_id},
        ).fetchone()
        if row is None:
            row = conn.execute(
                sa.text(
                    """
                    SELECT id FROM whatsapp_canais
                    WHERE loja_id = :loja
                    ORDER BY criado_em ASC
                    LIMIT 1
                    """
                ),
                {"loja": loja_id},
            ).fetchone()
        if row is not None:
            conn.execute(
                sa.text(
                    "UPDATE whatsapp_canais SET principal_estoque = true WHERE id = :id"
                ),
                {"id": row[0]},
            )
    op.alter_column("whatsapp_canais", "principal_estoque", server_default=None)


def downgrade() -> None:
    op.drop_column("whatsapp_canais", "principal_estoque")
