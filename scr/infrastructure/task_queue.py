"""Durable Redis Streams queue with leases, bounded retries, DLQ, and local fallback."""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


class ResearchTaskQueue:
    MAX_ATTEMPTS = 3
    LEASE_MS = 120_000
    HEARTBEAT_SECONDS = 20

    def __init__(self, processor: Callable[[dict[str, Any], dict[str, Any] | None, Callable[[dict[str, Any]], None]], dict[str, Any]],
                 store: Any | None = None, redis_url: str = "", workers: int = 2, allow_local_fallback: bool = True,
                 task_timeout_seconds: int = 1800) -> None:
        self.processor, self.store = processor, store
        self.redis_url, self.worker_count = redis_url, max(1, min(16, workers))
        self.allow_local_fallback = allow_local_fallback
        self.task_timeout_seconds = max(60, int(task_timeout_seconds))
        self._executor = ThreadPoolExecutor(max_workers=self.worker_count, thread_name_prefix="research-worker")
        self._local: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._redis: Any | None = None
        self._worker_threads: list[threading.Thread] = []
        self._cancel_events: dict[str, threading.Event] = {}
        self._closed = False
        self._stream_key = "product-research:jobs:v2"
        self._group = "research-workers-v2"
        self._dead_letter_key = "product-research:dead-letter:v2"
        self._consumer = f"worker-{uuid4()}"

    def start(self, consume: bool = True) -> None:
        self._stop.clear()
        if self._closed:
            self._executor = ThreadPoolExecutor(max_workers=self.worker_count, thread_name_prefix="research-worker")
            self._closed = False
        if self._worker_threads:
            return
        if self.redis_url:
            try:
                import redis
                client = redis.Redis.from_url(self.redis_url, decode_responses=True,
                    socket_connect_timeout=2, socket_timeout=3, health_check_interval=30)
                client.ping()
                self._redis = client
                try:
                    client.xgroup_create(self._stream_key, self._group, id="0-0", mkstream=True)
                except Exception as exc:
                    if "BUSYGROUP" not in str(exc):
                        raise
                if consume:
                    for index in range(self.worker_count):
                        thread = threading.Thread(target=self._consume, name=f"research-stream-worker-{index}", daemon=True)
                        thread.start()
                        self._worker_threads.append(thread)
            except Exception as exc:
                self._redis = None
                logger.warning("Redis Streams unavailable error_type=%s", type(exc).__name__)
                if not self.allow_local_fallback:
                    raise RuntimeError("Redis Streams is required but unavailable; refusing unsafe local queue fallback.") from exc
        self._recover_tasks()

    def _recover_tasks(self) -> None:
        if not self.store:
            return
        for task in self.store.recoverable_tasks(stale_after_seconds=self.LEASE_MS // 1000):
            actor = None
            if task.get("user_id") and task.get("organization_id"):
                role = self.store.member_role(task["user_id"], task["organization_id"])
                if role:
                    actor = {"user_id": task["user_id"], "organization_id": task["organization_id"], "role": role}
            body = {key: task.get(key) for key in ("message", "marketplace", "intent", "params", "project_id")}
            self._enqueue({"task_id": task["task_id"], "organization_id": task.get("organization_id"), "body": body, "actor": actor}, attempt=0)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._worker_threads:
            thread.join(timeout=2)
        self._worker_threads.clear()
        self._executor.shutdown(wait=False, cancel_futures=False)
        self._closed = True

    def submit(self, body: dict[str, Any], actor: dict[str, Any] | None = None) -> str:
        if self.store:
            task_id = self.store.create_task(actor, body["message"], body["marketplace"], body.get("intent"), body.get("params", {}), body.get("project_id"))
        else:
            task_id = str(uuid4())
            with self._lock:
                self._local[task_id] = {"task_id": task_id, "organization_id": (actor or {}).get("organization_id"),
                    "user_id": (actor or {}).get("user_id"), "message": body["message"], "marketplace": body["marketplace"],
                    "intent": body.get("intent"), "params": body.get("params", {}), "status": "queued", "progress": {"completed": 0},
                    "favorite": False, "result": None, "created_at": datetime.now(timezone.utc).isoformat()}
        self._enqueue({"task_id": task_id, "organization_id": (actor or {}).get("organization_id"), "body": body, "actor": actor}, 0)
        return task_id

    def _enqueue(self, job: dict[str, Any], attempt: int = 0) -> None:
        if self._redis is not None:
            try:
                self._redis.xadd(self._stream_key, {"payload": json.dumps(job, ensure_ascii=False, separators=(",", ":")), "attempt": str(attempt)}, maxlen=100_000, approximate=True)
                return
            except Exception as exc:
                logger.warning("Redis enqueue failed error_type=%s", type(exc).__name__)
                if not self.allow_local_fallback:
                    raise RuntimeError("Redis Streams enqueue failed; task was not sent to a local worker.") from exc
        self._executor.submit(self._run_with_retries, job, attempt)

    def _run_with_retries(self, job: dict[str, Any], attempt: int = 0) -> None:
        for current_attempt in range(attempt, self.MAX_ATTEMPTS):
            succeeded = self._execute(job)
            if succeeded:
                return
            task = self.get(job["task_id"], job.get("organization_id")) or {}
            if task.get("status") == "cancelled":
                return
            if self.store and current_attempt + 1 < self.MAX_ATTEMPTS:
                if not self.store.requeue_task(job["task_id"], job.get("organization_id")):
                    return
            elif not self.store and current_attempt + 1 < self.MAX_ATTEMPTS:
                self._update(job["task_id"], job.get("organization_id"), status="queued", error=None)
            else:
                self._record_dead_letter(job["task_id"], current_attempt + 1, "task_failed")
                return
            self._stop.wait(min(2 ** current_attempt, 8))

    def get(self, task_id: str, organization_id: str | None) -> dict[str, Any] | None:
        if self.store:
            return self.store.get_task(task_id, organization_id)
        with self._lock:
            row = self._local.get(task_id)
            return dict(row) if row and row.get("organization_id") == organization_id else None

    def list(self, organization_id: str | None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if self.store:
            return self.store.list_tasks(organization_id, limit, offset)
        with self._lock:
            rows = [dict(row) for row in self._local.values() if row.get("organization_id") == organization_id]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[offset:offset + limit]

    def favorite(self, task_id: str, organization_id: str | None, favorite: bool) -> bool:
        if self.store:
            return self.store.set_favorite(task_id, organization_id, favorite)
        with self._lock:
            row = self._local.get(task_id)
            if not row or row.get("organization_id") != organization_id:
                return False
            row["favorite"] = favorite
            return True

    def cancel(self, task_id: str, organization_id: str | None) -> bool:
        if self.store:
            cancelled = self.store.cancel_task(task_id, organization_id)
        else:
            with self._lock:
                row = self._local.get(task_id)
                if not row or row.get("organization_id") != organization_id or row.get("status") not in {"queued", "running"}:
                    return False
                row.update(status="cancelled", progress={**(row.get("progress") or {}), "stage": "cancelled"})
                cancelled = True
        if cancelled:
            with self._lock:
                event = self._cancel_events.get(task_id)
                if event:
                    event.set()
        return cancelled

    def stats(self) -> dict[str, int | str]:
        if self._redis is None:
            return {"backend": "local", "backlog": sum(row.get("status") == "queued" for row in self._local.values()), "dead_letter": 0}
        try:
            pending = self._redis.xpending(self._stream_key, self._group)
            groups = self._redis.xinfo_groups(self._stream_key)
            group = next((row for row in groups if row.get("name") == self._group), {})
            lag = group.get("lag")
            pending_count = int(pending.get("pending", 0))
            backlog = pending_count + int(lag) if lag is not None else -1
            return {"backend": "redis_streams", "backlog": backlog,
                    "pending": pending_count, "dead_letter": int(self._redis.xlen(self._dead_letter_key))}
        except Exception as exc:
            logger.warning("queue stats unavailable error_type=%s", type(exc).__name__)
            return {"backend": "redis_streams", "backlog": -1, "pending": -1, "dead_letter": -1}

    def dead_letters(self, limit: int = 50) -> list[dict[str, str]]:
        if self._redis is None:
            return []
        try:
            rows = self._redis.xrevrange(self._dead_letter_key, count=max(1, min(100, limit)))
            return [{"message_id": str(message_id), "task_id": str(fields.get("task_id", "")),
                     "attempts": str(fields.get("attempts", "")), "error_type": str(fields.get("error_type", ""))}
                    for message_id, fields in rows]
        except Exception as exc:
            logger.warning("dead-letter listing failed error_type=%s", type(exc).__name__)
            return []

    def _consume(self) -> None:
        while not self._stop.is_set():
            try:
                reclaimed = self._redis.xautoclaim(self._stream_key, self._group, self._consumer,
                    min_idle_time=self.LEASE_MS, start_id="0-0", count=1)
                messages = reclaimed[1] if reclaimed and len(reclaimed) > 1 else []
                if not messages:
                    batches = self._redis.xreadgroup(self._group, self._consumer, {self._stream_key: ">"}, count=1, block=1000)
                    messages = batches[0][1] if batches else []
                for message_id, fields in messages:
                    self._process_stream_message(message_id, fields)
            except Exception as exc:
                if not self._stop.is_set():
                    logger.warning("Redis Streams poll failed error_type=%s", type(exc).__name__)
                    self._stop.wait(1)

    def _process_stream_message(self, message_id: str, fields: dict[str, str]) -> None:
        try:
            job = json.loads(fields["payload"])
            attempt = max(0, int(fields.get("attempt", "0")))
            succeeded = self._execute(job)
            task = self.get(job["task_id"], job.get("organization_id")) or {}
            if not succeeded and task.get("status") != "cancelled":
                if attempt + 1 < self.MAX_ATTEMPTS and self.store and self.store.requeue_task(job["task_id"], job.get("organization_id")):
                    self._stop.wait(min(2 ** attempt, 8))
                    self._redis.xadd(self._stream_key, {"payload": fields["payload"], "attempt": str(attempt + 1)}, maxlen=100_000, approximate=True)
                else:
                    self._record_dead_letter(job["task_id"], attempt + 1, "task_failed")
        except Exception as exc:
            logger.exception("Redis task message failed error_type=%s", type(exc).__name__)
            self._record_dead_letter("unknown", self.MAX_ATTEMPTS, type(exc).__name__)
        finally:
            self._redis.xack(self._stream_key, self._group, message_id)

    def _record_dead_letter(self, task_id: str, attempts: int, error: str | None) -> None:
        if self._redis is None:
            return
        try:
            # Keep user query text and credentials out of the dead-letter payload.
            self._redis.xadd(self._dead_letter_key, {"task_id": task_id, "attempts": str(attempts),
                "error_type": (str(error or "task_failed")[:120])}, maxlen=10_000, approximate=True)
        except Exception as exc:
            logger.warning("dead-letter write failed error_type=%s", type(exc).__name__)

    def _execute(self, job: dict[str, Any]) -> bool:
        task_id, organization_id = job["task_id"], job.get("organization_id")
        current = self.get(task_id, organization_id)
        if not current or current.get("status") in {"cancelled", "completed"}:
            return current is not None and current.get("status") == "completed"
        if self.store:
            if not self.store.claim_task(task_id, organization_id, self.LEASE_MS // 1000):
                latest = self.get(task_id, organization_id) or {}
                # A duplicate stream delivery must not race the active lease or
                # turn a healthy in-flight task into a dead letter.
                return latest.get("status") in {"running", "completed", "cancelled"}
        else:
            with self._lock:
                current = self._local.get(task_id)
                if not current or current.get("status") not in {"queued", "failed"}:
                    return current is not None and current.get("status") == "completed"
                current.update(status="running", progress={"completed": 0, "stage": "starting"})

        cancel_event = threading.Event()
        heartbeat_stop = threading.Event()
        started_at = time.monotonic()
        with self._lock:
            self._cancel_events[task_id] = cancel_event

        def heartbeat() -> None:
            while not heartbeat_stop.wait(self.HEARTBEAT_SECONDS):
                try:
                    self.store.heartbeat_task(task_id, organization_id)
                except Exception as exc:
                    logger.warning("task heartbeat failed error_type=%s", type(exc).__name__)

        heartbeat_thread = None
        if self.store:
            heartbeat_thread = threading.Thread(target=heartbeat, name="research-task-lease", daemon=True)
            heartbeat_thread.start()

        def on_event(event: dict[str, Any]) -> None:
            if cancel_event.is_set():
                raise TaskCancelled()
            if time.monotonic() - started_at > self.task_timeout_seconds:
                raise TaskTimedOut()
            kind, data = event.get("type"), event.get("data") or {}
            if kind in {"stage_start", "stage_done", "stage_skip"}:
                latest = self.get(task_id, organization_id) or {}
                progress = dict(latest.get("progress") or {})
                if kind == "stage_start":
                    progress["stage"] = data.get("stage")
                else:
                    progress["completed"] = int(progress.get("completed", 0)) + 1
                    progress["stage"] = data.get("stage")
                self._update(task_id, organization_id, progress=progress)

        succeeded = False
        try:
            result = self.processor(job["body"], job.get("actor"), on_event)
            if time.monotonic() - started_at > self.task_timeout_seconds:
                raise TaskTimedOut()
            if cancel_event.is_set() or (self.get(task_id, organization_id) or {}).get("status") == "cancelled":
                raise TaskCancelled()
            if self.store:
                self.store.update_task(task_id, organization_id, status="completed",
                    progress={"completed": len(result.get("stages", {})), "stage": "completed"}, result=result)
                self.store.save_evidence(task_id, organization_id, result)
                self.store.audit(job.get("actor"), "research.task.completed", task_id)
            else:
                self._update(task_id, organization_id, status="completed",
                    progress={"completed": len(result.get("stages", {})), "stage": "completed"}, result=result)
            succeeded = True
        except TaskCancelled:
            self._update(task_id, organization_id, status="cancelled", progress={"stage": "cancelled"})
        except TaskTimedOut:
            self._update(task_id, organization_id, status="failed", error="调研任务超出最长运行时间，已停止并允许重试。")
        except Exception as exc:
            logger.exception("Research task failed task_id=%s error_type=%s", task_id, type(exc).__name__)
            if cancel_event.is_set() or (self.get(task_id, organization_id) or {}).get("status") == "cancelled":
                self._update(task_id, organization_id, status="cancelled", progress={"stage": "cancelled"})
            else:
                self._update(task_id, organization_id, status="failed", error="调研任务执行失败，请稍后重试。")
        finally:
            heartbeat_stop.set()
            if heartbeat_thread:
                heartbeat_thread.join(timeout=1)
            with self._lock:
                self._cancel_events.pop(task_id, None)
        return succeeded

    def _update(self, task_id: str, organization_id: str | None, **fields: Any) -> None:
        if self.store:
            self.store.update_task(task_id, organization_id, **fields)
            return
        with self._lock:
            row = self._local.get(task_id)
            if row and row.get("organization_id") == organization_id:
                row.update(fields)


class TaskCancelled(Exception):
    """Raised inside a processor when a cooperative cancellation is requested."""


class TaskTimedOut(Exception):
    """Raised when a research task exceeds its configured execution deadline."""
