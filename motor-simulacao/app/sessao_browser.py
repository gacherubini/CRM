"""Warm session + batch 2 — paths de storage_state e classificação de driver browser.

Plano: docs/plans/2026-07-17-plano1a-warm-session-batch2.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app import config

# Segmento de path: evita path traversal e caracteres estranhos no volume.
_SEG_OK = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitizar_segmento(valor: str, *, fallback: str = "x") -> str:
    """Normaliza cliente_id/provedor para uso em nome de arquivo/diretório."""
    s = _SEG_OK.sub("_", (valor or "").strip())[:80]
    s = s.strip("._") or fallback
    if s in {".", ".."}:
        return fallback
    return s


def path_storage_state(cliente_id: str | None, provedor: str) -> Path:
    """Path canônico: ``{STORAGE}/{cliente_id}/{provedor}.json``.

    Se o canônico ainda não existe, mas o legado ``{STORAGE}/{provedor}.json``
    existir, devolve o legado **para leitura** (migração suave). Gravações novas
    devem preferir ``path_storage_state_gravacao``.
    """
    base = Path(config.STORAGE_STATE_DIR)
    prov = sanitizar_segmento(provedor, fallback="provedor")
    if not cliente_id:
        return base / f"{prov}.json"
    cli = sanitizar_segmento(cliente_id, fallback="cliente")
    canonico = base / cli / f"{prov}.json"
    if canonico.is_file():
        return canonico
    legado = base / f"{prov}.json"
    if legado.is_file():
        return legado
    return canonico


def path_storage_state_gravacao(cliente_id: str | None, provedor: str) -> Path:
    """Sempre o path canônico (grava na árvore por cliente)."""
    base = Path(config.STORAGE_STATE_DIR)
    prov = sanitizar_segmento(provedor, fallback="provedor")
    if not cliente_id:
        return base / f"{prov}.json"
    cli = sanitizar_segmento(cliente_id, fallback="cliente")
    return base / cli / f"{prov}.json"


def sessao_parece_quente(cliente_id: str | None, provedor: str) -> bool:
    """True se existe arquivo de storage_state utilizável (não valida o portal)."""
    if not config.WARM_SESSION:
        return False
    p = path_storage_state(cliente_id, provedor)
    try:
        return p.is_file() and p.stat().st_size > 2
    except OSError:
        return False


def driver_usa_browser(driver: Any) -> bool:
    """Playwright real consome slot do semáforo; API/mock não."""
    if getattr(driver, "usa_browser", None) is True:
        return True
    if getattr(driver, "usa_browser", None) is False:
        return False
    # Instâncias de classes com atributo de classe
    cls = type(driver)
    if getattr(cls, "usa_browser", None) is True:
        return True
    try:
        from app.motor.playwright_base import PlaywrightBankDriver

        if isinstance(driver, PlaywrightBankDriver):
            return True
    except Exception:
        pass
    return False


def browser_concurrency() -> int:
    """Teto de browsers Playwright (default produto = 2)."""
    raw = getattr(config, "MAX_BROWSER_WORKERS", None)
    if raw is None:
        raw = getattr(config, "BROWSER_CONCURRENCY", 2)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 2
    return max(1, n)
