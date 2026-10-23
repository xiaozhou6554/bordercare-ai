import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import scr.api  # noqa: F401 — configures the application runtime for route tests
from scr.interfaces.http import routes
from scr.interfaces.http.schemas import ResearchRequest
from tests.support import make_agent


def test_health_and_homepage() -> None:
    health = routes.health()
    assert health["status"] == "ok"
    assert "database_status" not in health
    assert "redis_status" not in health
    assert "data_sources" not in health
    assert "llm_configured" not in health
    assert not any("/providers/" in str(getattr(route, "path", "")) for route in routes.router.routes)
    assert any(getattr(route, "path", None) == "/api/research/stream" for route in routes.router.routes)
    html = (Path(__file__).parents[1] / "scr/interfaces/web/index.html").read_text(encoding="utf-8")
    assert "选品调研工作台" in html
    assert "/static/app.js" in html


def test_frontend_query_contract_and_accessible_controls() -> None:
    web_root = Path(__file__).parents[1] / "scr/interfaces/web"
    html = (web_root / "index.html").read_text(encoding="utf-8")
    script = (web_root / "app.js").read_text(encoding="utf-8")
    assert 'id="inp"' in html and 'id="send"' in html
    assert 'aria-pressed="true"' in html and '<button type="button" class="chip"' in html
    assert 'id="inp" aria-label=' in html
    assert 'fetch("/api/tasks"' in script and 'fetch(`/api/tasks/${encodeURIComponent(submitted.task_id)}`' in script
    assert 'if (!response.ok)' in script and 'catch (error)' in script


def test_readiness_failure_does_not_disclose_dependency_status(monkeypatch) -> None:
    class DownStore:
        @staticmethod
        def ping():
            raise RuntimeError("db down")

    monkeypatch.setattr(routes, "persistence", DownStore())
    with pytest.raises(HTTPException) as error:
        routes.health_ready()
    assert error.value.status_code == 503
    assert "database" not in str(error.value.detail).casefold()
    assert "redis" not in str(error.value.detail).casefold()


def test_request_body_limit_rejects_oversized_content_length() -> None:
    response = scr.api._declared_body_error(str(scr.api.MAX_REQUEST_BODY_BYTES + 1))
    assert response is not None
    assert response.status_code == 413


def test_request_body_limit_rejects_invalid_content_length() -> None:
    response = scr.api._declared_body_error("not-a-number")
    assert response is not None
    assert response.status_code == 400


def test_first_workspace_bootstrap_is_available_only_without_accounts(monkeypatch) -> None:
    class Store:
        def __init__(self, count):
            self.count = count

        def ping(self):
            return True

        def account_count(self):
            return self.count

    class Registry:
        cache_backend = "memory"

        @staticmethod
        def cache_stats():
            return {}

    class Queue:
        @staticmethod
        def stats():
            return {}

    class RateLimiter:
        @staticmethod
        def ping_backend():
            return True

    class Model:
        available = False

    config = replace(routes.settings, auth_enabled=True, auth_allow_signup=False,
                     database_url="mysql+pymysql://research:secret@localhost/research?charset=utf8mb4",
                     redis_url="redis://localhost:6379/0")
    monkeypatch.setattr(routes, "settings", config)
    monkeypatch.setattr(routes, "registry", Registry())
    monkeypatch.setattr(routes, "task_queue", Queue())
    monkeypatch.setattr(routes, "rate_limiter", RateLimiter())
    monkeypatch.setattr(routes, "llm", Model())

    monkeypatch.setattr(routes, "persistence", Store(0))
    assert routes.health()["auth_bootstrap_available"] is True
    monkeypatch.setattr(routes, "persistence", Store(1))
    assert routes.health()["auth_bootstrap_available"] is False


def test_tools_and_stream_contract(monkeypatch) -> None:
    # Keep API contract tests offline even when the developer's DeepSeek key is configured.
    monkeypatch.setattr(routes, "agent", make_agent())
    payload = routes.tools()
    assert payload["pipeline"] == ["market_overview", "trend_analyzer", "category_explorer", "competitor_analysis", "review_miner", "keyword_research", "profit_calculator", "supplier_search", "product_scorer"]
    request = ResearchRequest(message="分析宠物饮水机", marketplace="US")
    report = routes.research(request)
    assert len(report["stages"]) == 9
    response = routes.research_stream(request)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    frames = list(routes.iter_research_events(request))
    events = [json.loads(frame.removeprefix("data: ")) for frame in frames if frame.startswith("data: ")]
    assert events[0]["type"] == "intent"
    assert sum(event["type"] == "stage_done" for event in events) == 9
    assert events[-1]["type"] == "complete"


def test_viewer_cannot_clear_shared_cache(monkeypatch) -> None:
    class Registry:
        cleared = 0

        def clear_cache(self):
            self.cleared += 1

        @staticmethod
        def cache_stats():
            return {}

    config = replace(routes.settings, auth_enabled=True, auth_secret="x" * 48)
    registry = Registry()
    monkeypatch.setattr(routes, "settings", config)
    monkeypatch.setattr(routes, "registry", registry)

    def request(role):
        return Request({
            "type": "http", "method": "DELETE", "path": "/api/cache", "headers": [],
            "query_string": b"", "state": {"actor": {"user_id": "u1", "organization_id": "o1", "role": role}},
        })

    with pytest.raises(HTTPException) as error:
        routes.clear_cache(request("viewer"))
    assert error.value.status_code == 403
    assert routes.clear_cache(request("admin")) == {"status": "cleared"}
    assert registry.cleared == 1
