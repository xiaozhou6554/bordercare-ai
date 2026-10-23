"""Application use case for running a persisted research task through the Agent."""
from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from scr.application.agent import ResearchAgent
from scr.domain.ports import SessionMemoryPort


def scope_session_id(session_id: str, actor: dict[str, Any] | None, auth_enabled: bool) -> str:
    if not auth_enabled or not actor:
        return session_id
    return f"{actor['organization_id']}:{actor['user_id']}:{session_id}"


class ResearchTaskProcessor:
    """Coordinates the Agent and session-memory port; queue persistence is outside this use case."""

    def __init__(self, agent: ResearchAgent, memory: SessionMemoryPort, auth_enabled: bool = False) -> None:
        self.agent, self.memory, self.auth_enabled = agent, memory, auth_enabled

    def __call__(self, body: dict[str, Any], actor: dict[str, Any] | None,
                 on_event: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        public_session_id = body.get("session_id") or str(uuid4())
        session_id = scope_session_id(public_session_id, actor, self.auth_enabled)
        previous = self.memory.load(session_id)
        result: dict[str, Any] = {}
        for event in self.agent.stream(body["message"], body.get("marketplace", "US"), body.get("intent"),
                                       body.get("params", {}), session_id, previous["messages"]):
            on_event(event)
            if event.get("type") == "complete":
                result = event["data"]
        result["session_id"] = public_session_id
        assistant_text = result.get("answer") or result.get("report_markdown") or ""
        if assistant_text:
            self.memory.save_turn(session_id, body["message"], str(assistant_text), body.get("marketplace", "US"))
        return result
