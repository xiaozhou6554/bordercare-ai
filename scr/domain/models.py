from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Intent:
    intent: str
    keyword: str
    marketplace: str = "US"
    additional_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolOutput:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchReport:
    keyword: str
    marketplace: str
    intent: Intent
    stages: dict[str, ToolOutput]
    report_markdown: str
    aborted: bool = False
    abort_reason: str | None = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "marketplace": self.marketplace,
            "intent": asdict(self.intent),
            "stages": {key: value.to_dict() for key, value in self.stages.items()},
            "report_markdown": self.report_markdown,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "created_at": self.created_at,
        }


@dataclass
class AgentMessage:
    role: str
    content: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class AgentTask:
    task_id: str = field(default_factory=lambda: str(uuid4()))
    user_input: str = ""
    intent: str = "qna"
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None


@dataclass
class AgentState:
    """Request-scoped conversational and workflow state; deliberately not persisted."""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_input: str = ""
    messages: list[AgentMessage] = field(default_factory=list)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    watchlist: list[str] = field(default_factory=list)
    cache_state: dict[str, Any] = field(default_factory=dict)
    current_task: AgentTask | None = None
    task_history: list[AgentTask] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
