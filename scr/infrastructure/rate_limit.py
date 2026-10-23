"""Per-IP fixed-window limiter with a Redis shared counter when configured."""
from __future__ import annotations

import threading
import time
from typing import Any


class RequestRateLimiter:
    def __init__(self, redis_url: str = "") -> None:
        self.redis_url = redis_url
        self._redis: Any | None = None
        self._memory: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def ping_backend(self) -> bool | None:
        """Return None when Redis is not configured, otherwise its availability."""
        if not self.redis_url:
            return None
        try:
            if self._redis is None:
                import redis
                self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True,
                    socket_connect_timeout=1, socket_timeout=1)
            self._redis.ping()
            return True
        except Exception:
            self._redis = None
            return False

    def allow(self, scope: str, identity: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        current = time.time() if now is None else now
        window = int(current // 60)
        retry_after = max(1, 60 - int(current % 60))
        key = f"product-research:rate:{scope}:{identity}:{window}"
        if self.redis_url:
            try:
                if self._redis is None:
                    import redis
                    self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
                count = int(self._redis.incr(key))
                if count == 1:
                    self._redis.expire(key, 65)
                return count <= limit, retry_after
            except Exception:
                self._redis = None
        with self._lock:
            count, old_window = self._memory.get(key, (0, window))
            count = count + 1 if old_window == window else 1
            self._memory[key] = (count, window)
            if len(self._memory) > 10000:
                self._memory = {item_key: value for item_key, value in self._memory.items() if value[1] >= window - 1}
            return count <= limit, retry_after
