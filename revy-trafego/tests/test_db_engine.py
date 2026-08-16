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
