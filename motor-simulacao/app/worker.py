"""Worker do Motor (Plano #1A, Task 6): em loop, reserva e processa jobs da fila.

Uso: ``python -m app.worker``. Intervalo via ``MOTOR_WORKER_INTERVALO`` (segundos, padrão 2).
Precisa de ``DATABASE_URL`` e ``MOTOR_ENCRYPTION_KEY`` no ambiente.
"""
import logging
import os
import time

from app.db import SessionLocal
from app.processamento import processar_proximo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s motor-worker %(message)s")
log = logging.getLogger("motor-worker")


def _uma_rodada() -> int:
    """Drena a fila numa rodada; retorna quantos jobs processou."""
    db = SessionLocal()
    processados = 0
    try:
        while True:
            sim = processar_proximo(db)
            if sim is None:
                break
            processados += 1
            log.info("job %s -> %s", sim.id, sim.status)
    finally:
        db.close()
    return processados


def main() -> None:
    intervalo = float(os.getenv("MOTOR_WORKER_INTERVALO", "2"))
    log.info("iniciado (intervalo=%ss)", intervalo)
    while True:
        try:
            _uma_rodada()
        except Exception as exc:  # nunca deixa o loop morrer
            # Exceções externas podem conter PII; registre somente o tipo sanitizado.
            log.error("falha ao processar rodada (tipo=%s)", type(exc).__name__)
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
