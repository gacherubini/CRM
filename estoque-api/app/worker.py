"""Worker da outbox: em loop, entrega os eventos pendentes ao webhook de cada loja.

Uso: ``python -m app.worker``. Intervalo via ``ESTOQUE_OUTBOX_INTERVALO`` (segundos, padrão 5).
Precisa de ``DATABASE_URL`` e ``ESTOQUE_OUTBOX_KEY`` no ambiente.
"""
import logging
import os
import time

from app.db import SessionLocal
from app.outbox import poster_httpx, processar_pendentes

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s outbox %(message)s"
)
log = logging.getLogger("outbox")


def rodar_uma_vez(poster) -> dict:
    db = SessionLocal()
    try:
        return processar_pendentes(db, poster)
    finally:
        db.close()


def main() -> None:
    intervalo = float(os.getenv("ESTOQUE_OUTBOX_INTERVALO", "5"))
    timeout = float(os.getenv("ESTOQUE_OUTBOX_TIMEOUT", "10"))
    poster = poster_httpx(timeout=timeout)
    log.info("iniciado (intervalo=%ss, timeout=%ss)", intervalo, timeout)
    while True:
        try:
            resumo = rodar_uma_vez(poster)
            if any(resumo.values()):
                log.info("lote: %s", resumo)
        except Exception:  # nunca deixa o loop morrer
            log.exception("falha ao processar lote da outbox")
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
