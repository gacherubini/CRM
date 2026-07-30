"""Guarda o QR de pareamento fora do cookie de sessao, por tempo curto.

Motivo: o QR da Evolution e um PNG em base64 de vários KB. Na sessao de cookie
assinado do Starlette ele estoura o limite de ~4 KB do navegador, que descarta o
cookie inteiro em silencio — a loja perderia a sessao ao tentar parear. Aqui a
sessao carrega so um token opaco curto, e o payload fica em memoria do processo.

Em processo e suficiente porque o Portal roda com um unico worker uvicorn
(``Dockerfile``, ``fly.toml``, ``deploy/fly/3vm/run-portal.sh``). Se algum dia
passar a rodar com varios workers, isto precisa virar armazenamento compartilhado:
o POST de conectar e o GET seguinte teriam que cair no mesmo processo.

O QR nunca e logado nem auditado — este modulo nao tem logger de proposito.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

# O QR da Evolution expira em ~60s; a folga cobre o redirect e um reload lento.
TTL_SEGUNDOS = 120


@dataclass(frozen=True)
class QrEfemero:
    canal_id: str
    payload: str


_guardados: dict[str, tuple[float, QrEfemero]] = {}


def _limpar(agora: float) -> None:
    vencidos = [t for t, (exp, _) in _guardados.items() if exp <= agora]
    for token in vencidos:
        _guardados.pop(token, None)


def guardar(canal_id: str, payload: str) -> str:
    """Guarda o QR e devolve o token opaco que vai para a sessao."""
    agora = time.monotonic()
    _limpar(agora)
    token = secrets.token_urlsafe(16)
    _guardados[token] = (agora + TTL_SEGUNDOS, QrEfemero(canal_id, payload))
    return token


def consumir(token: str | None) -> QrEfemero | None:
    """Devolve o QR e o remove. Token ausente, invalido ou vencido -> ``None``."""
    if not token:
        return None
    agora = time.monotonic()
    _limpar(agora)
    guardado = _guardados.pop(token, None)
    if guardado is None:
        return None
    expira_em, qr = guardado
    if expira_em <= agora:
        return None
    return qr
