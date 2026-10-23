import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from scr.config import Settings
from scr.infrastructure.auth import hash_password, issue_token, verify_password, verify_token
from scr.infrastructure.persistence import PersistenceStore
from scr.infrastructure.task_queue import ResearchTaskQueue
from scr.application.identity import IdentityService


def test_mysql_is_valid_for_staging_persistence():
    config = Settings(
        app_env="staging",
        auth_enabled=True,
        auth_secret="x" * 48,
        database_url="mysql+pymysql://research:secret@localhost/research?charset=utf8mb4",
        redis_url="redis://localhost:6379/0",
    )
    config.validate_for_startup()


def test_password_hash_and_signed_token_round_trip():
    encoded = hash_password("a sufficiently long password")
    assert verify_password("a sufficiently long password", encoded)
    assert not verify_password("wrong password", encoded)
    actor = {"user_id": "user-1", "organization_id": "org-1", "role": "owner"}
    token = issue_token(actor, "x" * 48, 3600)
    assert verify_token(token, "x" * 48) == {**actor, "token_version": 0}
    assert verify_token(token, "y" * 48) is None


def test_only_one_concurrent_first_workspace_registration_succeeds(tmp_path):
    store = PersistenceStore(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    identity = IdentityService(
        store, lambda secret: f"hashed:{secret}", lambda secret, digest: digest == f"hashed:{secret}",
        lambda actor, secret, ttl: "token", lambda token, secret: None, "x" * 48, 3600, False,
    )
    start = Barrier(2)

    def register(index):
        start.wait()
        try:
            identity.register(f"owner{index}@example.test", "Owner", "password-123456", f"Workspace {index}")
            return "created"
        except PermissionError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(register, range(2)))

    assert outcomes.count("created") == 1
    assert outcomes.count("blocked") == 1
    assert store.account_count() == 1
    store.engine.dispose()


def test_persistence_tenant_scope_favorites_and_evidence(tmp_path):
    store = PersistenceStore(f"sqlite:///{tmp_path / 'enterprise.db'}")
    owner = store.create_account("owner@example.test", "Owner", hash_password("owner-password-123"), "Workspace")
    member = store.add_member(owner["organization_id"], "analyst@example.test", "Analyst", hash_password("analyst-password-123"), "analyst")
    assert store.member_role(member["user_id"], owner["organization_id"]) == "analyst"
    task_id = store.create_task(owner, "pet fountain", "US", "market_overview", {})
    assert store.get_task(task_id, owner["organization_id"])["status"] == "queued"
    assert store.get_task(task_id, "another-org") is None
    assert store.set_favorite(task_id, owner["organization_id"], True)
    assert store.get_task(task_id, owner["organization_id"])["favorite"] is True
    store.update_task(task_id, owner["organization_id"], status="completed", result={"stages": {}})
    store.save_evidence(task_id, owner["organization_id"], {"marketplace": "US", "stages": {"market_overview": {"data": {"source": "Amazon", "evidence": ["visible listings"], "data_timestamp": "2026-10-23T00:00:00Z"}}}})
    assert store.list_tasks(owner["organization_id"])[0]["status"] == "completed"
    store.engine.dispose()


def test_background_task_queue_persists_completion(tmp_path):
    store = PersistenceStore(f"sqlite:///{tmp_path / 'queue.db'}")
    started = Event()

    def processor(body, actor, on_event):
        started.set()
        on_event({"type": "stage_start", "data": {"stage": "market_overview"}})
        on_event({"type": "stage_done", "data": {"stage": "market_overview"}})
        return {"keyword": body["message"], "stages": {"market_overview": {"success": True}}}

    queue = ResearchTaskQueue(processor, store, workers=1)
    actor = store.create_account("q@example.test", "Q", hash_password("password-123456"), "Q Org")
    task_id = queue.submit({"message": "pet fountain", "marketplace": "US"}, actor)
    assert started.wait(3)
    deadline = time.time() + 5
    task = None
    while time.time() < deadline:
        task = queue.get(task_id, actor["organization_id"])
        if task and task["status"] == "completed":
            break
        time.sleep(0.02)
    assert task and task["status"] == "completed"
    assert task["result"]["keyword"] == "pet fountain"
    queue.stop()
    store.engine.dispose()


def test_queued_tasks_recover_after_process_restart(tmp_path):
    store = PersistenceStore(f"sqlite:///{tmp_path / 'recover.db'}")
    actor = store.create_account("recover@example.test", "Recover", hash_password("password-123456"), "Recover Org")
    task_id = store.create_task(actor, "desk lamp", "US", "market_overview", {"source": "test"})
    completed = Event()
    def processor(body, actor, on_event):
        completed.set()
        return {"keyword": body["message"], "stages": {}}
    queue = ResearchTaskQueue(processor, store, workers=1)
    queue.start()
    assert completed.wait(3)
    deadline = time.time() + 3
    while time.time() < deadline and store.get_task(task_id, actor["organization_id"])["status"] != "completed":
        time.sleep(0.01)
    assert store.get_task(task_id, actor["organization_id"])["status"] == "completed"
    queue.stop()
    store.engine.dispose()


