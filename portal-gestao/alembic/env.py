from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db import Base, normalizar_database_url
from app import models  # noqa: F401

config = context.config
# A URL crua NÃO serve aqui, e o alembic roda no boot (`entrypoint-app.sh`, com
# `set -euo pipefail`) antes do app:
#   1. normalizar: o Fly emite `postgres://`, que o SQLAlchemy resolve para
#      psycopg2 — que não está instalado. O app normaliza e sobe; sem isto o
#      alembic morria com ModuleNotFoundError e a máquina entrava em
#      crash-loop levando os seis serviços do container junto.
#   2. escapar `%`: `set_main_option` passa por ConfigParser, que interpola
#      `%`. Uma senha URL-encoded (`%40`, `%2F` — o que `openssl rand -base64`
#      costuma gerar) mataria o boot com InterpolationSyntaxError.
# Nesta ordem: normalizar vê a URL de verdade, o escape é a última coisa antes
# do ConfigParser.
DATABASE_URL = normalizar_database_url(settings.database_url).replace("%", "%%")
config.set_main_option("sqlalchemy.url", DATABASE_URL)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
