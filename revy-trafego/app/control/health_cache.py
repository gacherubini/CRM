from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class TTLCache:
    def __init__(self, ttl_seg: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seg
        self._clock = clock
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        stamped, value = item
        if self._clock() - stamped > self._ttl:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (self._clock(), value)

    def invalidate(self, key: Any) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
