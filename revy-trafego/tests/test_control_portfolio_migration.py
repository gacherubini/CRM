from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa


APP_DIR = Path(__file__).resolve().parents[1]


def _alembic(
    database_url: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REVY_TRAFEGO_DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            *args,
        ],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_portfolio_semeia_catalogo_e_preserva_lojas(tmp_path):
    banco = tmp_path / "control-portfolio.db"
    database_url = f"sqlite:///{banco}"
    _alembic(database_url, "upgrade", "0006_revy_control_recuperacoes")

    engine = sa.create_engine(database_url)
    agora = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO lojas (
                    id, slug, nome, status, criada_em, atualizada_em
                ) VALUES (
                    'loja-portfolio', 'loja-portfolio', 'Loja Portfólio',
                    'rascunho', :agora, :agora
                )
                """
            ),
            {"agora": agora},
        )

    _alembic(database_url, "upgrade", "0007_revy_control_portfolio")

    inspector = sa.inspect(engine)
    assert {
        "modulos_revy",
        "loja_modulos",
        "contratos_loja",
    } <= set(inspector.get_table_names())
    assert {
        column["name"]
        for column in inspector.get_columns("modulos_revy")
    } == {
        "id",
        "codigo",
        "nome",
        "criado_em",
    }
    assert {
        column["name"]
        for column in inspector.get_columns("loja_modulos")
    } == {
        "id",
        "loja_id",
        "modulo_id",
        "estado",
        "versao",
        "contratado_em",
        "suspenso_em",
        "atualizado_em",
    }
    assert {
        column["name"]
        for column in inspector.get_columns("contratos_loja")
    } == {
        "id",
        "loja_id",
        "valor_mensal",
        "moeda",
        "vigencia_inicio",
        "vigencia_fim",
        "vencimento_dia",
        "situacao_cobranca",
        "estado",
        "criado_em",
        "atualizado_em",
    }

    assert {
        constraint["name"]: constraint["column_names"]
        for constraint in inspector.get_unique_constraints("modulos_revy")
    } == {
        "uq_modulos_revy_codigo": ["codigo"],
    }
    assert {
        constraint["name"]: constraint["column_names"]
        for constraint in inspector.get_unique_constraints("loja_modulos")
    } == {
        "uq_loja_modulos_loja_modulo": ["loja_id", "modulo_id"],
    }
    assert {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("modulos_revy")
    } == {
        "ck_modulos_revy_codigo": "codigo IN ('vendas', 'estoque')",
    }
    assert {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("loja_modulos")
    } == {
        "ck_loja_modulos_estado": "estado IN ('ativo', 'suspenso')",
        "ck_loja_modulos_suspensao": (
            "(estado = 'ativo' AND suspenso_em IS NULL) OR "
            "(estado = 'suspenso' AND suspenso_em IS NOT NULL)"
        ),
        "ck_loja_modulos_versao": "versao >= 1",
    }
    assert {
        check["name"]: check["sqltext"]
        for check in inspector.get_check_constraints("contratos_loja")
    } == {
        "ck_contratos_loja_estado": "estado IN ('ativo', 'encerrado')",
        "ck_contratos_loja_moeda": "moeda = 'BRL'",
        "ck_contratos_loja_situacao_cobranca": (
            "situacao_cobranca IN ('em_dia', 'atrasada', 'isenta')"
        ),
        "ck_contratos_loja_valor_mensal": "valor_mensal >= 0",
        "ck_contratos_loja_vencimento_dia": (
            "vencimento_dia BETWEEN 1 AND 31"
        ),
        "ck_contratos_loja_vigencia": (
            "vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio"
        ),
    }

    assert {
        foreign_key["name"]: (
            foreign_key["constrained_columns"],
            foreign_key["referred_table"],
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("loja_modulos")
    } == {
        "fk_loja_modulos_loja_id": (["loja_id"], "lojas", "RESTRICT"),
        "fk_loja_modulos_modulo_id": (
            ["modulo_id"],
            "modulos_revy",
            "RESTRICT",
        ),
    }
    assert {
        foreign_key["name"]: (
            foreign_key["constrained_columns"],
            foreign_key["referred_table"],
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("contratos_loja")
    } == {
        "fk_contratos_loja_loja_id": (["loja_id"], "lojas", "RESTRICT"),
    }
    assert {
        index["name"]: (
            index["column_names"],
            bool(index["unique"]),
        )
        for index in inspector.get_indexes("contratos_loja")
    } == {
        "ix_contratos_loja_loja_id": (["loja_id"], False),
        "uq_contratos_loja_ativo": (["loja_id"], True),
    }

    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                """
                SELECT id, codigo, nome
                FROM modulos_revy
                ORDER BY id
                """
            )
        ).all() == [
            ("estoque", "estoque", "Estoque"),
            ("vendas", "vendas", "Vendas"),
        ]
        assert connection.execute(
            sa.text(
                """
                SELECT slug, nome, status
                FROM lojas
                WHERE id = 'loja-portfolio'
                """
            )
        ).one() == (
            "loja-portfolio",
            "Loja Portfólio",
            "rascunho",
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO loja_modulos (
                    id, loja_id, modulo_id, estado,
                    contratado_em, suspenso_em, atualizado_em
                ) VALUES (
                    'loja-modulo-vendas', 'loja-portfolio', 'vendas', 'ativo',
                    :agora, NULL, :agora
                )
                """
            ),
            {"agora": agora},
        )
        assert connection.execute(
            sa.text(
                """
                SELECT versao
                FROM loja_modulos
                WHERE id = 'loja-modulo-vendas'
                """
            )
        ).scalar_one() == 1
        connection.execute(
            sa.text(
                """
                INSERT INTO contratos_loja (
                    id, loja_id, valor_mensal, vigencia_inicio,
                    vigencia_fim, vencimento_dia, situacao_cobranca,
                    estado, criado_em, atualizado_em
                ) VALUES (
                    'contrato-ativo', 'loja-portfolio', :valor,
                    :vigencia_inicio, NULL, 10, 'em_dia',
                    'ativo', :agora, :agora
                )
                """
            ),
            {
                "valor": 199.90,
                "vigencia_inicio": date(2026, 7, 1),
                "agora": agora,
            },
        )
        assert connection.execute(
            sa.text(
                """
                SELECT moeda
                FROM contratos_loja
                WHERE id = 'contrato-ativo'
                """
            )
        ).scalar_one() == "BRL"

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO loja_modulos (
                        id, loja_id, modulo_id, estado, versao,
                        contratado_em, suspenso_em, atualizado_em
                    ) VALUES (
                        'loja-modulo-incoerente', 'loja-portfolio',
                        'estoque', 'ativo', 1, :agora, :suspenso_em, :agora
                    )
                    """
                ),
                {
                    "agora": agora,
                    "suspenso_em": agora + timedelta(minutes=1),
                },
            )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO contratos_loja (
                        id, loja_id, valor_mensal, moeda, vigencia_inicio,
                        vigencia_fim, vencimento_dia, situacao_cobranca,
                        estado, criado_em, atualizado_em
                    ) VALUES (
                        'contrato-ativo-duplicado', 'loja-portfolio',
                        250, 'BRL', :vigencia_inicio, NULL, 15, 'em_dia',
                        'ativo', :agora, :agora
                    )
                    """
                ),
                {
                    "vigencia_inicio": date(2026, 8, 1),
                    "agora": agora,
                },
            )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO contratos_loja (
                    id, loja_id, valor_mensal, moeda, vigencia_inicio,
                    vigencia_fim, vencimento_dia, situacao_cobranca,
                    estado, criado_em, atualizado_em
                ) VALUES (
                    'contrato-encerrado', 'loja-portfolio',
                    180, 'BRL', :vigencia_inicio, :vigencia_fim,
                    20, 'isenta', 'encerrado', :agora, :agora
                )
                """
            ),
            {
                "vigencia_inicio": date(2026, 6, 1),
                "vigencia_fim": date(2026, 6, 30),
                "agora": agora,
            },
        )
        assert connection.execute(
            sa.text(
                """
                SELECT version_num
                FROM alembic_version_revy_trafego
                """
            )
        ).scalar_one() == "0007_revy_control_portfolio"