def test_running_task_can_be_cancelled_cooperatively():
    started, release = Event(), Event()
    def processor(body, actor, on_event):
        started.set()
        release.wait(2)
        on_event({"type": "stage_start", "data": {"stage": "market_overview"}})
        return {"stages": {}}
    queue = ResearchTaskQueue(processor, workers=1)
    task_id = queue.submit({"message": "test", "marketplace": "US"})
    assert started.wait(2)
    assert queue.cancel(task_id, None)
    release.set()
    deadline = time.time() + 2
    while time.time() < deadline and queue.get(task_id, None)["status"] != "cancelled":
        time.sleep(0.01)
    assert queue.get(task_id, None)["status"] == "cancelled"
    queue.stop()


def test_local_queue_retries_transient_failure_and_completes():
    attempts = {"count": 0}
    def processor(body, actor, on_event):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary provider failure")
        return {"stages": {"market_overview": {"success": True}}}
    queue = ResearchTaskQueue(processor, workers=1)
    task_id = queue.submit({"message": "test", "marketplace": "US"})
    deadline = time.time() + 5
    while time.time() < deadline and queue.get(task_id, None)["status"] != "completed":
        time.sleep(0.01)
    assert attempts["count"] == 3
    assert queue.get(task_id, None)["status"] == "completed"
    queue.stop()


def test_task_timeout_is_reported_as_retryable_failure():
    attempts = {"count": 0}
    def processor(body, actor, on_event):
        attempts["count"] += 1
        time.sleep(0.03)
        on_event({"type": "stage_start", "data": {"stage": "market_overview"}})
        return {"stages": {}}
    queue = ResearchTaskQueue(processor, workers=1)
    queue.task_timeout_seconds = 0.01
    task_id = queue.submit({"message": "test", "marketplace": "US"})
    deadline = time.time() + 6
    while time.time() < deadline:
        task = queue.get(task_id, None)
        if attempts["count"] >= 3 and task["status"] == "failed":
            break
        time.sleep(0.01)
    task = queue.get(task_id, None)
    assert task["status"] == "failed"
    assert attempts["count"] == 3
    assert "超出最长运行时间" in task["error"]
    queue.stop()


def test_persistent_task_claim_is_atomic_and_recovery_respects_live_lease(tmp_path):
    from datetime import timedelta
    from scr.infrastructure.persistence import ResearchTaskRecord, now_utc

    store = PersistenceStore(f"sqlite:///{tmp_path / 'leases.db'}")
    owner = store.create_account("lease@example.test", "Lease", hash_password("password-123456"), "Lease Org")
    task_id = store.create_task(owner, "desk lamp", "US", "market_overview", {})
    assert store.claim_task(task_id, owner["organization_id"])
    assert not store.claim_task(task_id, owner["organization_id"])
    assert store.recoverable_tasks(stale_after_seconds=120) == []
    with store.session() as db:
        row = db.get(ResearchTaskRecord, task_id)
        row.updated_at = now_utc() - timedelta(minutes=5)
    assert len(store.recoverable_tasks(stale_after_seconds=120)) == 1
    assert store.claim_task(task_id, owner["organization_id"], stale_after_seconds=120)
    store.engine.dispose()


def test_redis_stream_retry_is_bounded_and_dead_letter_excludes_query_text():
    class Store:
        def __init__(self): self.status = "failed"; self.requeues = 0
        def get_task(self, task_id, organization_id): return {"status": self.status, "error": "provider timeout"}
        def requeue_task(self, task_id, organization_id):
            self.requeues += 1
            self.status = "queued"
            return True

    class Redis:
        def __init__(self): self.stream_entries = []; self.dead_entries = []; self.acked = []
        def xadd(self, key, fields, **kwargs):
            (self.dead_entries if "dead-letter" in key else self.stream_entries).append(fields)
        def xack(self, key, group, message_id): self.acked.append(message_id)

    store, redis = Store(), Redis()
    queue = ResearchTaskQueue(lambda *_: {}, store=store, redis_url="redis://unused")
    queue._redis = redis
    queue._execute = lambda _job: False
    payload = '{"task_id":"task-1","organization_id":"org-1","body":{"message":"private query"}}'
    queue._process_stream_message("1-0", {"payload": payload, "attempt": "1"})
    assert store.requeues == 1 and store.status == "queued"
    assert redis.stream_entries[0]["attempt"] == "2"
    assert redis.acked == ["1-0"]

    store.status = "failed"
    queue._process_stream_message("2-0", {"payload": payload, "attempt": "2"})
    assert len(redis.dead_entries) == 1
    assert redis.dead_entries[0]["attempts"] == "3"
    assert "private query" not in str(redis.dead_entries)
    queue.stop()


