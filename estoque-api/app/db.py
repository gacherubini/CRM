"""Conexão com o banco do Estoque (Plano #4A). SQLite local; Postgres em produção."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

def normalizar_database_url(url: str) -> str:
    """Converte a URL curta emitida pelo Fly para o driver psycopg instalado."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


DATABASE_URL = normalizar_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./estoque.db")
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
