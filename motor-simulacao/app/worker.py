"""Worker do Motor (Plano #1A Task 6 + workers sob demanda).

Uso: ``python -m app.worker``.

Modos:
- **Always-on** (padrão): loop infinito, processa jobs/tarefas.
- **On-demand** (``MOTOR_WORKER_ON_DEMAND=1`` ou ``MOTOR_WORKER_PROVEDOR``):
  drena a fila do provedor, espera idle grace e **sai 0** para a Machine parar
  (restart policy ``on-failure``).
"""
from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

from app import config
from app.db import SessionLocal
from app.processamento import processar_proximo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s motor-worker %(message)s",
)
log = logging.getLogger("motor-worker")

_encerrar = False


def _handle_signal(signum, frame) -> None:
    global _encerrar
    log.info("sinal %s recebido; encerrando após a rodada", signum)
    _encerrar = True


def _limpar_screenshots_expirados() -> int:
    """Remove prints com PII após a retenção configurada; nunca segue symlinks."""
    dias = max(1, config.SCREENSHOT_RETENTION_DAYS)
    limite = time.time() - (dias * 86400)
    raiz = Path(config.SCREENSHOT_DIR)
    if not raiz.is_dir():
        return 0
    removidos = 0
    for arquivo in raiz.rglob("*.png"):
        try:
            if arquivo.is_symlink() or arquivo.stat().st_mtime >= limite:
                continue
            arquivo.unlink()
            removidos += 1
        except OSError:
            continue
    return removidos


def _uma_rodada() -> int:
    """Drena a fila numa rodada; retorna quantos itens processou."""
    db = SessionLocal()
    processados = 0
    try:
        while not _encerrar:
            sim = processar_proximo(db)
            if sim is None:
                break
            processados += 1
            log.info("job %s -> %s", sim.id, sim.status)
    finally:
        db.close()
    return processados


def main() -> int:
    intervalo = float(os.getenv("MOTOR_WORKER_INTERVALO", "2"))
    on_demand = bool(config.WORKER_ON_DEMAND)
    idle_stop = max(0, int(config.WORKER_IDLE_STOP_SECONDS)) if on_demand else 0
    provedor = config.WORKER_PROVEDOR or "*"

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_signal)

    log.info(
        "iniciado (intervalo=%ss on_demand=%s provedor=%s idle_stop=%ss fanout=%s)",
        intervalo,
        on_demand,
        provedor,
        idle_stop,
        config.FANOUT_ENABLED,
    )
    removidos = _limpar_screenshots_expirados()
    if removidos:
        log.info("prints expirados removidos=%s", removidos)
    proxima_limpeza = time.monotonic() + 3600
    ocioso_desde: float | None = None

    while not _encerrar:
        try:
            n = _uma_rodada()
        except Exception as exc:  # nunca deixa o loop morrer em always-on
            trecho = str(exc).replace("\n", " ")[:160]
            log.error(
                "falha ao processar rodada (tipo=%s): %s",
                type(exc).__name__,
                trecho,
            )
            n = 0
            if on_demand:
                # Em on-demand, erro persistente ainda permite idle exit
                pass

        if n > 0:
            ocioso_desde = None
        elif on_demand and idle_stop > 0:
            agora = time.monotonic()
            if ocioso_desde is None:
                ocioso_desde = agora
                log.info("fila vazia; idle grace %ss", idle_stop)
            elif agora - ocioso_desde >= idle_stop:
                log.info("idle grace esgotado; saindo 0 (worker dorme)")
                return 0

        if time.monotonic() >= proxima_limpeza:
            _limpar_screenshots_expirados()
            proxima_limpeza = time.monotonic() + 3600

        if _encerrar:
            break
        time.sleep(intervalo)

    log.info("encerrado limpo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
