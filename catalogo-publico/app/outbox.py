import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx

from app.events import InterestStore


Poster = Callable[[str, bytes, dict[str, str], float], tuple[int | None, str | None]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def http_poster(url: str, body: bytes, headers: dict[str, str], timeout: float):
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=timeout)
        return response.status_code, None
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def process_pending(
    store: InterestStore,
    *,
    url: str,
    token: str,
    timeout: float = 5,
    max_attempts: int = 5,
    now: datetime | None = None,
    poster: Poster = http_poster,
) -> dict[str, int]:
    """Entrega um lote. Event ID permanece estável entre tentativas."""
    summary = {"delivered": 0, "retried": 0, "discarded": 0, "not_configured": 0}
    if not url or not token:
        summary["not_configured"] = len(store.pending_outbox(now=now))
        return summary

    instant = now or _now()
    for item in store.pending_outbox(now=instant):
        body = item["payload"].encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": item["event_id"],
            "X-Event-Type": item["event_type"],
        }
        try:
            status, error = poster(url, body, headers, timeout)
        except Exception as exc:
            status, error = None, f"{type(exc).__name__}: {exc}"
        if status is not None and 200 <= status < 300:
            store.mark_delivered(item["event_id"], status, instant)
            summary["delivered"] += 1
            continue

        attempts = int(item["attempts"]) + 1
        discard = attempts >= max_attempts
        delay = min(30 * (2 ** max(attempts - 1, 0)), 3600)
        store.mark_failed(
            item["event_id"],
            error=error or f"HTTP {status}",
            status=status,
            next_attempt_at=None if discard else instant + timedelta(seconds=delay),
            discard=discard,
        )
        summary["discarded" if discard else "retried"] += 1
    return summary


class OutboxWorker:
    def __init__(self, store: InterestStore, **options):
        self.store = store
        self.options = options
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.interval = float(options.pop("interval", 5))

    def start(self) -> None:
        if not self.options.get("url") or not self.options.get("token"):
            return
        self._thread = threading.Thread(target=self._run, name="catalog-outbox", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                process_pending(self.store, **self.options)
            except Exception:
                # Uma falha transitória do banco/rede não pode matar o worker.
                pass
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=min(self.interval + 1, 10))
