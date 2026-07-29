from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa


APP_DIR = Path(__file__).resolve().parents[1]
TABELAS_COM_LOJA = (
    "vendas_projetadas",
    "meta_pixel_config",
    "meta_ads_config",
    "pixel_capi_auditoria",
    "meta_capi_outbox",
    "campanhas",
    "campanha_gastos",
)


def _alembic_upgrade(database_url: str, revision: str) -> None:
    env = os.environ.copy()
    env["REVY_TRAFEGO_DATABASE_URL"] = database_url
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            revision,
        ],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_aditiva_e_backfill_repetido_sao_idempotentes(tmp_path):
    banco = tmp_path / "control.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "0001_revy_trafego_baseline")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO meta_pixel_config (
                    loja_slug, pixel_id, token_ciphertext, test_event_code,
                    enviar_page_view, enviar_lead, enviar_purchase,
                    medicao_onboarding_dismiss_em, atualizada_em
                ) VALUES (
                    'loja-demo', '', NULL, NULL, 1, 1, 1, NULL, :agora
                )
                """
            ),
            {"agora": agora},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO campanhas (
                    id, loja_slug, nome, canal, status, utm_source, utm_medium,
                    utm_campaign, utm_campaign_norm, utm_content, utm_term,
                    meta_campaign_id, codigo_ctwa, periodo_inicio, periodo_fim,
                    notas, criada_em, atualizada_em, criada_por_email
                ) VALUES (
                    'campanha-1', 'loja-dois', 'Campanha', 'meta', 'ativa',
                    NULL, NULL, 'campanha', 'campanha', NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL, :agora, :agora, 'admin@revy.local'
                )
                """
            ),
            {"agora": agora},
        )

    _alembic_upgrade(database_url, "head")

    inspector = sa.inspect(engine)
    assert {"lojas", "vinculos_trafego", "auditoria_eventos"} <= set(
        inspector.get_table_names()
    )
    for tabela in TABELAS_COM_LOJA:
        assert "loja_id" in {coluna["name"] for coluna in inspector.get_columns(tabela)}

    with engine.begin() as connection:
        lojas = connection.execute(
            sa.text("SELECT slug, status FROM lojas ORDER BY slug")
        ).all()
        assert lojas == [("loja-demo", "rascunho"), ("loja-dois", "rascunho")]
        assert connection.execute(
            sa.text(
                "SELECT loja_id IS NOT NULL FROM meta_pixel_config "
                "WHERE loja_slug = 'loja-demo'"
            )
        ).scalar_one()
        assert connection.execute(
            sa.text(
                "SELECT loja_id IS NOT NULL FROM campanhas "
                "WHERE loja_slug = 'loja-dois'"
            )
        ).scalar_one()

        from app.control.backfill import backfill_lojas_confirmadas

        backfill_lojas_confirmadas(connection, ["loja-demo", "loja-nova"])
        backfill_lojas_confirmadas(connection, ["loja-demo", "loja-nova"])
        assert connection.execute(sa.text("SELECT count(*) FROM lojas")).scalar_one() == 3

    with engine.begin() as connection:
        loja_id = connection.execute(
            sa.text("SELECT id FROM lojas WHERE slug = 'loja-demo'")
        ).scalar_one()
        for gestor_id in ("gestor-1", "gestor-2"):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO gestores_revy (
                        id, email, nome, senha_hash, papel, ativo, criado_em
                    ) VALUES (
                        :id, :email, :nome, 'hash', 'gestor', 1, :agora
                    )
                    """
                ),
                {
                    "id": gestor_id,
                    "email": f"{gestor_id}@revy.local",
                    "nome": gestor_id,
                    "agora": agora,
                },
            )
        connection.execute(
            sa.text(
                """
                INSERT INTO vinculos_trafego (
                    id, loja_id, gestor_id, tipo, iniciado_em, encerrado_em
                ) VALUES (
                    'vinculo-1', :loja_id, 'gestor-1', 'responsavel', :agora, NULL
                )
                """
            ),
            {"loja_id": loja_id, "agora": agora},
        )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO vinculos_trafego (
                        id, loja_id, gestor_id, tipo, iniciado_em, encerrado_em
                    ) VALUES (
                        'vinculo-2', :loja_id, 'gestor-2',
                        'responsavel', :agora, NULL
                    )
                    """
                ),
                {"loja_id": loja_id, "agora": agora},
            )

    encerrado_em = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE vinculos_trafego
                SET encerrado_em = :encerrado_em
                WHERE id = 'vinculo-1'
                """
            ),
            {"encerrado_em": encerrado_em},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO vinculos_trafego (
                    id, loja_id, gestor_id, tipo, iniciado_em, encerrado_em
                ) VALUES (
                    'vinculo-2', :loja_id, 'gestor-2',
                    'responsavel', :agora, NULL
                )
                """
            ),
            {"loja_id": loja_id, "agora": encerrado_em},
        )
        assert connection.execute(
            sa.text(
                "SELECT count(*) FROM vinculos_trafego WHERE loja_id = :loja_id"
            ),
            {"loja_id": loja_id},
        ).scalar_one() == 2
