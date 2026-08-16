"""Conexão do Portal. SQLite nos testes e no dev; Postgres (schema `portal`) em produção."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

SCHEMA = "portal"


def normalizar_database_url(url: str) -> str:
    """Aponta para o driver que está instalado.

    O Fly emite `postgres://`; SQLAlchemy 2 resolve tanto `postgres://` quanto
    `postgresql://` para psycopg2, e o que está no requirements é
    `psycopg[binary]==3.*`. Sem isto o boot morre com ModuleNotFoundError.
    """
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url.removeprefix(prefixo)
    return url


def montar_kwargs(url: str, *, schema: str) -> dict:
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return kwargs
    return {
        # search_path: o default é `"$user", public`. Com `public` vazio e sem
        # permissão de criar, errar aqui falha alto — mas não dependa só disso.
        # timezone=UTC: o container roda com TZ=America/Sao_Paulo; se algum
        # caminho mandar datetime naive, o Postgres o interpreta no fuso da
        # sessão e o valor desloca 3h sem erro nenhum.
        "connect_args": {"options": f"-csearch_path={schema} -ctimezone=UTC"},
        # O Fly Proxy encerra conexão ociosa (mesmo motivo de chatbot/app/db.py).
        "pool_pre_ping": True,
        "pool_recycle": 300,
        # 1 GB de RAM no app2037 com seis serviços no mesmo container, e o
        # suite-pg é shared-1x/512 MB. Pool curto de propósito.
        "pool_size": 5,
        "max_overflow": 5,
    }


DATABASE_URL = normalizar_database_url(settings.database_url)
engine = create_engine(
    DATABASE_URL, future=True, **montar_kwargs(DATABASE_URL, schema=SCHEMA)
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
