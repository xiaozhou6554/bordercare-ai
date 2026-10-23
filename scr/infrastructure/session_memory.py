from __future__ import annotations

from typing import Any

from scr.domain.models import utc_now
from scr.domain.ports import CachePort


class SessionMemory:
    """Stores bounded short context and a longer session archive through CachePort."""

    def __init__(self, cache: CachePort, ttl_seconds: int = 30 * 24 * 3600, short_message_limit: int = 12, archive_message_limit: int = 100) -> None:
        self.cache = cache
        self.ttl_seconds = ttl_seconds
        self.short_message_limit = short_message_limit
        self.archive_message_limit = archive_message_limit

    def load(self, session_id: str) -> dict[str, Any]:
        data = self.cache.get(self._key(session_id)) or {}
        messages = data.get("messages", []) if isinstance(data, dict) else []
        return {"messages": messages[-self.short_message_limit :], "preferences": data.get("preferences", {}) if isinstance(data, dict) else {}}

    def save_turn(self, session_id: str, user_text: str, assistant_text: str, marketplace: str) -> None:
        key = self._key(session_id)
        data = self.cache.get(key) or {"messages": [], "preferences": {}}
        messages = data.get("messages", [])
        messages.extend([
            {"role": "user", "content": user_text[:1000], "created_at": utc_now()},
            {"role": "assistant", "content": assistant_text[:12000], "created_at": utc_now()},
        ])
        data["messages"] = messages[-self.archive_message_limit :]
        data["preferences"] = {**data.get("preferences", {}), "marketplace": marketplace}
        data["updated_at"] = utc_now()
        self.cache.set(key, data, self.ttl_seconds)

    def clear(self, session_id: str) -> None:
        self.cache.delete(self._key(session_id))

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session-memory:{session_id}"
