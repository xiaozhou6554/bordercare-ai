from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated, Any, Iterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi import status

from scr.application.agent import PIPELINE
from scr.application.idempotency import IdempotencyConflict
from scr.application.identity import IdentityService
from scr.application.research_task import scope_session_id
from scr.application.runtime import RuntimeServices
from scr.config import settings
from scr.domain.services import calculate_profit
from scr.interfaces.http.schemas import (CandidateRequest, ComplianceRequest, FavoriteRequest, FeedbackRequest,
    LoginRequest, MemberCreateRequest, ProfitRequest, ProjectRequest, RegisterRequest, ResearchRequest, ReviewRequest)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
identity: IdentityService | None = None
agent: Any = None
registry: Any = None
llm: Any = None
session_memory: Any = None
idempotency: Any = None
persistence: Any = None
task_queue: Any = None
rate_limiter: Any = None


def configure_runtime(runtime: RuntimeServices) -> None:
    """Receive concrete services from the infrastructure composition root."""
    global identity, agent, registry, llm, session_memory, idempotency, persistence, task_queue, rate_limiter
    identity = runtime.identity
    agent, registry, llm = runtime.agent, runtime.tools, runtime.model
    session_memory, idempotency = runtime.session_memory, runtime.idempotency
    persistence, task_queue = runtime.workspace, runtime.task_queue
    rate_limiter = runtime.rate_limiter


def _require_enterprise_store() -> Any:
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="企业账号功能尚未启用。")
    if not persistence or len(settings.auth_secret) < 32:
        raise HTTPException(status_code=503, detail="企业功能需要可用的数据库以及至少 32 位 AUTH_SECRET。")
    return persistence


