from pathlib import Path

import pytest

from app.db import montar_kwargs, normalizar_database_url


def test_normaliza_url_curta_do_fly():
    assert normalizar_database_url("postgres://u:p@h:5432/revy") == (
        "postgresql+psycopg://u:p@h:5432/revy"
    )


def test_normaliza_postgresql_sem_driver():
    """`postgresql://` resolve para psycopg2, que NAO esta instalado."""
    assert normalizar_database_url("postgresql://u:p@h:5432/revy") == (
        "postgresql+psycopg://u:p@h:5432/revy"
    )


def test_nao_mexe_em_url_ja_com_driver():
    url = "postgresql+psycopg://u:p@h:5432/revy"
    assert normalizar_database_url(url) == url


def test_nao_mexe_em_sqlite():
    assert normalizar_database_url("sqlite:///./portal.db") == "sqlite:///./portal.db"


def test_kwargs_sqlite_em_memoria_usa_staticpool():
    from sqlalchemy.pool import StaticPool

    kwargs = montar_kwargs("sqlite+pysqlite:///:memory:", schema="control")
    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert kwargs["poolclass"] is StaticPool


def test_kwargs_postgres_fixa_schema_e_utc():
    kwargs = montar_kwargs(
        "postgresql+psycopg://u:p@h:5432/revy", schema="control"
    )
    opcoes = kwargs["connect_args"]["options"]
    assert "-csearch_path=control" in opcoes
    assert "-ctimezone=UTC" in opcoes


def test_kwargs_postgres_sobrevive_ao_fly_proxy():
    kwargs = montar_kwargs(
        "postgresql+psycopg://u:p@h:5432/revy", schema="control"
    )
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
    # 1 GB de RAM no app2037, seis servicos no mesmo container: pool curto.
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 5


# --- I5/I6: o alembic do boot precisa da MESMA normalizacao que o app ---------
# `entrypoint-app.sh` roda `alembic upgrade head` com `set -euo pipefail` ANTES
# do supervisord. Se o env.py usar a URL crua, o boot morre e a maquina entra em
# crash-loop levando os seis servicos do container junto.

ENV_PY = Path(__file__).resolve().parents[1] / "alembic" / "env.py"


def test_alembic_env_normaliza_e_escapa_a_url():
    texto = ENV_PY.read_text(encoding="utf-8")
    assert "from app.db import Base, normalizar_database_url" in texto, (
        "alembic/env.py precisa importar normalizar_database_url de app.db"
    )
    assert (
        'normalizar_database_url(settings.database_url).replace("%", "%%")' in texto
    ), "alembic/env.py precisa normalizar a URL e escapar % antes do ConfigParser"
    assert 'config.set_main_option("sqlalchemy.url", DATABASE_URL)' in texto


def test_url_do_fly_com_senha_urlencoded_sobrevive_ao_configparser():
    """`set_main_option` passa por ConfigParser, que interpola `%`: uma senha
    URL-encoded (`%40`, `%2F`) explode no set. E `postgres://` resolveria para
    psycopg2, que nao esta instalado."""
    from alembic.config import Config

    crua = "postgres://u:p%40ss%2Fw@h:5432/revy"
    valor = normalizar_database_url(crua).replace("%", "%%")

    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", valor)
    assert cfg.get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://u:p%40ss%2Fw@h:5432/revy"
    )

    with pytest.raises(ValueError):
        Config().set_main_option("sqlalchemy.url", crua)
