"""credencial de integracao: loja_id passa a aceitar NULL

Spec 6.2: um workflow n8n-cloud serve N lojas, entao o token da plataforma nao
pertence a loja nenhuma. Credencial de loja continua exatamente como estava.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_credencial_integracao"
down_revision = "0025_canal_cloud_por_loja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER direto: o alvo e o Postgres do suite-pg. A cadeia deste produto ja
    # nao roda em SQLite desde a 0017 (add_column NOT NULL), entao batch aqui
    # daria portabilidade que a cadeia nao tem -- e batch no PG e justamente o
    # que estoura quando ha FK dependendo do indice da PK.
    op.alter_column(
        "credenciais_servico",
        "loja_id",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # As credenciais de integracao nao tem loja para onde voltar.
    op.execute("DELETE FROM credenciais_servico WHERE loja_id IS NULL")
    op.alter_column(
        "credenciais_servico",
        "loja_id",
        existing_type=sa.String(),
        nullable=False,
    )
