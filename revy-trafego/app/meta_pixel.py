"""Validação do identificador público do Meta Pixel."""

from __future__ import annotations

import re


_PIXEL_ID_RE = re.compile(r"^[0-9]{5,32}$")


def normalizar_pixel_id(valor: str | None) -> str:
    pixel_id = (valor or "").strip()
    return pixel_id if _PIXEL_ID_RE.fullmatch(pixel_id) else ""


def pixel_id_valido(valor: str | None) -> bool:
    return bool(normalizar_pixel_id(valor))
