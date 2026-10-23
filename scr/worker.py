"""Standalone Redis-backed research worker entry point."""
from __future__ import annotations

import logging
import threading

from scr.config import settings
from scr.infrastructure.container import build_http_runtime


def main() -> None:
    settings.validate_for_startup()
    if not settings.redis_url:
        raise RuntimeError("Standalone worker requires REDIS_URL.")
    runtime = build_http_runtime()
    task_queue = runtime.task_queue
    task_queue.start(consume=True)
    if task_queue._redis is None:
        raise RuntimeError("Redis is unavailable; standalone worker cannot start.")
    logging.getLogger(__name__).info("research_worker_started workers=%s", settings.task_queue_workers)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        task_queue.stop()


if __name__ == "__main__":
    main()
