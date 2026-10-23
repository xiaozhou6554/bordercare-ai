from __future__ import annotations

import threading
import time
from typing import Any


class MemoryTTLCache:
    """Thread-safe process-local cache with lazy expiry and hit counters."""
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._hits = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + max(0, ttl_seconds), value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def set_if_absent(self, key: str, value: Any, ttl_seconds: int) -> bool:
        with self._lock:
            item = self._items.get(key)
            if item is not None and item[0] > time.monotonic():
                return False
            self._items[key] = (time.monotonic() + max(1, ttl_seconds), value)
            return True

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._hits = 0

    def stats(self) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            expired = [key for key, (deadline, _) in self._items.items() if deadline <= now]
            for key in expired:
                self._items.pop(key, None)
            return {"entries": len(self._items), "hits": self._hits}
