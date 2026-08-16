"""Serialização por loja que funciona nos dois engines.

Em Postgres é um advisory lock de transação: liberado no commit ou no rollback,
sem tabela, sem linha, sem risco de vazar lock se o processo morrer. Em SQLite é
no-op — que é exatamente o comportamento de hoje, então nada regride enquanto o
banco for arquivo.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text


def _chave(nome: str) -> int:
    """int64 estável a partir do nome do escopo.

    ``blake2b`` e não ``hash()``: hash de str é randomizado por processo via
    PYTHONHASHSEED, então dois workers gerariam chaves diferentes para a mesma
    loja e a trava não travaria nada — falhando em silêncio, que é o pior modo
    de falha que uma trava pode ter.
    """
    digest = hashlib.blake2b(nome.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def travar_por_loja(db, loja_slug: str, escopo: str) -> None:
    """Serializa, por loja e por escopo, até o fim da transação atual.

    A trava é por loja: uma loja lenta não bloqueia as outras. Ela é mantida até
    o commit/rollback da transação de quem chamou — se essa transação inclui uma
    chamada de rede, a trava dura a chamada. Isso é intencional onde é usada
    (ver ``acoes._checar_rate_limit``), mas é a razão de ela não ser um utilitário
    de uso geral.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:chave)"),
        {"chave": _chave(f"{escopo}:{loja_slug}")},
    )
