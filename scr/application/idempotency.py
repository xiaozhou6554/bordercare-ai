from __future__ import annotations

import hashlib
import threading
import time
import weakref
from typing import Any, Callable
from uuid import uuid4

from scr.domain.ports import CachePort


class IdempotencyConflict(ValueError):
    pass


class IdempotencyService:
    """Replay successful API results for a caller-supplied key and same payload."""

    def __init__(self, cache: CachePort, ttl_seconds: int = 24 * 3600) -> None:
        self.cache, self.ttl_seconds = cache, ttl_seconds
        self._locks: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()
        self._guard = threading.Lock()

    def execute(self, key: str | None, fingerprint: str, callback: Callable[[], Any]) -> tuple[Any, bool]:
        if not key:
            return callback(), False
        if len(key) > 128 or not key.strip():
            raise ValueError("Idempotency-Key must contain 1 to 128 characters")
        hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
        cache_key = f"idempotency:{hashed}"
        with self._guard:
            lock = self._locks.setdefault(hashed, threading.RLock())
        with lock:
            cached = self.cache.get(cache_key)
            if cached is not None:
                if cached.get("fingerprint") != fingerprint:
                    raise IdempotencyConflict("Idempotency-Key was already used with a different request body")
                return cached["result"], True
            lock_key = f"{cache_key}:processing"
            token = str(uuid4())
            acquired = self.cache.set_if_absent(lock_key, token, 600)
            deadline = time.monotonic() + 120
            while not acquired and time.monotonic() < deadline:
                time.sleep(0.05)
                cached = self.cache.get(cache_key)
                if cached is not None:
                    if cached.get("fingerprint") != fingerprint:
                        raise IdempotencyConflict("Idempotency-Key was already used with a different request body")
                    return cached["result"], True
                acquired = self.cache.set_if_absent(lock_key, token, 600)
            if not acquired:
                raise IdempotencyConflict("A request with this Idempotency-Key is still processing; retry shortly")
            try:
                result = callback()
                self.cache.set(cache_key, {"fingerprint": fingerprint, "result": result}, self.ttl_seconds)
                return result, False
            finally:
                if self.cache.get(lock_key) == token:
                    self.cache.delete(lock_key)
