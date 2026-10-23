from __future__ import annotations

import json
from typing import Any

class RedisTTLCache:
    """JSON-backed Redis cache implementing the shared cache port."""

    backend = "redis"

    def __init__(self, url: str, namespace: str = "product-research:", client: Any | None = None) -> None:
        if client is None:
            import redis
            client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=3)
        self.client = client
        self.namespace = namespace
        self.client.ping()

    def _key(self, key: str) -> str:
        return f"{self.namespace}{key}"

    def get(self, key: str) -> Any | None:
        value = self.client.get(self._key(key))
        if value is None:
            return None
        self.client.incr(f"{self.namespace}__hits")
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            self.client.delete(self._key(key))
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        self.client.set(self._key(key), encoded, ex=max(1, ttl_seconds))

    def set_if_absent(self, key: str, value: Any, ttl_seconds: int) -> bool:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        return bool(self.client.set(self._key(key), encoded, ex=max(1, ttl_seconds), nx=True))

    def delete(self, key: str) -> None:
        self.client.delete(self._key(key))

    def clear(self) -> None:
        cursor = 0
        while True:
            cursor, keys = self.client.scan(cursor=cursor, match=f"{self.namespace}*", count=500)
            if keys:
                self.client.delete(*keys)
            if cursor == 0:
                break

    def stats(self) -> dict[str, int]:
        cursor = 0
        entries = 0
        while True:
            cursor, keys = self.client.scan(cursor=cursor, match=f"{self.namespace}*", count=500)
            entries += sum(1 for key in keys if key != f"{self.namespace}__hits")
            if cursor == 0:
                break
        return {"entries": entries, "hits": int(self.client.get(f"{self.namespace}__hits") or 0)}
