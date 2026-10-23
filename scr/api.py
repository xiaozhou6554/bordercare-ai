from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4
import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from scr.config import ROOT, settings
from scr.interfaces.http import routes
from scr.infrastructure.container import build_http_runtime

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_REQUEST_BODY_BYTES = 1_048_576


class RequestBodyTooLarge(Exception):
    pass


def _declared_body_error(content_length: str | None):
    if content_length is None:
        return None
    try:
        declared_length = int(content_length)
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "无效的请求体长度。"})
    if declared_length < 0:
        return JSONResponse(status_code=400, content={"detail": "无效的请求体长度。"})
    if declared_length > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "请求体超过 1 MiB 限制。"})
    return None
routes.configure_runtime(build_http_runtime())
router = routes.router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    routes.task_queue.start(consume=settings.task_queue_role != "api")
    yield
    routes.task_queue.stop()


app = FastAPI(title=settings.project_name, description="跨境电商选品调研工作台与 Agent API", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=ROOT / "scr" / "interfaces" / "web"), name="static")


@app.middleware("http")
async def organization_authentication(request: Request, call_next):
    started = perf_counter()
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if _REQUEST_ID.fullmatch(supplied_id) else str(uuid4())
    request.state.request_id = request_id
    path = request.url.path
    response = _declared_body_error(request.headers.get("content-length"))

    original_receive = request.receive
    received_bytes = 0

    async def limited_receive():
        nonlocal received_bytes
        message = await original_receive()
        if message["type"] == "http.request":
            received_bytes += len(message.get("body", b""))
            if received_bytes > MAX_REQUEST_BODY_BYTES:
                raise RequestBodyTooLarge
        return message

    request._receive = limited_receive
    health_paths = {"/api/health", "/api/health/live", "/api/health/ready"}
    if response is None and path.startswith("/api/") and path not in health_paths:
        client_ip = request.client.host if request.client else "unknown"
        is_auth = path in {"/api/auth/login", "/api/auth/register"}
        allowed, retry_after = routes.rate_limiter.allow("auth" if is_auth else "api", client_ip,
                                                  settings.auth_rate_limit_per_minute if is_auth else settings.api_rate_limit_per_minute)
        if not allowed:
            response = JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试。"}, headers={"Retry-After": str(retry_after)})
    if response is None and settings.auth_enabled and path.startswith("/api/") and path not in health_paths | {"/api/auth/register", "/api/auth/login"}:
        if not routes.persistence or len(settings.auth_secret) < 32:
            response = JSONResponse(status_code=503, content={"detail": "认证服务暂不可用，请检查数据库和认证配置。"})
        else:
            header = request.headers.get("authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else ""
            actor = routes.identity.authenticate(token) if token else None
            if not actor:
                response = JSONResponse(status_code=401, content={"detail": "登录已失效或令牌无效，请重新登录。"})
            else:
                role = actor["role"]
                request.state.actor = actor
                write_paths = ("/api/research", "/api/research/stream", "/api/tasks", "/api/members")
                if role == "viewer" and request.method not in {"GET", "HEAD"} and path.startswith(write_paths):
                    response = JSONResponse(status_code=403, content={"detail": "当前账号为只读角色，不能执行此操作。"})
    if response is None:
        try:
            response = await call_next(request)
        except RequestBodyTooLarge:
            response = JSONResponse(status_code=413, content={"detail": "请求体超过 1 MiB 限制。"})
    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Server-Timing", f"app;dur={(perf_counter() - started) * 1000:.1f}")
    logger.info("http_request request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id, request.method, path, response.status_code, (perf_counter() - started) * 1000)
    return response

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "scr" / "interfaces" / "web" / "index.html")


@app.get("/health", include_in_schema=False)
def health_compat():
    from scr.interfaces.http.routes import health as api_health
    return api_health()
