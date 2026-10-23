"""Application-facing runtime bindings injected by the infrastructure composition root."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeServices:
    identity: Any
    agent: Any
    tools: Any
    model: Any
    session_memory: Any
    idempotency: Any
    workspace: Any | None
    task_queue: Any
    rate_limiter: Any
