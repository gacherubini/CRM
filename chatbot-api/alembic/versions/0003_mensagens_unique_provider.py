"""dedupe no banco: UNIQUE em mensagens (loja_id, provider_message_id)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # provider_message_id nulo continua permitido em várias linhas; só ids reais deduplicam.
    with op.batch_alter_table("mensagens") as batch_op:
        batch_op.create_unique_constraint(
            "uq_mensagens_loja_provider", ["loja_id", "provider_message_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("mensagens") as batch_op:
        batch_op.drop_constraint("uq_mensagens_loja_provider", type_="unique")
