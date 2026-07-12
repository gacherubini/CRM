import sqlite3
import base64
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_reference() -> str:
    token = base64.b32encode(secrets.token_bytes(8)).decode("ascii").rstrip("=")
    return f"CAT-{token}"


@dataclass(frozen=True)
class InterestRecord:
    id: str
    event_id: str
    public_ref: str
    payload: dict


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
                    event_id TEXT NOT NULL UNIQUE,
                    public_ref TEXT NOT NULL UNIQUE,
                    loja_slug TEXT NOT NULL,
                    veiculo_id TEXT NOT NULL,
                    ocorrido_em TEXT NOT NULL,
                    origem TEXT,
                    utm_source TEXT,
                    utm_medium TEXT,
                    utm_campaign TEXT,
                    utm_content TEXT,
                    utm_term TEXT,
                    visitante_id TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(interest_events)")}
            for name in ("event_id", "public_ref", "utm_content", "utm_term"):
                if name not in columns:
                    db.execute(f"ALTER TABLE interest_events ADD COLUMN {name} TEXT")
            legacy = db.execute(
                "SELECT id FROM interest_events WHERE event_id IS NULL OR public_ref IS NULL"
            ).fetchall()
            for row in legacy:
                db.execute(
                    "UPDATE interest_events SET event_id = ?, public_ref = ? WHERE id = ?",
                    (str(uuid.uuid4()), _public_reference(), row[0]),
                )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_interest_event_id ON interest_events(event_id)"
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_interest_public_ref ON interest_events(public_ref)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_interest_store_time "
                "ON interest_events (loja_slug, ocorrido_em)"
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS event_outbox (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error TEXT,
                    last_http_status INTEGER,
                    delivered_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_event_outbox_pending "
                "ON event_outbox(status, next_attempt_at, created_at)"
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
        utm_content: str = "",
        utm_term: str = "",
    ) -> InterestRecord:
        event_id = str(uuid.uuid4())
        interest_id = str(uuid.uuid4())
        public_ref = _public_reference()
        occurred_at = _now().isoformat()
        payload = {
            "event_id": event_id,
            "event_type": "catalog.interest_clicked",
            "occurred_at": occurred_at,
            "loja_slug": loja_slug,
            "catalog_interest_ref": public_ref,
            "veiculo_ref": veiculo_id,
            "origem": "catalogo_publico",
            "canal": "whatsapp",
            "utm_source": utm_source or None,
            "utm_medium": utm_medium or None,
            "utm_campaign": utm_campaign or None,
            "utm_content": utm_content or None,
            "utm_term": utm_term or None,
        }
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO interest_events (
                    id, event_id, public_ref, loja_slug, veiculo_id, ocorrido_em, origem,
                    utm_source, utm_medium, utm_campaign, utm_content, utm_term, visitante_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interest_id,
                    event_id,
                    public_ref,
                    loja_slug,
                    veiculo_id,
                    occurred_at,
                    origem or None,
                    utm_source or None,
                    utm_medium or None,
                    utm_campaign or None,
                    utm_content or None,
                    utm_term or None,
                    visitante_id,
                ),
            )
            db.execute(
                """
                INSERT INTO event_outbox (
                    event_id, event_type, payload, status, attempts, created_at
                ) VALUES (?, 'catalog.interest_clicked', ?, 'pending', 0, ?)
                """,
                (event_id, json.dumps(payload, ensure_ascii=False, sort_keys=True), occurred_at),
            )
        return InterestRecord(
            id=interest_id, event_id=event_id, public_ref=public_ref, payload=payload
        )

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM interest_events").fetchone()[0])

    def get_interest(self, event_id: str) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute(
                "SELECT * FROM interest_events WHERE event_id = ?", (event_id,)
            ).fetchone()

    def pending_outbox(self, now: datetime | None = None, limit: int = 50) -> list[sqlite3.Row]:
        instant = (now or _now()).isoformat()
        with self._connect() as db:
            return db.execute(
                """
                SELECT * FROM event_outbox
                WHERE status = 'pending'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at ASC LIMIT ?
                """,
                (instant, limit),
            ).fetchall()

    def mark_delivered(self, event_id: str, status: int, now: datetime | None = None) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE event_outbox
                SET status='delivered', attempts=attempts+1, delivered_at=?,
                    last_http_status=?, last_error=NULL, next_attempt_at=NULL
                WHERE event_id=?
                """,
                ((now or _now()).isoformat(), status, event_id),
            )

    def mark_failed(
        self,
        event_id: str,
        *,
        error: str,
        status: int | None,
        next_attempt_at: datetime | None,
        discard: bool,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE event_outbox
                SET status=?, attempts=attempts+1, next_attempt_at=?,
                    last_error=?, last_http_status=?
                WHERE event_id=?
                """,
                (
                    "discarded" if discard else "pending",
                    next_attempt_at.isoformat() if next_attempt_at else None,
                    error[:500],
                    status,
                    event_id,
                ),
            )

    def get_outbox(self, event_id: str) -> sqlite3.Row | None:
        with self._connect() as db:
            return db.execute(
                "SELECT * FROM event_outbox WHERE event_id = ?", (event_id,)
            ).fetchone()
