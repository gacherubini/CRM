"""config do agente por loja: versoes, rascunho e publicada

Spec 2026-08-24 §3.2. Duas tabelas novas, nada alterado no que ja existe.
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_agente_config"
down_revision = "0026_credencial_integracao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_table direto: o alvo e o Postgres do suite-pg. batch_alter_table
    # aqui daria portabilidade que a cadeia deste produto nao tem desde a 0017,
    # e batch no PG estoura com FK dependendo do indice da PK.
    op.create_table(
        "agente_config_versao",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("loja_id", sa.String(), sa.ForeignKey("lojas.id"), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("campos", sa.JSON(), nullable=False),
        sa.Column("prompt_gerado", sa.Text(), nullable=False),
        sa.Column("autor", sa.String(length=120), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agente_config_versao_loja_id", "agente_config_versao", ["loja_id"]
    )
    # No máximo um rascunho por loja: sem isto, salvar_rascunho e obter_rascunho
    # podem cada um enxergar uma linha diferente e o publicar seguinte põe o
    # texto errado no ar sem erro nenhum. Parcial (não UniqueConstraint simples)
    # porque duas versões "arquivada" da mesma loja são o histórico da feature.
    op.create_index(
        "uq_agente_config_versao_rascunho_por_loja",
        "agente_config_versao",
        ["loja_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'rascunho'"),
        sqlite_where=sa.text("estado = 'rascunho'"),
    )
    op.create_table(
        "agente_config",
        sa.Column("loja_id", sa.String(), sa.ForeignKey("lojas.id"), primary_key=True),
        sa.Column(
            "versao_publicada_id",
            sa.String(length=36),
            sa.ForeignKey("agente_config_versao.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("agente_config")
    op.drop_index(
        "uq_agente_config_versao_rascunho_por_loja",
        table_name="agente_config_versao",
    )
    op.drop_index("ix_agente_config_versao_loja_id", table_name="agente_config_versao")
    op.drop_table("agente_config_versao")
