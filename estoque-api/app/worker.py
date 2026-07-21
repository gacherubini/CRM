"""Worker operacional: entrega a outbox e limpa mídias órfãs periodicamente.

Uso: ``python -m app.worker``. Intervalo via ``ESTOQUE_OUTBOX_INTERVALO`` (segundos, padrão 5).
A limpeza usa ``ESTOQUE_MEDIA_CLEANUP_INTERVAL_SECONDS`` (padrão 6 horas),
sempre respeita a carência e é desativada quando a base pública não está configurada.
"""
import logging
import os
import time

from app import config, servico
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


def limpar_midias_uma_vez() -> dict:
    db = SessionLocal()
    try:
        return servico.limpar_midias_orfas(db, aplicar=True)
    finally:
        db.close()


def executar_limpeza_se_devida(
    agora: float,
    proxima_execucao: float,
    intervalo: float,
    limpador=None,
) -> tuple[float, dict | None]:
    """Executa no máximo uma limpeza por intervalo e nunca propaga sua falha."""
    if intervalo <= 0 or agora < proxima_execucao:
        return proxima_execucao, None
    proxima_execucao = agora + intervalo
    try:
        resumo = (limpador or limpar_midias_uma_vez)()
    except Exception:
        log.exception("falha na limpeza periódica de mídias")
        return proxima_execucao, None
    return proxima_execucao, resumo


def main() -> None:
    intervalo = float(os.getenv("ESTOQUE_OUTBOX_INTERVALO", "5"))
    timeout = float(os.getenv("ESTOQUE_OUTBOX_TIMEOUT", "10"))
    intervalo_limpeza = float(config.MEDIA_CLEANUP_INTERVAL_SECONDS)
    proxima_limpeza = 0.0
    poster = poster_httpx(timeout=timeout)
    log.info(
        "iniciado (outbox=%ss, timeout=%ss, limpeza_midias=%ss)",
        intervalo,
        timeout,
        intervalo_limpeza,
    )
    while True:
        try:
            resumo = rodar_uma_vez(poster)
            if any(resumo.values()):
                log.info("lote: %s", resumo)
        except Exception:  # nunca deixa o loop morrer
            log.exception("falha ao processar lote da outbox")
        proxima_limpeza, resumo_limpeza = executar_limpeza_se_devida(
            time.monotonic(),
            proxima_limpeza,
            intervalo_limpeza,
        )
        if resumo_limpeza is not None:
            log.info("limpeza de mídias: %s", resumo_limpeza)
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