def _require_role(actor: dict[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    if not actor:
        raise HTTPException(status_code=401, detail="请先登录。")
    if actor.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="当前账号没有执行此操作的权限。")
    return actor


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest) -> dict[str, Any]:
    try:
        _require_enterprise_store()
        return identity.register(request.email, request.display_name, request.password, request.organization_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂不可用，请检查数据库配置。") from exc


@router.post("/auth/login")
def login(request: LoginRequest) -> dict[str, Any]:
    try:
        _require_enterprise_store()
        return identity.login(request.email, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂不可用，请检查数据库配置。") from exc


@router.get("/auth/me")
def who_am_i(http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst", "viewer"})
    return actor


@router.get("/members")
def list_members(http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin"})
    store = _require_enterprise_store()
    return {"members": store.list_members(actor["organization_id"])}


@router.post("/members", status_code=status.HTTP_201_CREATED)
def create_member(request: MemberCreateRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin"})
    if actor["role"] == "admin" and request.role == "admin":
        raise HTTPException(status_code=403, detail="管理员不能创建其他管理员账号。")
    store = _require_enterprise_store()
    try:
        member = store.add_member(actor["organization_id"], request.email, request.display_name, identity.hash_password(request.password), request.role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.audit(actor, "organization.member.created", member["user_id"], {"role": request.role})
    return {"member": member}


@router.delete("/members/{user_id}")
def remove_member(user_id: str, http_request: Request) -> dict[str, bool]:
    actor = _require_role(_actor(http_request), {"owner", "admin"})
    if actor["user_id"] == user_id:
        raise HTTPException(status_code=409, detail="不能移除当前登录账号。")
    store = _require_enterprise_store()
    target_role = store.member_role(user_id, actor["organization_id"])
    if not target_role:
        raise HTTPException(status_code=404, detail="工作区成员不存在。")
    if target_role == "owner" or (actor["role"] == "admin" and target_role == "admin"):
        raise HTTPException(status_code=403, detail="当前管理员无权移除该成员。")
    if not store.disable_member(actor["organization_id"], user_id):
        raise HTTPException(status_code=404, detail="工作区成员不存在。")
    persistence.audit(actor, "organization.member.removed", user_id)
    return {"removed": True}


@router.get("/projects")
def projects(http_request: Request, include_archived: bool = False) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst", "viewer"})
    return {"projects": _require_enterprise_store().list_projects(actor["organization_id"], include_archived)}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(request: ProjectRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst"})
    project = _require_enterprise_store().create_project(actor["organization_id"], actor["user_id"], request.name, request.description)
    persistence.audit(actor, "research.project.created", project["project_id"])
    return project


@router.delete("/projects/{project_id}")
def archive_project(project_id: str, http_request: Request) -> dict[str, bool]:
    actor = _require_role(_actor(http_request), {"owner", "admin"})
    if not _require_enterprise_store().archive_project(actor["organization_id"], project_id):
        raise HTTPException(status_code=404, detail="项目不存在。")
    persistence.audit(actor, "research.project.archived", project_id)
    return {"archived": True}


@router.get("/tasks/{task_id}/report-versions")
def report_versions(task_id: str, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst", "viewer"})
    store = _require_enterprise_store()
    if not store.get_task(task_id, actor["organization_id"]):
        raise HTTPException(status_code=404, detail="任务不存在或无权查看。")
    return {"versions": store.list_report_versions(task_id, actor["organization_id"])}


@router.get("/tasks/{task_id}/reviews")
def report_reviews(task_id: str, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst", "viewer"})
    store = _require_enterprise_store()
    if not store.get_task(task_id, actor["organization_id"]):
        raise HTTPException(status_code=404, detail="任务不存在或无权查看。")
    return {"reviews": store.list_report_reviews(task_id, actor["organization_id"])}


@router.post("/tasks/{task_id}/reviews", status_code=status.HTTP_201_CREATED)
def add_report_review(task_id: str, request: ReviewRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst"})
    if request.status in {"approved", "rejected"} and actor["role"] not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="只有工作区所有者或管理员可以审批报告。")
    try:
        review = _require_enterprise_store().add_report_review(task_id, actor["organization_id"], actor["user_id"], request.status, request.comment)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    persistence.audit(actor, "research.report.reviewed", task_id, {"status": request.status})
    return review


@router.get("/candidates")
def candidates(http_request: Request, project_id: str | None = None) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst", "viewer"})
    store = _require_enterprise_store()
    if project_id and not store.validate_project(actor["organization_id"], project_id):
        raise HTTPException(status_code=404, detail="项目不存在或无权查看。")
    return {"candidates": store.list_candidates(actor["organization_id"], project_id)}


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def save_candidate(request: CandidateRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst"})
    store = _require_enterprise_store()
    if request.project_id and not store.validate_project(actor["organization_id"], request.project_id):
        raise HTTPException(status_code=404, detail="项目不存在或无权查看。")
    if request.task_id and not store.get_task(request.task_id, actor["organization_id"]):
        raise HTTPException(status_code=404, detail="关联调研任务不存在或无权查看。")
    candidate = store.save_candidate(actor, request.external_key, request.title, request.marketplace, request.source,
                                     request.source_url, request.data, request.project_id, request.task_id)
    persistence.audit(actor, "product.candidate.saved", candidate["candidate_id"])
    return candidate


@router.post("/compliance-assessments", status_code=status.HTTP_201_CREATED)
def compliance_assessment(request: ComplianceRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst"})
    store = _require_enterprise_store()
    if request.project_id and not store.validate_project(actor["organization_id"], request.project_id):
        raise HTTPException(status_code=404, detail="项目不存在或无权查看。")
    if request.candidate_id and not store.validate_candidate(actor["organization_id"], request.candidate_id):
        raise HTTPException(status_code=404, detail="候选商品不存在或无权查看。")
    return store.add_compliance_assessment(actor, request.marketplace, request.category, request.rule_source,
        request.rules_updated_at, request.findings, request.project_id, request.candidate_id)


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def business_feedback(request: FeedbackRequest, http_request: Request) -> dict[str, Any]:
    actor = _require_role(_actor(http_request), {"owner", "admin", "analyst"})
    store = _require_enterprise_store()
    if request.task_id and not store.get_task(request.task_id, actor["organization_id"]):
        raise HTTPException(status_code=404, detail="关联调研任务不存在或无权查看。")
    return store.add_business_feedback(actor, request.outcome, request.task_id, request.metrics, request.notes)


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def submit_task(request: ResearchRequest, http_request: Request) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst"})
    if request.project_id and persistence and not persistence.validate_project((actor or {}).get("organization_id", ""), request.project_id):
        raise HTTPException(status_code=404, detail="项目不存在、已归档或不属于当前工作区。")
    task_id = task_queue.submit(request.model_dump(), actor)
    return {"task_id": task_id, "status": "queued", "poll_url": f"/api/tasks/{task_id}"}


@router.get("/tasks")
def task_history(http_request: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst", "viewer"})
    return {"tasks": task_queue.list((actor or {}).get("organization_id"), max(1, min(100, limit)), max(0, offset))}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, http_request: Request) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst", "viewer"})
    task = task_queue.get(task_id, (actor or {}).get("organization_id"))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或无权查看。")
    return task


@router.delete("/tasks/{task_id}")
def cancel_task(task_id: str, http_request: Request) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst"})
    organization_id = (actor or {}).get("organization_id")
    if not task_queue.cancel(task_id, organization_id):
        task = task_queue.get(task_id, organization_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在或无权取消。")
        raise HTTPException(status_code=409, detail="任务已结束，无法取消。")
    if persistence:
        persistence.audit(actor, "research.task.cancelled", task_id)
    return {"task_id": task_id, "status": "cancelled"}


@router.post("/tasks/{task_id}/favorite")
def favorite_task(task_id: str, request: FavoriteRequest, http_request: Request) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst"})
    if not task_queue.favorite(task_id, (actor or {}).get("organization_id"), request.favorite):
        raise HTTPException(status_code=404, detail="任务不存在或无权修改。")
    if persistence:
        persistence.audit(actor, "research.task.favorite_changed", task_id, {"favorite": request.favorite})
    return {"task_id": task_id, "favorite": request.favorite}


@router.get("/tasks/{task_id}/export", response_class=PlainTextResponse)
def export_task(task_id: str, http_request: Request) -> PlainTextResponse:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst", "viewer"})
    task = task_queue.get(task_id, (actor or {}).get("organization_id"))
    if not task or not task.get("result"):
        raise HTTPException(status_code=404, detail="调研报告不存在或任务尚未完成。")
    if persistence:
        persistence.audit(actor, "research.report.exported", task_id)
    report = task["result"].get("report_markdown") or task["result"].get("answer") or "暂无可导出的报告内容。"
    return PlainTextResponse(str(report), media_type="text/markdown; charset=utf-8")


@router.post("/tasks/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_task(task_id: str, http_request: Request) -> dict[str, Any]:
    actor = _actor(http_request)
    if settings.auth_enabled:
        _require_role(actor, {"owner", "admin", "analyst"})
    task = task_queue.get(task_id, (actor or {}).get("organization_id"))
    if not task or task.get("status") != "failed":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试。")
    body = {"message": task["message"], "marketplace": task["marketplace"], "intent": task.get("intent"), "params": task.get("params", {}), "project_id": task.get("project_id")}
    new_id = task_queue.submit(body, actor)
    return {"task_id": new_id, "status": "queued", "poll_url": f"/api/tasks/{new_id}"}


@router.get("/admin/queue/dead-letters")
def queue_dead_letters(limit: int = 50, http_request: Request = None) -> dict[str, Any]:
    actor = _actor(http_request)
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="队列管理功能仅在启用认证后开放。")
    _require_role(actor, {"owner", "admin"})
    return {"items": task_queue.dead_letters(max(1, min(100, limit))), "stats": task_queue.stats()}


@router.get("/health")
def health() -> dict[str, Any]:
    database_status = "disabled"
    if persistence:
        try:
            persistence.ping()
            database_status = "connected"
        except Exception as exc:
            database_status = "unavailable"
            logger.warning("health database probe failed error_type=%s", type(exc).__name__)
    auth_bootstrap_available = False
    if settings.auth_enabled and persistence and database_status == "connected":
        try:
            auth_bootstrap_available = persistence.account_count() == 0
        except Exception as exc:
            logger.warning("health auth bootstrap probe failed error_type=%s", type(exc).__name__)
    redis_status = "disabled"
    if settings.redis_url:
        redis_status = "connected" if rate_limiter.ping_backend() else "unavailable"
        if redis_status == "unavailable":
            logger.warning("health redis probe failed")
    healthy = database_status != "unavailable" and redis_status != "unavailable"
    return {
        "status": "ok" if healthy else "degraded",
        "auth_enabled": settings.auth_enabled,
        "auth_allow_signup": settings.auth_allow_signup,
        "auth_bootstrap_available": auth_bootstrap_available,
    }


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready() -> dict[str, Any]:
    result = health()
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail={"status": "not_ready"})
    return result


@router.get("/tools")
def tools() -> dict[str, Any]:
    return {"tools": list(registry.names), "pipeline": PIPELINE}


@router.post("/research")
def research(request: ResearchRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
             http_request: Request = None) -> dict[str, Any]:
    try:
        actor = _actor(http_request)
        events, replayed = idempotency.execute(idempotency_key, _fingerprint(request), lambda: (_collect_events(request, actor) if actor else _collect_events(request)))
        result = next(event["data"] for event in reversed(events) if event["type"] == "complete")
        if not replayed:
            _persist_report(actor, request, result)
        return result
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Research request failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Request could not be processed. Check input and try again.") from exc


@router.post("/research/stream")
def research_stream(request: ResearchRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
                    http_request: Request = None) -> StreamingResponse:
    actor = _actor(http_request)
    if idempotency_key:
        try:
            events, replayed = idempotency.execute(idempotency_key, _fingerprint(request), lambda: (_collect_events(request, actor) if actor else _collect_events(request)))
            if not replayed:
                result = next(event["data"] for event in reversed(events) if event["type"] == "complete")
                _persist_report(actor, request, result)
            content = serialize_events(events)
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        content = iter_research_events(request, actor)
    return StreamingResponse(content, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def iter_research_events(request: ResearchRequest, actor: dict[str, Any] | None = None) -> Iterator[str]:
    try:
        public_session_id = request.session_id or str(uuid4())
        session_id = _session_key(public_session_id, actor)
        previous = session_memory.load(session_id)
        events = []
        assistant_text = ""
        for event in agent.stream(request.message, request.marketplace, request.intent, request.params, session_id, previous["messages"]):
            if event["type"] == "complete":
                event["data"]["session_id"] = public_session_id
                assistant_text = str(event["data"].get("answer") or event["data"].get("report_markdown") or "")
                _persist_report(actor, request, event["data"])
            elif event["type"] == "intent":
                event["data"]["session_id"] = public_session_id
            events.append(event)
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        if assistant_text:
            session_memory.save_turn(session_id, request.message, assistant_text, request.marketplace)
    except Exception as exc:
        logger.error("SSE research request failed error_type=%s", type(exc).__name__)
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Request could not be processed.'}})}\n\n"


def _collect_events(request: ResearchRequest, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    public_session_id = request.session_id or str(uuid4())
    session_id = _session_key(public_session_id, actor)
    previous = session_memory.load(session_id)
    events = list(agent.stream(request.message, request.marketplace, request.intent, request.params, session_id, previous["messages"]))
    for event in events:
        if event["type"] == "complete":
            event["data"]["session_id"] = public_session_id
            response = event["data"]
            assistant_text = response.get("answer") or response.get("report_markdown") or ""
            if assistant_text:
                session_memory.save_turn(session_id, request.message, str(assistant_text), request.marketplace)
    return events


def _actor(http_request: Request | None) -> dict[str, Any] | None:
    return getattr(getattr(http_request, "state", None), "actor", None)


def _session_key(session_id: str, actor: dict[str, Any] | None) -> str:
    return scope_session_id(session_id, actor, settings.auth_enabled)


def _persist_report(actor: dict[str, Any] | None, request: ResearchRequest, result: dict[str, Any]) -> None:
    if not persistence:
        return
    task_id = persistence.create_task(actor, request.message, request.marketplace, request.intent, request.params)
    persistence.update_task(task_id, (actor or {}).get("organization_id"), status="completed",
                            progress={"completed": len(result.get("stages", {})), "stage": "completed"}, result=result)
    persistence.save_evidence(task_id, (actor or {}).get("organization_id"), result)
    persistence.audit(actor, "research.report.created", task_id)


def serialize_events(events: list[dict[str, Any]]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _fingerprint(request: ResearchRequest) -> str:
    payload = json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@router.post("/profit")
def profit(request: ProfitRequest) -> dict[str, Any]:
    try:
        return calculate_profit(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cache")
def cache_stats() -> dict[str, int]:
    return registry.cache_stats()


@router.delete("/cache")
def clear_cache(http_request: Request = None) -> dict[str, str]:
    if settings.auth_enabled:
        _require_role(_actor(http_request), {"owner", "admin"})
    registry.clear_cache()
    return {"status": "cleared"}


@router.delete("/session/{session_id}")
def clear_session(session_id: str, http_request: Request = None) -> dict[str, str]:
    try:
        normalized_id = str(UUID(session_id))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session ID")
    actor = _actor(http_request)
    session_memory.clear(_session_key(normalized_id, actor))
    if persistence:
        persistence.audit(actor, "session.memory.deleted", normalized_id)
    return {"status": "cleared"}
