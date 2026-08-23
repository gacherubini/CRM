"""Acha os arquivos do PROJETO, nunca os das dependencias."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PRODUTOS: tuple[str, ...] = (
    "chatbot-api",
    "portal-gestao",
    "motor-simulacao",
    "estoque-api",
    "revy-trafego",
    "catalogo-publico",
)

# O mapa tambem se alimenta de fora dos produtos: `cruzamentos.n8n_costura` le
# `n8n/workflow-*.json` e `cruzamentos.fly_tomls` varre os `fly.toml` do repo.
# Enquanto o frescor olhava so PRODUTOS, mexer no workflow do n8n nunca acendia
# luz nenhuma — e a secao n8n x chatbot e, pelo comentario do proprio
# cruzamentos.py, "a junta de maior severidade do repo: quando abre, o bot
# emudece". Achado no ensaio cego de 23/08.
FONTES_DO_MAPA: tuple[str, ...] = PRODUTOS + ("n8n", "deploy")

IGNORADOS: frozenset[str] = frozenset({
    ".venv", "__pycache__", "node_modules", ".git",
    ".pytest_cache", ".pytest-tmp", "graphify-out", ".mypy_cache",
})


@dataclass(frozen=True)
class Entrada:
    secao: str
    chave: str
    simbolo: str
    arquivo: str
    linha: int


def raiz_repo() -> Path:
    """Sobe de .claude/skills/revy-research/ ate a raiz do repo."""
    return Path(__file__).resolve().parents[3]


def _ignorado(caminho: Path, base: Path) -> bool:
    for parte in caminho.relative_to(base).parts:
        if parte in IGNORADOS or parte.startswith("test-tmp"):
            return True
    return False


def arquivos_py(raiz: Path, produto: str) -> list[Path]:
    base = raiz / produto
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.rglob("*.py")
        if p.is_file() and not _ignorado(p, base)
    )