def test_redis_stream_worker_acknowledges_reclaimed_job_once():
    class Store:
        def __init__(self): self.status = "queued"; self.claims = 0; self.result = None
        def get_task(self, task_id, organization_id): return {"status": self.status, "progress": {}}
        def claim_task(self, task_id, organization_id, stale_after_seconds):
            self.claims += 1
            if self.status != "queued": return False
            self.status = "running"
            return True
        def update_task(self, task_id, organization_id, **fields):
            self.status = fields.get("status", self.status)
            self.result = fields.get("result", self.result)
        def save_evidence(self, *args): pass
        def audit(self, *args): pass

    class Redis:
        def __init__(self, queue): self.queue = queue; self.delivered = False; self.acks = []
        def xautoclaim(self, *args, **kwargs):
            if self.delivered: return ("0-0", [], [])
            self.delivered = True
            return ("0-0", [("5-0", {"payload": '{"task_id":"task-5","organization_id":"org-5","body":{"message":"query","marketplace":"US"}}', "attempt":"0"})], [])
        def xreadgroup(self, *args, **kwargs): return []
        def xack(self, stream, group, message_id):
            self.acks.append(message_id)
            self.queue._stop.set()

    store = Store()
    queue = ResearchTaskQueue(lambda *_: {"stages": {"market_overview": {"success": True}}}, store=store)
    redis = Redis(queue)
    queue._redis = redis
    queue._consume()
    assert store.claims == 1 and store.status == "completed"
    assert redis.acks == ["5-0"]
    queue.stop()


def test_enterprise_project_evidence_review_candidate_compliance_and_feedback(tmp_path):
    from sqlalchemy import inspect

    store = PersistenceStore(f"sqlite:///{tmp_path / 'workflow.db'}")
    assert store.schema_version >= 2
    assert "project_id" in {column["name"] for column in inspect(store.engine).get_columns("research_tasks")}
    owner = store.create_account("workflow@example.test", "Workflow", hash_password("password-123456"), "Workflow Org")
    project = store.create_project(owner["organization_id"], owner["user_id"], "US pet research")
    assert store.validate_project(owner["organization_id"], project["project_id"])
    task_id = store.create_task(owner, "pet fountain", "US", "market_overview", {}, project["project_id"])
    store.update_task(task_id, owner["organization_id"], status="completed", result={"report_markdown": "A sourced report.", "stages": {}})
    store.save_evidence(task_id, owner["organization_id"], {"report_markdown": "A sourced report.", "stages": {}})
    candidate = store.save_candidate(owner, "ASIN-B00000001", "Pet water fountain", "US", "Amazon", "https://example.test/item", {"price": 20}, project["project_id"], task_id)
    assert store.validate_candidate(owner["organization_id"], candidate["candidate_id"])
    assessment = store.add_compliance_assessment(owner, "US", "Pet supplies", "manual source", "2026-10-23", {"needs_review": True}, project["project_id"], candidate["candidate_id"])
    review = store.add_report_review(task_id, owner["organization_id"], owner["user_id"], "approved", "Reviewed")
    feedback = store.add_business_feedback(owner, "selected", task_id, {"units": 10}, "Pilot")
    assert assessment["status"] == "needs_human_review"
    assert review["status"] == "approved"
    assert feedback["outcome"] == "selected"
    assert store.list_report_versions(task_id, owner["organization_id"])[0]["content"] == "A sourced report."
    assert len(store.list_candidates(owner["organization_id"], project["project_id"])) == 1
    store.engine.dispose()


def test_rate_limiter_blocks_over_limit_and_resets_next_window():
    from scr.infrastructure.rate_limit import RequestRateLimiter

    limiter = RequestRateLimiter()
    assert limiter.allow("api", "127.0.0.1", 2, now=120.0)[0]
    assert limiter.allow("api", "127.0.0.1", 2, now=121.0)[0]
    allowed, retry = limiter.allow("api", "127.0.0.1", 2, now=122.0)
    assert not allowed and retry > 0
    assert limiter.allow("api", "127.0.0.1", 2, now=180.0)[0]


def test_downloadable_report_sections_are_human_readable_not_json():
    from scr.application.agent import _report_stage_details

    markdown = _report_stage_details("market_overview", {"total_product_count": 48, "avg_price": 45.9})
    assert "```" not in markdown
    assert "48" in markdown and "45.9" in markdown
    assert "\\u5546" not in markdown


def test_domain_and_application_keep_infrastructure_and_web_framework_out_of_dependencies():
    import ast
    from pathlib import Path

    forbidden = ("scr.infrastructure", "fastapi", "sqlalchemy", "redis", "httpx", "openai")
    for layer in (Path("scr/domain"), Path("scr/application")):
        for source_path in layer.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import): imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module: imported.append(node.module)
            assert not [name for name in imported if name.startswith(forbidden)], str(source_path)


def test_unavailable_provider_results_are_not_cached():
    from scr.application.tool_registry import MarketOverviewTool
    from scr.infrastructure.cache import MemoryTTLCache

    class UnavailableProvider:
        calls = 0
        def fetch(self, kind, keyword, marketplace, params):
            self.calls += 1
            return {"available": False, "items": {}, "source": "provider", "note": "provider unavailable"}

    provider = UnavailableProvider()
    tool = MarketOverviewTool(MemoryTTLCache(), provider, 60)
    first = tool.run("desk lamp", "US")
    second = tool.run("desk lamp", "US")
    assert first.data["available"] is False and second.data["available"] is False
    assert provider.calls == 2
