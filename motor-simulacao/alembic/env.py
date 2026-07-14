"""Ambiente Alembic do Motor de Simulação.

Usa DATABASE_URL (ou o default de app.db) e o metadata dos modelos canônicos.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app import models_db  # noqa: F401 (registra os modelos no metadata)
from app.db import DATABASE_URL, Base, normalizar_database_url

config = context.config
# Relê os.environ em vez de usar só o DATABASE_URL importado: app.db calcula essa
# constante uma única vez, no primeiro import do processo (ex.: via conftest.py nos
# testes). Se o ambiente mudar DATABASE_URL depois desse import (ex.: testes de
# migração com monkeypatch.setenv), usar o valor cacheado ignora a troca e o
# alembic acaba migrando o banco default em vez do banco isolado do teste.
# Normaliza igual ao app.db para não usar `postgres://` cru (rejeitado pelo
# SQLAlchemy 2.x) quando o Fly injeta a URL curta no deploy.
config.set_main_option(
    "sqlalchemy.url", normalizar_database_url(os.getenv("DATABASE_URL", DATABASE_URL))
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Libera o arquivo SQLite também no Windows (útil para testes/rollback).
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
