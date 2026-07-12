import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class InterestStore:
    def __init__(self, database_path: str):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS interest_events (
                    id TEXT PRIMARY KEY,
                    loja_slug TEXT NOT NULL,
                    veiculo_id TEXT NOT NULL,
                    ocorrido_em TEXT NOT NULL,
                    origem TEXT,
                    utm_source TEXT,
                    utm_medium TEXT,
                    utm_campaign TEXT,
                    visitante_id TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_interest_store_time "
                "ON interest_events (loja_slug, ocorrido_em)"
            )

    def ready(self) -> bool:
        try:
            self.initialize()
            with self._connect() as db:
                db.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def record(
        self,
        *,
        loja_slug: str,
        veiculo_id: str,
        visitante_id: str,
        origem: str = "",
        utm_source: str = "",
        utm_medium: str = "",
        utm_campaign: str = "",
    ) -> str:
        event_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO interest_events (
                    id, loja_slug, veiculo_id, ocorrido_em, origem,
                    utm_source, utm_medium, utm_campaign, visitante_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    loja_slug,
                    veiculo_id,
                    datetime.now(timezone.utc).isoformat(),
                    origem or None,
                    utm_source or None,
                    utm_medium or None,
                    utm_campaign or None,
                    visitante_id,
                ),
            )
        return event_id

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM interest_events").fetchone()[0])
