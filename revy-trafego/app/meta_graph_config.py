"""Configuração compartilhada da Meta Graph/Marketing API."""
from __future__ import annotations

import os
import re


DEFAULT_GRAPH_VERSION = "v26.0"


def _graph_version() -> str:
    """Aceita override operacional sem permitir montar uma URL arbitrária."""
    value = os.getenv("META_GRAPH_API_VERSION", DEFAULT_GRAPH_VERSION).strip()
    if re.fullmatch(r"v\d+\.\d+", value):
        return value
    return DEFAULT_GRAPH_VERSION


GRAPH_VERSION = _graph_version()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
