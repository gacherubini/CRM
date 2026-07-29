"""Projeção operacional do Control e gate de vitrine pública.

Fail-open vs Chatbot/Estoque
----------------------------
Chatbot e Estoque usam **fail-closed**: ausência de projeção bloqueia efeitos.
O Catálogo Público usa **fail-open quando não há projeção da loja**, para a
vitrine continuar acessível até o Control entregar o primeiro snapshot (cutover).

Quando a projeção existe e indica loja não ``ativa`` ou módulo ``estoque``
não ``ativo`` (ausente/suspenso), a vitrine, o detalhe e o interesse respondem
404/HIDE — sem reescrever ``publicado`` nos veículos (ADR 0001).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvisioningStore:
    """Persistência SQLite da projeção operacional por ``loja_slug`` + aggregate."""

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
                CREATE TABLE IF NOT EXISTS loja_operacional_projecao (
                    loja_slug TEXT NOT NULL,
                    aggregate TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    event_id TEXT NOT NULL DEFAULT '',
                    atualizado_em TEXT NOT NULL,
                    PRIMARY KEY (loja_slug, aggregate)
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_proj_slug "
                "ON loja_operacional_projecao (loja_slug)"
            )

    def get(
        self, loja_slug: str, aggregate: str
    ) -> Optional[dict[str, Any]]:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT loja_slug, aggregate, version, state, event_id, atualizado_em
                FROM loja_operacional_projecao
                WHERE loja_slug = ? AND aggregate = ?
                """,
                (loja_slug, aggregate),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def apply_payload(
        self, loja_slug: str, payload: dict[str, Any]
    ) -> list[str]:
        """Aplica envelopes operacionais de forma monotônica e idempotente.

        - versão menor que a local → ``stale``
        - mesma versão e mesmo estado → ``idempotent``
        - demais casos → ``applied``
        """
        reasons: list[str] = []
        with self._connect() as db:
            for envelope in payload.get("operational") or []:
                if not isinstance(envelope, dict):
                    continue
                aggregate = envelope.get("aggregate")
                if not aggregate:
                    continue
                reasons.append(
                    self._apply_envelope(
                        db, loja_slug, envelope, str(aggregate)
                    )
                )
            db.commit()
        return reasons

    def allows_processing(
        self, loja_slug: str, module: str | None = None
    ) -> bool:
        """Gate de vitrine: loja ativa e módulo estoque ativo, se exigido.

        **Fail-open** se não existe projeção de loja (cutover sem Control).
        Com projeção: exige ``state == ativa``; se ``module``, exige projeção
        do módulo com ``state == ativo``.
        """
        loja = self.get(loja_slug, "loja")
        if loja is None:
            return True
        if loja["state"] != "ativa":
            return False
        if module is None:
            return True
        assigned = self.get(loja_slug, module)
        return assigned is not None and assigned["state"] == "ativo"

    def _apply_envelope(
        self,
        db: sqlite3.Connection,
        loja_slug: str,
        envelope: dict[str, Any],
        aggregate: str,
    ) -> str:
        version = int(envelope.get("version") or 0)
        state = str(envelope.get("state") or "")
        event_id = str(envelope.get("event_id") or "")
        now = _now_iso()

        existing = db.execute(
            """
            SELECT version, state FROM loja_operacional_projecao
            WHERE loja_slug = ? AND aggregate = ?
            """,
            (loja_slug, aggregate),
        ).fetchone()

        if existing is not None:
            if int(existing["version"]) > version:
                return "stale"
            if int(existing["version"]) == version and existing["state"] == state:
                return "idempotent"
            db.execute(
                """
                UPDATE loja_operacional_projecao
                SET version = ?, state = ?, event_id = ?, atualizado_em = ?
                WHERE loja_slug = ? AND aggregate = ?
                """,
                (version, state, event_id, now, loja_slug, aggregate),
            )
            return "applied"

        db.execute(
            """
            INSERT INTO loja_operacional_projecao
                (loja_slug, aggregate, version, state, event_id, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (loja_slug, aggregate, version, state, event_id, now),
        )
        return "applied"
