"""Cache TTL em processo para o fan-out caro do SalesOverview.

``build_sales_overview`` faz 3–4 round-trips HTTP em sequência e chama
``listar_leads()`` três vezes sem memoização. Três perguntas seguidas sobre o
mesmo mês fariam o fan-out três vezes.

Escopo consciente: é cache POR PROCESSO, não distribuído. TTL curto — o dono
prefere um número 60s velho a esperar 20s por ele.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

TTL_PADRAO_SEGUNDOS = 90.0


class CacheTTL:
    def __init__(
        self,
        ttl_segundos: float = TTL_PADRAO_SEGUNDOS,
        *,
        agora: Callable[[], float] = time.monotonic,
    ):
        self.ttl = float(ttl_segundos)
        self._agora = agora
        self._dados: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def tamanho(self) -> int:
        with self._lock:
            return len(self._dados)

    def obter(self, chave: str, produtor: Callable[[], Any]) -> Any:
        agora = self._agora()
        with self._lock:
            item = self._dados.get(chave)
            if item is not None and agora - item[0] < self.ttl:
                return item[1]
        # Produz fora do lock: o produtor faz I/O de segundos.
        valor = produtor()
        with self._lock:
            self._dados[chave] = (self._agora(), valor)
        return valor

    def invalidar(self, *, prefixo: str | None = None) -> None:
        with self._lock:
            if prefixo is None:
                self._dados.clear()
                return
            for chave in [k for k in self._dados if k.startswith(prefixo)]:
                self._dados.pop(chave, None)


def chave_overview(
    loja_slug: str,
    papel: str,
    inicio: str | None,
    fim: str | None,
) -> str:
    """Papel entra na chave: vendedor e dono veem escopos diferentes."""
    return f"{loja_slug}:overview:{papel}:{inicio or '-'}:{fim or '-'}"


cache_overview = CacheTTL()
