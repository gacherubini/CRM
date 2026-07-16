"""Lifecycle de workers sob demanda (Fly Machines).

Plano 2026-07-14 Fase 4: só a API/orquestrador chama start; workers não recebem
token Fly. Allowlist = ``worker_slots.fly_machine_id`` no banco.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app import config

log = logging.getLogger("motor-lifecycle")


class WorkerLifecycle(Protocol):
    def start(self, machine_id: str) -> bool:
        """Inicia Machine. True se aceito/idempotente; False se falhou."""
        ...

    def stop(self, machine_id: str) -> bool:
        """Para Machine (opcional; idle exit do processo já basta)."""
        ...


@dataclass
class FakeLifecycle:
    """Para testes: registra starts sem rede."""

    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    fail_ids: set[str] = field(default_factory=set)
    # Simula rate limit / indisponibilidade global
    disponivel: bool = True

    def start(self, machine_id: str) -> bool:
        if not self.disponivel or machine_id in self.fail_ids:
            return False
        self.started.append(machine_id)
        return True

    def stop(self, machine_id: str) -> bool:
        if not self.disponivel or machine_id in self.fail_ids:
            return False
        self.stopped.append(machine_id)
        return True


class FlyMachinesLifecycle:
    """Cliente HTTP da Machines API (start/stop idempotentes)."""

    def __init__(
        self,
        *,
        token: str | None = None,
        app_name: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        allowlist: set[str] | None = None,
        client: httpx.Client | None = None,
    ):
        self.token = (token if token is not None else config.FLY_API_TOKEN) or ""
        self.app_name = app_name or config.FLY_APP_NAME
        self.base_url = (base_url or config.FLY_API_BASE).rstrip("/")
        self.timeout = timeout if timeout is not None else config.FLY_START_TIMEOUT_SECONDS
        self.allowlist = allowlist
        self._client = client
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _permitido(self, machine_id: str) -> bool:
        mid = (machine_id or "").strip()
        if not mid:
            return False
        if self.allowlist is not None and mid not in self.allowlist:
            log.warning("start recusado: machine_id fora da allowlist")
            return False
        return True

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def start(self, machine_id: str) -> bool:
        if not self.token:
            log.warning("FLY_API_TOKEN ausente; não é possível acordar worker")
            return False
        if not self._permitido(machine_id):
            return False
        url = f"{self.base_url}/v1/apps/{self.app_name}/machines/{machine_id}/start"
        try:
            resp = self._http().post(url, headers=self._headers())
        except httpx.HTTPError as exc:
            log.warning("fly start falhou (rede): %s", type(exc).__name__)
            return False
        # 200/204 ok; 400/409 machine already started = idempotente ok
        if resp.status_code in (200, 202, 204):
            return True
        if resp.status_code in (400, 409):
            corpo = (resp.text or "")[:120].lower()
            if "already" in corpo or "started" in corpo or "running" in corpo:
                return True
            log.warning("fly start status=%s", resp.status_code)
            return False
        log.warning("fly start status=%s", resp.status_code)
        return False

    def stop(self, machine_id: str) -> bool:
        if not self.token or not self._permitido(machine_id):
            return False
        url = f"{self.base_url}/v1/apps/{self.app_name}/machines/{machine_id}/stop"
        try:
            resp = self._http().post(url, headers=self._headers())
        except httpx.HTTPError:
            return False
        return resp.status_code in (200, 202, 204, 400, 409)


class RateLimitedLifecycle:
    """Envolve outro lifecycle com semáforo de burst (thread-safe, sem sleep em série)."""

    def __init__(
        self,
        inner: WorkerLifecycle,
        *,
        burst: int | None = None,
        window_seconds: float = 2.0,
    ):
        import threading

        self.inner = inner
        self.burst = max(1, burst if burst is not None else config.FLY_START_BURST)
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()
        self._sem = threading.Semaphore(self.burst)

    def start(self, machine_id: str) -> bool:
        self._sem.acquire()
        try:
            with self._lock:
                agora = time.monotonic()
                self._timestamps = [
                    t for t in self._timestamps if agora - t < self.window_seconds
                ]
            ok = self.inner.start(machine_id)
            if ok:
                with self._lock:
                    self._timestamps.append(time.monotonic())
            return ok
        finally:
            self._sem.release()

    def stop(self, machine_id: str) -> bool:
        return self.inner.stop(machine_id)


def lifecycle_padrao(
    allowlist: set[str] | None = None,
) -> WorkerLifecycle:
    """Produção: Fly se houver token; senão fake no-op (starts sempre False)."""
    if config.FLY_API_TOKEN:
        fly = FlyMachinesLifecycle(allowlist=allowlist)
        return RateLimitedLifecycle(fly)
    return FakeLifecycle(disponivel=False)
