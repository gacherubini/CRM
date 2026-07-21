"""Cria eventos idempotentes do funil por loja.

Revision ID: 0008_funil_eventos
Revises: 0007_onboarding_medicao
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_funil_eventos"
down_revision = "0007_onboarding_medicao"
branch_labels = None
depends_on = None


TIPOS = (
    "lead_criado",
    "primeira_resposta",
    "simulacao_solicitada",
    "etapa_manual",
    "venda_registrada",
    "venda_confirmada",
    "perda",
)


def upgrade() -> None:
    tipos_sql = ", ".join(f"'{tipo}'" for tipo in TIPOS)
    op.create_table(
        "funil_eventos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("lead_ref", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("ocorrido_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ator_email", sa.String(length=320), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"tipo IN ({tipos_sql})", name="ck_funil_evento_tipo"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "loja_slug",
            "idempotency_key",
            name="uq_funil_evento_loja_idempotencia",
        ),
    )
    op.create_index(
        "ix_funil_eventos_loja_lead_ocorrido",
        "funil_eventos",
        ["loja_slug", "lead_ref", "ocorrido_em"],
    )
    op.create_index(
        "ix_funil_eventos_loja_tipo_ocorrido",
        "funil_eventos",
        ["loja_slug", "tipo", "ocorrido_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_funil_eventos_loja_tipo_ocorrido", table_name="funil_eventos")
    op.drop_index("ix_funil_eventos_loja_lead_ocorrido", table_name="funil_eventos")
    op.drop_table("funil_eventos")
